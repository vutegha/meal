# We MEAL

Application web pour faciliter les activités MEAL (suivi, évaluation, redevabilité et apprentissage) des organisations : déduction du cadre logique, du budget et des indicateurs à partir des documents de projet, génération des Termes de Référence de chaque activité, puis du rapport narratif à partir des éléments collectés sur le terrain.

- Cahier des charges : [docs/prompt-lancement.md](docs/prompt-lancement.md)
- Architecture : [docs/architecture.md](docs/architecture.md)
- Modèle de données : [docs/data-model.md](docs/data-model.md)
- Tickets et avancement : [docs/roadmap.md](docs/roadmap.md)

## Démarrer avec Docker

```bash
cp .env.example .env   # puis renseigner POSTGRES_PASSWORD, SECRET_KEY et MINIO_ROOT_PASSWORD
docker compose up --build
```

L'application est servie sur https://localhost (API sous `/api/v1`, documentation sous `/api/docs`).
Pour charger un projet de démonstration : `docker compose exec api python -m app.scripts.seed`.

## Développement local

Prérequis : Python 3.11+ avec [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16 et Redis.

```bash
# API
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.scripts.seed           # données de démonstration (affiche le mot de passe)
uv run uvicorn app.main:app --reload       # http://localhost:8000/api/docs

# Worker
uv run arq app.workers.settings.WorkerSettings

# Interface
cd ../frontend
npm install
npm run dev                                # http://localhost:5173
```

Variables utiles côté API : `DATABASE_URL` (par défaut `postgresql+asyncpg://meal:meal@localhost:5432/meal`), `REDIS_URL`, `SECRET_KEY`.

## Fonctions d'IA

À la création d'un projet, les documents joints (proposition, cadre logique, budget, chronogramme) sont analysés d'office : l'API Claude en extrait la fiche du projet, le cadre logique, les indicateurs, le budget et le chronogramme des activités, validés par l'utilisateur avant enregistrement. Renseignez `ANTHROPIC_API_KEY` dans `.env` ; sans clé, le reste de l'application fonctionne et l'extraction renvoie une erreur explicite. Le plafond de dépense mensuel par organisation se règle avec `AI_MONTHLY_BUDGET_USD` (50 USD par défaut).

Pour mesurer la qualité du prompt d'extraction (appel réel, quelques centimes) :

```bash
cd backend && uv run python -m app.llm.evals.run
```

## SMS des plaintes et retours

Depuis le registre des plaintes et retours, la personne qui traite un retour peut écrire par SMS au contact enregistré et lire ses réponses dans le même fil. La passerelle se choisit avec `SMS_PROVIDER` :

- `simulated` (par défaut) : aucun SMS ne part, l'envoi est enregistré comme réussi et un bouton permet de simuler la réponse de la personne ;
- `twilio` : renseignez `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` et `SMS_SENDER` (numéro Twilio) ;
- `africastalking` : renseignez `AFRICASTALKING_USERNAME` (`sandbox` pour le bac à sable), `AFRICASTALKING_API_KEY` et, si besoin, `SMS_SENDER`.

Pour recevoir les SMS, choisissez un secret `SMS_WEBHOOK_TOKEN` et déclarez chez le prestataire l'URL `https://<domaine>/api/v1/sms/inbound/<SMS_WEBHOOK_TOKEN>`. Un SMS reçu d'un numéro à qui l'équipe a déjà écrit rejoint l'échange du retour concerné ; un SMS qui commence par le code d'un projet (ex. « RES-NK-01 Le point d'eau est en panne ») crée un nouveau retour dans ce projet, canal SMS, à qualifier. Les autres SMS sont conservés sans être rattachés à une organisation.

## Tests et qualité

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest   # base meal_test requise
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
cd frontend && npm run e2e   # parcours complet dans Chromium ; base meal_e2e requise, lance API (faux modèle IA) et Vite
```
