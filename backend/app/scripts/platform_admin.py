"""Accorde (ou retire avec --revoke) l'accès à l'administration de la plateforme.

uv run python -m app.scripts.platform_admin personne@exemple.org
uv run python -m app.scripts.platform_admin personne@exemple.org --revoke
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.core.db import system_session
from app.models import User


async def main(email: str, revoke: bool) -> int:
    async with system_session() as session:
        user = await session.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user is None:
            print(f"Aucun compte pour {email} : la personne doit d'abord s'inscrire.")
            return 1
        user.is_platform_admin = not revoke
        await session.commit()
    state = "retiré à" if revoke else "accordé à"
    print(f"Accès à l'administration de la plateforme {state} {email}.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.email, args.revoke)))
