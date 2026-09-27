# We MEAL

Application web pour faciliter les activités MEAL (suivi, évaluation, redevabilité et apprentissage) des organisations : déduction du cadre logique, du budget et des indicateurs à partir des documents de projet, génération des Termes de Référence de chaque activité, puis du rapport narratif à partir des éléments collectés sur le terrain.

- Cahier des charges : [docs/prompt-lancement.md](docs/prompt-lancement.md)
- Architecture : [docs/architecture.md](docs/architecture.md)
- Modèle de données : [docs/data-model.md](docs/data-model.md)
- Tickets et avancement : [docs/roadmap.md](docs/roadmap.md)

## Démarrer avec Docker

```bash
cp .env.example .env   # puis renseigner SECRET_KEY et MINIO_ROOT_PASSWORD
docker compose up --build
```

L'application est servie sur https://localhost (API sous `/api/v1`, documentation sous `/api/docs`).

## Développement local

Prérequis : Python 3.11+ avec [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16 et Redis.

```bash
# API
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload       # http://localhost:8000/api/docs

# Worker
uv run arq app.workers.settings.WorkerSettings

# Interface
cd ../frontend
npm install
npm run dev                                # http://localhost:5173
```

Variables utiles côté API : `DATABASE_URL` (par défaut `postgresql+asyncpg://meal:meal@localhost:5432/meal`), `REDIS_URL`, `SECRET_KEY`.

## Tests et qualité

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest   # base meal_test requise
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```
