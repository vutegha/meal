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

`admin`, `project_manager`, `meal_officer`, `field_agent`, `finance`, `viewer`. Tous les membres lisent les projets. Ensuite :

| Action | Rôles |
|---|---|
| Gérer l'organisation et ses membres | admin |
| Créer, modifier, supprimer un projet | admin, project_manager |
| Modifier le cadre logique et les indicateurs | admin, project_manager, meal_officer |
| Modifier le budget et saisir les dépenses | admin, project_manager, finance |
| Saisir des valeurs d'indicateurs | admin, project_manager, meal_officer, field_agent |
| Importer des documents, lancer l'IA, rédiger et soumettre des TdR | admin, project_manager, meal_officer |
| Approuver, renvoyer, rouvrir ou supprimer des TdR | admin, project_manager |
| Saisir une exécution, déposer des preuves | admin, project_manager, meal_officer, field_agent |
| Saisir les dépenses réelles d'une exécution | les mêmes, plus finance |
| Supprimer une exécution | admin, project_manager |

## IA

- L'IA propose, un humain valide : l'extraction produit une **proposition** stockée (`ai_proposals`) qu'un planificateur relit, corrige et applique en partie ou rejette. Rien n'est écrit dans le cadre logique sans validation.
- Chaque élément proposé cite un extrait du document. Le serveur vérifie que l'extrait figure bien dans le texte (normalisation des espaces, guillemets et casse) et marque les citations introuvables « à vérifier ».
- Sorties structurées (schémas Pydantic dans `schemas/ai.py`), prompts versionnés dans `llm/prompts/`, cache de prompt sur les documents.
- Chaque appel est journalisé dans `ai_calls` (modèle, jetons, coût estimé, durée, version du prompt). Un plafond mensuel par organisation (`AI_MONTHLY_BUDGET_USD`) bloque les appels au-delà.
- Les modèles sont configurables : `LLM_MODEL_EXTRACTION` (claude-opus-5-5 par défaut), `LLM_MODEL_DRAFTING`, `LLM_MODEL_LIGHT`.
- Les TdR sont rédigés par l'IA (`LLM_MODEL_DRAFTING`) à partir du cadre logique, des indicateurs, des pages de documents les plus pertinentes (recherche plein texte) et des consignes de l'utilisateur. Les informations absentes sont laissées en « [À compléter] » et listées. La section budget est toujours calculée depuis le budget du projet, jamais rédigée par le modèle.
- Le rapport narratif d'une exécution est rédigé à partir de sources numérotées : saisie et notes (S1), TdR, texte des comptes rendus et listes de présence, légendes des photos consenties (P1…). Chaque phrase factuelle renvoie à sa source ; un renvoi vers une source inexistante est remplacé par « [source introuvable] ». Les sections participants et budget sont calculées. Les valeurs d'indicateurs proposées ne sont enregistrées qu'après vérification humaine.
- Un document trop volumineux est refusé avec un message explicite plutôt que tronqué en silence.
- Les tâches longues passent par le worker ARQ ; `JOBS_INLINE=true` les exécute dans la requête (tests, développement).

## Collecte terrain hors ligne

- Le frontend est une PWA installable : l'interface est mise en cache par le service worker (Workbox) et les lectures d'API passent en « réseau d'abord, cache sinon », pour consulter les projets sans connexion. Le cache d'API est vidé à la déconnexion.
- Toute saisie d'exécution et tout dépôt de preuve passe par une file d'envoi en IndexedDB (`frontend/src/lib/outbox.ts`, Dexie). La file est envoyée au démarrage, au retour du réseau et toutes les 30 secondes.
- Chaque élément porte un `client_uuid` créé sur le téléphone. L'API renvoie l'élément existant si elle le reçoit deux fois : une réponse perdue en route ne crée pas de doublon.
- Une saisie refusée par l'API (données invalides) reste visible dans la file avec le message d'erreur, au lieu d'être renvoyée indéfiniment.
- Les photos gardent leur original (accès réservé aux membres) ; la vignette affichée est redressée et ne contient aucune métadonnée. Une photo sans consentement n'est pas reprise dans les rapports.

## Journal d'audit

Chaque écriture passe par `services/audit.py::record` dans la même transaction que la modification : organisation, auteur, action, type et identifiant de l'entité, données utiles. Consultable par les administrateurs.

## État d'avancement

| Étape | Contenu | État |
|---|---|---|
| 1 | Fondations : monorepo, Compose, auth, organisations, rôles, audit, CI | fait |
| 2 | Cadre logique manuel, budget, indicateurs | fait (sauf RLS, voir roadmap) |
| 3 | Import de documents et extraction IA | fait (sauf OCR, voir roadmap) |
| 4 | TdR | fait (sauf modèles par organisation, voir roadmap) |
| 5 | Exécution, collecte PWA hors ligne | fait (sauf floutage automatique, voir roadmap) |
| 6 | Rapport narratif, tableau de bord | fait (sauf tests de bout en bout en CI, voir roadmap) |
| 7 | Agrégation, plaintes, leçons apprises | à faire |
