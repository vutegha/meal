# ADR 0001 : choix de la stack

- Statut : accepté
- Date : 2026-09-27

## Contexte
L'application traite de longs documents, appelle un modèle d'IA pour des générations de plusieurs dizaines de secondes, produit des documents Word/PDF et doit fonctionner sur le terrain avec une connectivité faible. Elle doit rester peu coûteuse à héberger.

## Décision
- Backend Python + FastAPI async, SQLAlchemy 2 async, Pydantic v2, Alembic.
- PostgreSQL 16 avec pgvector (recherche vectorielle dans la même base), JSONB pour les champs flexibles.
- Redis + ARQ pour les tâches longues.
- Stockage objet compatible S3 (MinIO en auto-hébergé).
- Frontend React 19 + TypeScript + Vite, TanStack Router et Query, Tailwind CSS, i18next ; PWA (Workbox, Dexie) pour le terrain.
- IA : API Anthropic (Claude) derrière une couche `llm/` interchangeable.
- Déploiement Docker Compose + Caddy.

## Conséquences
- Un seul langage côté serveur couvre API, IA et traitement de documents.
- Python 3.12 dans les images Docker ; le code reste compatible 3.11.
- Voir le détail et les alternatives écartées dans [prompt-lancement.md](../prompt-lancement.md#4-stack-technique-recommandée).
