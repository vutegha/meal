"""Données de démonstration : une organisation, un projet type et son cadre logique.

Usage : uv run python -m app.scripts.seed
Le mot de passe du compte de démonstration est lu dans DEMO_PASSWORD, ou généré et affiché.
"""

import asyncio
import os
import secrets
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import system_session
from app.core.security import hash_password
from app.models import (
    Aggregation,
    BudgetLine,
    Expense,
    Indicator,
    IndicatorValue,
    LogframeNode,
    NodeLevel,
    Project,
    ProjectStatus,
    User,
)
from app.services.organizations import create_organization

DEMO_EMAIL = "demo@wemeal.org"

# (niveau, code, intitulé, enfants)
NodeSpec = tuple[NodeLevel, str, str, list["NodeSpec"]]

LOGFRAME: NodeSpec = (
    NodeLevel.GOAL,
    "OG",
    "Contribuer à la résilience des ménages vulnérables du Nord-Kivu",
    [
        (
            NodeLevel.OUTCOME,
            "OS1",
            "Les ménages ciblés augmentent et diversifient leurs revenus",
            [
                (
                    NodeLevel.OUTPUT,
                    "R1.1",
                    "30 associations villageoises d'épargne et de crédit (AVEC) fonctionnent",
                    [
                        (NodeLevel.ACTIVITY, "A1.1.1", "Former les membres des AVEC", []),
                        (NodeLevel.ACTIVITY, "A1.1.2", "Doter les AVEC en kits de démarrage", []),
                    ],
                ),
                (
                    NodeLevel.OUTPUT,
                    "R1.2",
                    "Les jeunes formés lancent une activité génératrice de revenus",
                    [
                        (
                            NodeLevel.ACTIVITY,
                            "A1.2.1",
                            "Organiser des formations professionnelles",
                            [],
                        ),
                    ],
                ),
            ],
        ),
        (
            NodeLevel.OUTCOME,
            "OS2",
            "Les communautés disposent de mécanismes de redevabilité efficaces",
            [
                (
                    NodeLevel.OUTPUT,
                    "R2.1",
                    "Un mécanisme de plaintes et retours est opérationnel",
                    [
                        (
                            NodeLevel.ACTIVITY,
                            "A2.1.1",
                            "Mettre en place des comités de plaintes",
                            [],
                        ),
                    ],
                ),
            ],
        ),
    ],
)


async def seed(session: AsyncSession) -> str | None:
    if await session.scalar(select(User.id).where(User.email == DEMO_EMAIL)):
        return None
    password = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(9)
    user = User(
        email=DEMO_EMAIL, full_name="Compte de démonstration", password_hash=hash_password(password)
    )
    session.add(user)
    await session.flush()
    org = await create_organization(session, name="ONG Démo Kivu", owner=user)

    project = Project(
        organization_id=org.id,
        code="RES-NK-01",
        title="Résilience économique des ménages au Nord-Kivu",
        description="Projet de démonstration de We MEAL.",
        donor="Bailleur de démonstration",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 12, 31),
        currency="USD",
        status=ProjectStatus.ACTIVE,
        zones=["Goma", "Rutshuru", "Masisi"],
        target_groups=["Ménages vulnérables", "Jeunes de 18 à 35 ans"],
    )
    session.add(project)
    await session.flush()

    nodes: dict[str, LogframeNode] = {}

    async def add(spec: NodeSpec, parent: LogframeNode | None, position: int) -> None:
        level, code, title, children = spec
        node = LogframeNode(
            organization_id=org.id,
            project_id=project.id,
            parent_id=parent.id if parent else None,
            level=level,
            code=code,
            title=title,
            position=position,
        )
        session.add(node)
        await session.flush()
        nodes[code] = node
        for index, child in enumerate(children):
            await add(child, node, index)

    await add(LOGFRAME, None, 0)

    budget = [
        ("A1.1.1", "1.1", "Formateurs AVEC", "Personnel", 4, "mois", 800, 6),
        (
            "A1.1.1",
            "1.2",
            "Collations des sessions de formation",
            "Activités",
            30,
            "session",
            60,
            4,
        ),
        ("A1.1.2", "2.1", "Kits de démarrage AVEC", "Équipements", 30, "kit", 120, 1),
        ("A1.2.1", "2.2", "Formations professionnelles", "Activités", 150, "jeune", 90, 1),
        ("A2.1.1", "3.1", "Ateliers communautaires", "Activités", 12, "atelier", 250, 1),
        (None, "9.1", "Loyer du bureau de Goma", "Support", 1, "mois", 900, 24),
    ]
    lines = {}
    for activity, donor_code, label, category, qty, unit, cost, freq in budget:
        line = BudgetLine(
            organization_id=org.id,
            project_id=project.id,
            activity_id=nodes[activity].id if activity else None,
            donor_line_code=donor_code,
            label=label,
            category=category,
            quantity=Decimal(qty),
            unit=unit,
            unit_cost=Decimal(cost),
            frequency=Decimal(freq),
        )
        session.add(line)
        lines[donor_code] = line
    await session.flush()
    for donor_code, amount, day in [
        ("1.1", 9600, date(2026, 6, 30)),
        ("1.2", 4100, date(2026, 5, 15)),
        ("2.1", 3600, date(2026, 4, 2)),
        ("9.1", 8100, date(2026, 9, 1)),
    ]:
        session.add(
            Expense(
                organization_id=org.id,
                budget_line_id=lines[donor_code].id,
                amount=Decimal(amount),
                spent_on=day,
                reference=f"FAC-{donor_code}",
            )
        )

    indicators = [
        (
            "OS1",
            "I1",
            "Revenu mensuel moyen des ménages ciblés",
            "USD",
            38,
            55,
            Aggregation.LATEST,
            [],
            "Enquête de base et enquêtes de suivi",
            [(2026, 6, 44)],
        ),
        (
            "R1.1",
            "I2",
            "Nombre de membres d'AVEC formés",
            "personnes",
            0,
            600,
            Aggregation.SUM,
            ["sexe"],
            "Listes de présence",
            [(2026, 3, 210), (2026, 6, 180)],
        ),
        (
            "R1.2",
            "I3",
            "Nombre de jeunes ayant lancé une AGR",
            "jeunes",
            0,
            120,
            Aggregation.SUM,
            ["sexe", "âge"],
            "Fiches de suivi des AGR",
            [],
        ),
        (
            "OS2",
            "I4",
            "Pourcentage de plaintes traitées dans les délais",
            "%",
            0,
            90,
            Aggregation.LATEST,
            [],
            "Registre des plaintes",
            [(2026, 6, 72)],
        ),
    ]
    for node_code, code, name, unit, base, target, agg, dis, source, values in indicators:
        indicator = Indicator(
            organization_id=org.id,
            project_id=project.id,
            node_id=nodes[node_code].id,
            code=code,
            name=name,
            unit=unit,
            baseline=Decimal(base),
            target=Decimal(target),
            aggregation=agg,
            disaggregations=dis,
            source_of_verification=source,
            frequency="trimestrielle",
        )
        session.add(indicator)
        await session.flush()
        for year, month, value in values:
            session.add(
                IndicatorValue(
                    organization_id=org.id,
                    indicator_id=indicator.id,
                    period_start=date(year, month - 2, 1),
                    period_end=date(year, month, 28),
                    value=Decimal(value),
                    source=source,
                    recorded_by=user.id,
                )
            )
    await session.commit()
    return password


async def main() -> None:
    async with system_session() as session:
        password = await seed(session)
    if password is None:
        print(f"Le compte {DEMO_EMAIL} existe déjà : rien à faire.")
    else:
        print(f"Compte de démonstration : {DEMO_EMAIL} / {password}")


if __name__ == "__main__":
    asyncio.run(main())
