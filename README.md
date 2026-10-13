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

À la création d'un projet, les documents joints (proposition, cadre logique, budget, chronogramme) sont analysés d'office : l'API Claude en extrait la fiche du projet, le cadre logique, les indicateurs, le budget et le chronogramme des activités, validés par l'utilisateur avant enregistrement. Renseignez `ANTHROPIC_API_KEY` dans `.env` ; sans clé, le reste de l'application fonctionne et l'extraction renvoie une erreur explicite. Le plafond de dépense mensuel de chaque organisation dépend de sa formule (voir ci-dessous) ; `AI_MONTHLY_BUDGET_USD` ajoute un plafond commun à toutes (0 par défaut : celui de la formule seulement).

Pour mesurer la qualité du prompt d'extraction (appel réel, quelques centimes) :

```bash
cd backend && uv run python -m app.llm.evals.run
```

## SMS et WhatsApp des plaintes et retours

Depuis le registre des plaintes et retours, la personne qui traite un retour peut écrire par SMS ou par WhatsApp au contact enregistré et lire ses réponses dans le même fil (on répond par défaut sur le canal du dernier message reçu). La passerelle SMS se choisit avec `SMS_PROVIDER` :

- `simulated` (par défaut) : aucun SMS ne part, l'envoi est enregistré comme réussi et un bouton permet de simuler la réponse de la personne ;
- `twilio` : renseignez `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` et `SMS_SENDER` (numéro Twilio) ;
- `africastalking` : renseignez `AFRICASTALKING_USERNAME` (`sandbox` pour le bac à sable), `AFRICASTALKING_API_KEY` et, si besoin, `SMS_SENDER`.

La passerelle WhatsApp se choisit avec `WHATSAPP_PROVIDER` :

- `simulated` (par défaut) : aucun message ne part ;
- `twilio` : `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` et `TWILIO_WHATSAPP_SENDER` (numéro WhatsApp Twilio, `+14155238886` pour le bac à sable) ;
- `meta` (WhatsApp Cloud API) : `META_WHATSAPP_TOKEN`, `META_WHATSAPP_PHONE_NUMBER_ID` et, conseillé, `META_APP_SECRET` pour contrôler la signature des notifications. Hors des 24 h qui suivent le dernier message de la personne, Meta n'accepte qu'un modèle de message approuvé : l'envoi libre est alors refusé et l'erreur s'affiche dans le fil.

Pour recevoir les SMS, choisissez un secret `SMS_WEBHOOK_TOKEN` et déclarez chez le prestataire l'URL `https://<domaine>/api/v1/sms/inbound/<SMS_WEBHOOK_TOKEN>` ; pour WhatsApp, `https://<domaine>/api/v1/whatsapp/inbound/<SMS_WEBHOOK_TOKEN>` (chez Meta, le jeton de vérification est ce même secret). Un SMS ou message WhatsApp reçu d'un numéro à qui l'équipe a déjà écrit rejoint l'échange du retour concerné ; un SMS qui commence par le code d'un projet (ex. « RES-NK-01 Le point d'eau est en panne ») crée un nouveau retour dans ce projet, canal SMS, à qualifier. Les autres SMS sont conservés sans être rattachés à une organisation.

## Formules et administration des abonnements

Trois formules, définies dans `backend/app/services/billing.py` (tarifs indicatifs) : **Solo** (compte individuel), **Équipe** et **Institution** (organisations). Équipe ajoute les formulaires de collecte personnalisés, les rapports périodiques, les membres et rôles, les modèles, les leçons de l'organisation et le journal d'audit ; Institution ajoute les SMS et WhatsApp avec les communautés. L'API refuse avec 402 ce que la formule n'ouvre pas, l'interface affiche à la place une invitation à changer de formule. Le détail est dans `docs/architecture.md`.

L'équipe qui exploite la plateforme gère les abonnements et les paiements de tous les espaces sur `/admin`.
- Elle confirme les virements et envois mobile money annoncés par les clients.
- Elle enregistre un paiement reçu hors de l'application, ou rembourse un paiement.
- Elle ajuste une formule, une échéance ou des crédits.

Chaque paiement encaissé reçoit un reçu PDF numéroté, et chaque changement est inscrit au journal de l'espace. Les coordonnées de paiement affichées aux clients se règlent avec `PAYMENT_INSTRUCTIONS`. Pour y donner accès à un compte existant :

```bash
cd backend
uv run python -m app.scripts.platform_admin personne@exemple.org            # --revoke pour retirer
```

## Tests et qualité

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest   # base meal_test requise
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
cd frontend && npm run e2e   # parcours complet dans Chromium ; base meal_e2e requise, lance API (faux modèle IA) et Vite
```
