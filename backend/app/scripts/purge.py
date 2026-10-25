"""Applique les durées de conservation des données personnelles (services/retention.py).

Usage : `uv run python -m app.scripts.purge`. Le worker le fait chaque nuit à 3 h (UTC).
"""

import asyncio

from app.core.db import system_session
from app.services.retention import purge


async def main() -> None:
    async with system_session() as session:
        counts = await purge(session)
        await session.commit()
    print(counts)


if __name__ == "__main__":
    asyncio.run(main())
