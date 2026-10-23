# We MEAL

Application web pour faciliter les activités MEAL (suivi, évaluation, redevabilité et apprentissage) des organisations : déduction du cadre logique, du budget et des indicateurs à partir des documents de projet, génération des Termes de Référence de chaque activité, puis du rapport narratif à partir des éléments collectés sur le terrain.

- Cahier des charges : [docs/prompt-lancement.md](docs/prompt-lancement.md)
- Architecture : [docs/architecture.md](docs/architecture.md)
- Modèle de données : [docs/data-model.md](docs/data-model.md)
- Tickets et avancement : [docs/roadmap.md](docs/roadmap.md)

## Démarrer avec Docker

```bash
cp .env.example .env   # puis renseigner POSTGRES_PASSWORD, SECRET_KEY et BACKUP_PASSPHRASE
docker compose up --build
```

Les fichiers importés sont gardés dans le volume Docker `files`. Pour les stocker dans MinIO
(compatible S3) : `STORAGE_BACKEND=s3`, `MINIO_ROOT_PASSWORD` et, MinIO ne publiant plus
d'image sur Docker Hub, une image disponible dans `MINIO_IMAGE`, puis
`docker compose --profile s3 up --build`.

`SECRET_KEY` doit faire au moins 32 caractères aléatoires, sinon l'API refuse de démarrer :
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

L'application est servie sur https://localhost (API sous `/api/v1`). La documentation
`/api/docs` n'est ouverte qu'avec `ENVIRONMENT=development`.
Pour charger un projet de démonstration : `docker compose exec api python -m app.scripts.seed` (le mot de passe du compte `demo@wemeal.org` est affiché).

## Sauvegardes

Le service `backup` sauvegarde chaque jour, à `BACKUP_HOUR` heure UTC, la base et les fichiers
dans `BACKUP_DIR` (`./backups` par défaut). Chaque sauvegarde est chiffrée (AES-256) avec
`BACKUP_PASSPHRASE` et gardée `BACKUP_KEEP_DAYS` jours. Copiez ce dossier hors du serveur, et
gardez la phrase de passe ailleurs : sans elle, la sauvegarde est illisible.

```bash
docker compose run --rm backup now     # une sauvegarde tout de suite
docker compose run --rm backup list    # les sauvegardes présentes
# Restauration (remplace la base et les fichiers)
docker compose stop api worker
docker compose run --rm --entrypoint /ops/restore.sh backup wemeal-AAAAMMJJ-HHMMSS.tar.gpg
docker compose start api worker
```

Testez une restauration au moins une fois par trimestre.

## Données personnelles (RGPD)

- **Réglages par espace** (page *Données personnelles*, administrateurs) : IA activable ou non,
  accusé de réception des SMS avec la phrase d'information, durée de conservation des retours
  clôturés (36 mois par défaut), contact pour exercer ses droits.
- **Purge nocturne** (tâche du `worker`, 3 h UTC) : retours clôturés au-delà de la durée choisie
  anonymisés, SMS non rattachés effacés après 30 jours, liens de réinitialisation et sessions
  expirés après 30 jours, journal des consultations après 365 jours. À la main :
  `docker compose exec api python -m app.scripts.purge`.
- **Photos** : la date et la position sont lues puis retirées du fichier gardé, avec le reste
  des métadonnées (appareil, auteur, logiciel). Pour les photos déposées avant :
  `docker compose exec api python -m app.scripts.strip_metadata`.
- **Demande d'une personne** : recherche par nom, numéro ou e-mail, copie JSON et effacement
  motivé, tracé dans le journal sans les termes recherchés.
- **Comptes** : sessions révocables, double authentification (conseillée aux administrateurs),
  mot de passe oublié par e-mail si `SMTP_HOST` est renseigné, sinon lien remis par un
  administrateur.

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

## Tests et qualité

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest   # base meal_test requise
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
cd frontend && npm run e2e   # parcours complet dans Chromium ; base meal_e2e requise, lance API (faux modèle IA) et Vite
```
