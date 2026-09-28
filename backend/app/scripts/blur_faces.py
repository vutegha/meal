"""Floute les visages des photos déposées avant la mise en place du floutage automatique.

Usage : `uv run python -m app.scripts.blur_faces`. Les originaux ne sont pas modifiés ;
seules les vignettes (affichage et rapports) sont refaites. Relancer ne refait rien.
"""

import asyncio

from sqlalchemy import select

from app.core.db import system_session
from app.documents.storage import get_storage
from app.models import Evidence
from app.services.evidence import UnsupportedFile, render_thumbnail


async def main() -> None:
    storage = get_storage()
    done = 0
    async with system_session() as session:
        photos = await session.scalars(select(Evidence).where(Evidence.thumbnail_key != ""))
        for evidence in photos:
            extra = evidence.extra or {}
            if "faces" in extra:
                continue
            try:
                thumbnail, faces = await asyncio.to_thread(
                    render_thumbnail, await storage.get(evidence.storage_key), True
                )
            except UnsupportedFile:
                continue
            await storage.put(evidence.thumbnail_key, thumbnail, "image/webp")
            evidence.extra = {**extra, "faces": faces, "blur_faces": True}
            done += 1
        await session.commit()
    print(f"{done} photo(s) retraitée(s)")


if __name__ == "__main__":
    asyncio.run(main())
