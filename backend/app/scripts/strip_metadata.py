"""Retire les métadonnées (GPS, appareil, auteur) des photos déposées avant ce traitement.

Usage : `uv run python -m app.scripts.strip_metadata`. La date et la position restent en base.
Relancer ne refait rien : une photo déjà nettoyée garde la même empreinte.
"""

import asyncio
import hashlib

from sqlalchemy import select

from app.core.db import system_session
from app.documents.metadata import strip_metadata
from app.documents.storage import get_storage
from app.models import Evidence
from app.services.evidence import IMAGE_TYPES


async def main() -> None:
    storage = get_storage()
    done = 0
    async with system_session() as session:
        photos = await session.scalars(
            select(Evidence).where(Evidence.content_type.in_(list(IMAGE_TYPES)))
        )
        for evidence in photos:
            data = await storage.get(evidence.storage_key)
            cleaned = await asyncio.to_thread(strip_metadata, data, evidence.content_type)
            if cleaned == data:
                continue
            await storage.put(evidence.storage_key, cleaned, evidence.content_type)
            evidence.sha256 = hashlib.sha256(cleaned).hexdigest()
            evidence.size_bytes = len(cleaned)
            done += 1
        await session.commit()
    print(f"{done} photo(s) nettoyée(s)")


if __name__ == "__main__":
    asyncio.run(main())
