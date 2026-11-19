"""Registre des effacements de données personnelles, rejoué après une restauration.

Une sauvegarde de la veille contient encore les données d'une personne effacée ce matin :
restaurée telle quelle, elle les ferait revenir. Chaque effacement demandé (demande d'une
personne, suppression d'un compte, fermeture d'un espace) est donc inscrit dans un fichier à
part, hors de la base et des fichiers sauvegardés (`ERASURE_LOG_PATH`, volume `erasures`). Après
une restauration, `python -m app.scripts.replay_erasures` refait chacun de ces effacements.

Le registre ne contient que des identifiants techniques et des dates, jamais de nom ni de
contenu. L'inscription a lieu après la validation de la transaction : un effacement annulé n'y
figure pas.
"""

import json
import logging
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

Kind = Literal["feedback", "submission", "user", "organization"]
_PENDING = "pending_erasures"
# Session qui rejoue le registre : ses effacements y sont déjà.
REPLAYING = "replaying_erasures"


@dataclass(frozen=True)
class Erasure:
    kind: Kind
    entity_id: UUID
    organization_id: UUID | None
    at: datetime


def log_path() -> Path:
    return Path(get_settings().erasure_log_path)


def record(
    session: AsyncSession, kind: Kind, ids: Iterable[UUID], organization_id: UUID | None = None
) -> None:
    """Inscrit des effacements, écrits dans le registre quand la transaction est validée."""
    if session.sync_session.info.get(REPLAYING):
        return
    now = datetime.now(UTC)
    pending = session.sync_session.info.setdefault(_PENDING, [])
    pending.extend(Erasure(kind, entity_id, organization_id, now) for entity_id in ids)


def _line(erasure: Erasure) -> str:
    return json.dumps(
        {
            "kind": erasure.kind,
            "id": str(erasure.entity_id),
            "org": str(erasure.organization_id) if erasure.organization_id else None,
            "at": erasure.at.isoformat(),
        }
    )


def append(erasures: list[Erasure]) -> None:
    if not erasures:
        return
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(_line(e) + "\n" for e in erasures).encode()
    # Ajout en fin de fichier, en une écriture : sûr entre plusieurs processus.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@event.listens_for(Session, "after_commit")
def _write_pending(session: Session) -> None:
    pending: list[Erasure] = session.info.pop(_PENDING, [])
    try:
        append(pending)
    except OSError:
        # L'effacement est fait ; seul son inscription a échoué : à signaler, pas à annuler.
        logger.exception("Registre des effacements inaccessible (%s)", log_path())


@event.listens_for(Session, "after_rollback")
def _drop_pending(session: Session) -> None:
    session.info.pop(_PENDING, None)


def read(path: Path | None = None) -> Iterator[Erasure]:
    path = path or log_path()
    if not path.exists():
        return
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            data: dict[str, Any] = json.loads(line)
            yield Erasure(
                kind=data["kind"],
                entity_id=UUID(data["id"]),
                organization_id=UUID(data["org"]) if data.get("org") else None,
                at=datetime.fromisoformat(data["at"]),
            )
