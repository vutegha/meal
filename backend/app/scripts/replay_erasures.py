"""Refait les effacements inscrits au registre, après la restauration d'une sauvegarde.

Usage, une fois la restauration faite (ops/restore.sh) :
    docker compose run --rm api python -m app.scripts.replay_erasures

Une sauvegarde contient les données telles qu'elles étaient le jour où elle a été faite ; les
personnes effacées depuis y figurent encore. Ce script les efface de nouveau. Il peut être lancé
plusieurs fois sans effet de plus : un retour déjà anonymisé, un compte déjà supprimé ou un
espace déjà fermé sont laissés tels quels.
"""

import asyncio
from collections import Counter
from uuid import UUID

from sqlalchemy import delete, select

from app.core.db import system_session
from app.models import FeedbackEntry, FormSubmission, Organization, User
from app.services import accounts, erasures
from app.services.accounts import DELETED_NAME
from app.services.retention import anonymize_feedback


async def replay() -> Counter[str]:
    by_kind: dict[str, set[UUID]] = {}
    for erasure in erasures.read():
        by_kind.setdefault(erasure.kind, set()).add(erasure.entity_id)
    done: Counter[str] = Counter()
    async with system_session() as session:
        session.sync_session.info[erasures.REPLAYING] = True
        if ids := by_kind.get("organization"):
            for org_id in await session.scalars(
                select(Organization.id).where(Organization.id.in_(ids))
            ):
                await accounts.close_organization(session, org_id)
                done["organization"] += 1
        if ids := by_kind.get("feedback"):
            entries = list(
                await session.scalars(
                    select(FeedbackEntry).where(
                        FeedbackEntry.id.in_(ids), FeedbackEntry.anonymized_at.is_(None)
                    )
                )
            )
            await anonymize_feedback(session, entries)
            done["feedback"] += len(entries)
        if ids := by_kind.get("submission"):
            result = await session.execute(delete(FormSubmission).where(FormSubmission.id.in_(ids)))
            done["submission"] += result.rowcount  # type: ignore[attr-defined]
        if ids := by_kind.get("user"):
            for user in await session.scalars(
                select(User).where(User.id.in_(ids), User.full_name != DELETED_NAME)
            ):
                await accounts.delete_account(session, user)
                done["user"] += 1
        await session.commit()
    return done


def main() -> None:
    done = asyncio.run(replay())
    print(
        "Effacements refaits : "
        + (", ".join(f"{kind} {count}" for kind, count in sorted(done.items())) or "aucun")
    )


if __name__ == "__main__":
    main()
