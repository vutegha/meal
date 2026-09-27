# Architecture de We MEAL

Ce document décrit l'architecture cible de l'application et l'état actuel de sa mise en œuvre. Le cahier des charges complet est dans [prompt-lancement.md](prompt-lancement.md) ; le modèle de données dans [data-model.md](data-model.md) ; le découpage en tickets dans [roadmap.md](roadmap.md) ; les décisions dans [adr/](adr/).

## Vue d'ensemble

```
          Navigateur / PWA terrain (React + TS)
                       │  HTTPS (Caddy)
                       ▼
     ┌──────────── API FastAPI (async) ────────────┐
     │ auth · organisations · projets · cadre      │
     │ logique · budget · indicateurs · TdR ·      │
     │ exécutions · rapports · redevabilité        │
     └──────┬───────────────┬───────────────┬──────┘
            │               │               │
     PostgreSQL 16     Redis (file ARQ)   Stockage S3 (MinIO)
     + pgvector             │               photos, pièces, exports
                            ▼
                  Worker ARQ : extraction de documents,
                  indexation, appels IA (Claude),
                  génération DOCX/PDF
```

- **API** (`backend/app`) : FastAPI async, SQLAlchemy 2 async sur asyncpg, validation Pydantic v2. Préfixe `/api/v1`.
- **Worker** (`backend/app/workers`) : ARQ sur Redis. Tout travail long (IA, OCR, exports) passe par une tâche ; l'API renvoie immédiatement un identifiant de tâche et l'interface suit l'avancement.
- **Frontend** (`frontend/`) : React 19, Vite, TanStack Router et Query, Tailwind CSS, i18next (français par défaut).
- **Reverse proxy** : Caddy sert le frontend compilé et relaie `/api` vers l'API, HTTPS automatique en production.

## Organisation du backend

| Dossier | Rôle |
|---|---|
| `core/` | configuration (`pydantic-settings`), base de données, sécurité (mots de passe, JWT) |
| `models/` | modèles SQLAlchemy |
| `schemas/` | schémas Pydantic des entrées/sorties API (et, plus tard, des sorties IA) |
| `api/` | routes par module, dépendances d'authentification et de tenancy |
| `services/` | logique métier indépendante de HTTP (dont le journal d'audit) |
| `llm/` | client IA, prompts versionnés, sélection du modèle (étape 3) |
| `documents/` | extraction, découpage, indexation, génération DOCX/PDF (étapes 3 et 4) |
| `workers/` | configuration et tâches ARQ |

## Multi-tenant

Toutes les ressources métier appartiennent à une organisation et sont exposées sous `/api/v1/orgs/{org_id}/…`. La dépendance `require_membership` (dans `api/deps.py`) vérifie que l'utilisateur authentifié est membre de l'organisation et, si demandé, qu'il a l'un des rôles autorisés. Une requête sur une organisation dont l'utilisateur n'est pas membre renvoie **404** (on ne révèle pas son existence). Voir [ADR 0002](adr/0002-tenancy.md) pour l'ajout de la Row Level Security PostgreSQL.

## Authentification

- Mots de passe hachés en Argon2.
- Jeton d'accès JWT court (15 min par défaut) et jeton de rafraîchissement (7 jours), signés HS256 avec `SECRET_KEY`.
- L'inscription crée l'utilisateur **et** sa première organisation, dont il devient administrateur.
- SSO OIDC (Keycloak) prévu en option plus tard.

## Rôles

`admin`, `project_manager`, `meal_officer`, `field_agent`, `finance`, `viewer`. Les droits fins par module seront définis au fil des étapes ; à l'étape 1 seul `admin` gère l'organisation et ses membres.

## Journal d'audit

Chaque écriture passe par `services/audit.py::record` dans la même transaction que la modification : organisation, auteur, action, type et identifiant de l'entité, données utiles. Consultable par les administrateurs.

## État d'avancement

| Étape | Contenu | État |
|---|---|---|
| 1 | Fondations : monorepo, Compose, auth, organisations, rôles, audit, CI | **en cours (cette PR)** |
| 2 | Cadre logique manuel, budget, indicateurs | à faire |
| 3 | Import de documents et extraction IA | à faire |
| 4 | TdR | à faire |
| 5 | Exécution, collecte PWA hors ligne | à faire |
| 6 | Rapport narratif, tableaux de bord | à faire |
| 7 | Agrégation, plaintes, leçons apprises | à faire |
