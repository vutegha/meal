"""Journaux structurés, mesures Prometheus et suivi des erreurs, sans données personnelles.

- Journaux : une ligne JSON par événement (`LOG_FORMAT=json`, par défaut en production), avec
  l'identifiant de la requête. Le chemin est journalisé sans ses paramètres (une recherche de
  personne y met un nom) et les téléphones et adresses e-mail sont masqués dans les messages.
- Mesures : durée et nombre des requêtes par route (gabarit de la route, jamais l'adresse
  réelle), exposées sur `/metrics`. Caddy ne transmet que `/api/*` et `/health` : `/metrics`
  n'est joignable que depuis le réseau Docker, pour un Prometheus voisin.
- Erreurs : envoyées à Sentry ou à GlitchTip (auto-hébergé) seulement si `SENTRY_DSN` est
  défini, sans en-têtes, corps de requête, cookies ni utilisateur, et après masquage.
"""

import json
import logging
import os
import re
import sys
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any
from uuid import uuid4

# Mode multiprocessus (plusieurs processus d'API) : le dossier doit exister avant les mesures.
if directory := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    os.makedirs(directory, exist_ok=True)

from prometheus_client import (  # noqa: E402
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Numéros de téléphone : +243 970 000 000, 0970000000… (8 chiffres ou plus, espacés ou non).
_PHONE = re.compile(r"(?<![\w-])\+?\d(?:[\s.-]?\d){7,}(?![\w-])")


def scrub(text: str) -> str:
    """Masque adresses e-mail et numéros de téléphone d'un texte."""
    return _PHONE.sub("[téléphone]", _EMAIL.sub("[e-mail]", text))


class JsonFormatter(logging.Formatter):
    _STANDARD = set(vars(logging.makeLogRecord({})))

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": scrub(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in self._STANDARD and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exception"] = scrub(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """Journaux JSON sur la sortie standard (`LOG_FORMAT=text` pour le développement)."""
    if os.environ.get("LOG_FORMAT", "text") != "json":
        logging.basicConfig(level=logging.INFO)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "arq"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def _strip_event(event: dict[str, Any], _: dict[str, Any]) -> dict[str, Any] | None:
    event.pop("user", None)
    request = event.get("request")
    if isinstance(request, dict):
        event["request"] = {
            "method": request.get("method"),
            # Adresse sans paramètres : une recherche de personne y mettrait un nom.
            "url": str(request.get("url", "")).split("?")[0],
        }
    for exception in (event.get("exception") or {}).get("values", []):
        if isinstance(exception.get("value"), str):
            exception["value"] = scrub(exception["value"])
        for frame in (exception.get("stacktrace") or {}).get("frames", []):
            frame.pop("vars", None)
    if isinstance(event.get("message"), str):
        event["message"] = scrub(event["message"])
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = scrub(logentry[key])
        logentry.pop("params", None)
    for crumb in (event.get("breadcrumbs") or {}).get("values", []):
        if isinstance(crumb.get("message"), str):
            crumb["message"] = scrub(crumb["message"])
        crumb.pop("data", None)
    return event


def init_sentry() -> None:
    """Suivi des erreurs, seulement si `SENTRY_DSN` est défini."""
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("ENVIRONMENT", "production"),
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        before_send=_strip_event,  # type: ignore[arg-type]
    )


REQUESTS = Counter(
    "wemeal_http_requests_total", "Requêtes HTTP traitées", ["method", "route", "status"]
)
DURATION = Histogram(
    "wemeal_http_request_duration_seconds",
    "Durée des requêtes HTTP",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

_logger = logging.getLogger("wemeal.requests")
# Requêtes plus lentes : journalisées en avertissement.
SLOW_SECONDS = 1.0


def metrics_payload() -> tuple[bytes, str]:
    """Mesures de tous les processus de l'API (`PROMETHEUS_MULTIPROC_DIR`) ou du seul courant."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST


class ObservabilityMiddleware:
    """Identifiant de requête, durée par route et une ligne de journal par requête."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")[:64]
        request_id = incoming if re.fullmatch(r"[\w.-]{1,64}", incoming) else uuid4().hex
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            elapsed = time.perf_counter() - started
            route = getattr(scope.get("route"), "path", None) or "inconnue"
            method = scope.get("method", "")
            if route != "/metrics":
                REQUESTS.labels(method, route, str(status_code)).inc()
                DURATION.labels(method, route).observe(elapsed)
                level = (
                    logging.ERROR
                    if status_code >= 500
                    else logging.WARNING
                    if elapsed >= SLOW_SECONDS
                    else logging.INFO
                )
                _logger.log(
                    level,
                    "%s %s %s",
                    method,
                    route,
                    status_code,
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "route": route,
                        "status": status_code,
                        "duration_ms": round(elapsed * 1000, 1),
                    },
                )
