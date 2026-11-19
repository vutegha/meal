"""En cas de fuite de données ou de compte compromis : ferme toutes les sessions ouvertes.

Usage : `uv run python -m app.scripts.revoke_sessions` (tout le monde) ou
`uv run python -m app.scripts.revoke_sessions personne@ong.org` (une personne). Chacun doit se
reconnecter ; les jetons déjà copiés ne servent plus. Après un changement de SECRET_KEY, ajouter
`--unreadable-totp` : les secrets de double authentification devenus illisibles sont retirés,
et ces personnes la réactivent à leur prochaine connexion.
"""

import asyncio
import sys

from sqlalchemy import delete, select

from app.core import crypto
from app.core.db import system_session
from app.models import User, UserSession


async def main(args: list[str]) -> None:
    reset_totp = "--unreadable-totp" in args
    emails = [a.lower() for a in args if not a.startswith("--")]
    async with system_session() as session:
        users = select(User.id)
        if emails:
            users = users.where(User.email.in_(emails))
        result = await session.execute(delete(UserSession).where(UserSession.user_id.in_(users)))
        cleared = 0
        if reset_totp:
            for user in await session.scalars(select(User).where(User.totp_secret.is_not(None))):
                if user.totp_secret and crypto.decrypt(user.totp_secret) is None:
                    user.totp_secret = None
                    user.totp_enabled_at = None
                    cleared += 1
        await session.commit()
    closed = result.rowcount  # type: ignore[attr-defined]
    print(f"{closed} session(s) fermée(s), {cleared} double authentification(s) retirée(s)")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
