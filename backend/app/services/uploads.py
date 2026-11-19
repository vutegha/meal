"""Envoi par morceaux des preuves lourdes (vidéos, audios), avec reprise après coupure.

Sur une connexion de terrain, un fichier de 25 Mo envoyé d'un bloc repart de zéro à chaque
coupure. Le téléphone envoie donc des morceaux numérotés par leur position (`Content-Range`) ;
le serveur les ajoute à un fichier partiel et dit où il en est. Après une coupure, l'envoi
reprend là où il s'était arrêté. Une fois complet, le fichier partiel devient la preuve.

Les fichiers partiels sont rangés par organisation et par personne : nul ne peut compléter
l'envoi d'un autre. Ceux abandonnés depuis plus de `STALE_DAYS` jours sont effacés par la purge
quotidienne.
"""

import os
import re
import time
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings

STALE_DAYS = 2
# Taille maximale d'un morceau : assez petit pour passer sur un réseau instable.
MAX_CHUNK_BYTES = 4 * 1024 * 1024
_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class RangeError(ValueError):
    """Morceau hors séquence ou mal décrit ; `received` dit où reprendre."""

    def __init__(self, message: str, received: int) -> None:
        super().__init__(message)
        self.received = received


def _root() -> Path:
    return Path(get_settings().storage_local_path) / "_envois"


def part_path(org_id: UUID, user_id: UUID, upload_id: UUID) -> Path:
    return _root() / str(org_id) / str(user_id) / f"{upload_id}.part"


def received(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def parse_range(header: str) -> tuple[int, int, int]:
    match = _RANGE.match(header.strip())
    if not match:
        raise RangeError("En-tête Content-Range attendu : bytes début-fin/total", 0)
    start, end, total = (int(group) for group in match.groups())
    if end < start or end >= total:
        raise RangeError("Content-Range incohérent", 0)
    return start, end, total


def append(path: Path, start: int, chunk: bytes, total: int, limit: int) -> int:
    """Ajoute un morceau à sa place ; renvoie le nombre d'octets reçus.

    Un morceau déjà reçu (renvoyé après une coupure) est ignoré ; un morceau qui laisserait un
    trou est refusé avec la position attendue.
    """
    if total > limit:
        raise RangeError("Fichier trop volumineux", 0)
    if len(chunk) > MAX_CHUNK_BYTES:
        raise RangeError("Morceau trop gros", received(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    have = received(path)
    if start + len(chunk) <= have:
        return have
    if start > have:
        raise RangeError(f"Morceau attendu à partir de l'octet {have}", have)
    with path.open("ab") as handle:
        handle.write(chunk[have - start :])
    return received(path)


def purge_stale(now: float | None = None) -> int:
    """Efface les envois partiels abandonnés ; renvoie leur nombre."""
    now = now or time.time()
    root = _root()
    if not root.exists():
        return 0
    count = 0
    for path in root.rglob("*.part"):
        if now - path.stat().st_mtime > STALE_DAYS * 86400:
            path.unlink(missing_ok=True)
            count += 1
    for directory in sorted(root.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            os.rmdir(directory)
    return count
