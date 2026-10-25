from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valeurs d'exemple refusées en production (config.py et .env.example).
PLACEHOLDER_SECRETS = {"change-me-in-production", "remplacer-par-une-longue-valeur-aleatoire"}
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "We MEAL"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://meal:meal@localhost:5432/meal"
    # Rôle non propriétaire endossé par l'API pour que la Row Level Security s'applique.
    # Vide : pas de changement de rôle (déconseillé hors développement).
    db_app_role: str = "meal_app"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]
    # Connexion : au-delà de N échecs dans la fenêtre, refus (429) jusqu'à sa fin. Un compteur
    # par adresse e-mail, un autre par adresse IP. "redis" (partagé) ou "memory".
    login_max_failures: int = 5
    login_max_failures_per_ip: int = 20
    login_window_minutes: int = 15
    login_rate_limit_storage: str = "redis"
    # Lien de réinitialisation du mot de passe : valable 24 heures, à usage unique.
    password_reset_hours: int = 24
    # Adresse publique de l'interface, pour les liens envoyés par e-mail.
    public_url: str = "https://localhost"
    # E-mails (mot de passe oublié). Sans SMTP_HOST, aucun e-mail ne part : un administrateur
    # de l'organisation crée alors le lien depuis la page Membres.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Stockage des fichiers : "local" (dossier) ou "s3" (MinIO, S3, R2…)
    storage_backend: str = "local"
    storage_local_path: str = "./data/files"
    s3_endpoint: str | None = None
    s3_bucket: str = "wemeal"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    max_upload_mb: int = 25
    # Enregistrements audio et vidéo déposés comme preuves.
    max_media_mb: int = 200

    # Tâches longues : exécutées dans la requête (développement, tests) ou par le worker ARQ
    jobs_inline: bool = False

    # IA
    anthropic_api_key: str | None = None
    llm_model_extraction: str = "claude-opus-5-5"
    llm_model_drafting: str = "claude-sonnet-5"
    llm_model_light: str = "claude-haiku-4-5"
    # Lecture des pages scannées (images) : un modèle capable de lire l'écriture manuscrite.
    llm_model_ocr: str = "claude-sonnet-5"
    ocr_max_pages: int = 40
    # Plafond mensuel des dépenses IA de chaque formule (services/billing.py). Ce réglage ajoute
    # un plafond commun à toutes les organisations, en USD (0 = seulement celui de la formule).
    ai_monthly_budget_usd: float = 0.0
    # Recherche sémantique : embeddings Voyage AI (multilingues). Sans clé, plein texte seul.
    voyage_api_key: str | None = None
    embeddings_model: str = "voyage-3.5"
    # Pages vectorisées au plus par recherche (les suivantes le seront aux recherches d'après).
    embeddings_batch_pages: int = 256
    # Taille maximale du texte envoyé en une fois (au-delà : erreur explicite, pas de troncature)
    llm_max_document_chars: int = 2_000_000

    # SMS de la redevabilité : "simulated" (aucun envoi réel), "twilio" ou "africastalking".
    # Coordonnées affichées à qui choisit de payer par virement ou mobile money ; l'équipe de la
    # plateforme confirme ensuite chaque paiement reçu depuis /admin. Vide : texte indicatif.
    payment_instructions: str = ""
    sms_provider: str = "simulated"
    # Numéro ou identifiant d'expéditeur affiché au destinataire.
    sms_sender: str = ""
    # Secret inclus dans l'URL de réception à déclarer chez le prestataire :
    # /api/v1/sms/inbound/<SMS_WEBHOOK_TOKEN>. Vide : la réception est désactivée.
    sms_webhook_token: str = ""
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    africastalking_username: str | None = None
    africastalking_api_key: str | None = None
    # WhatsApp : "simulated" (aucun envoi réel), "twilio" ou "meta" (WhatsApp Cloud API).
    # Réception : /api/v1/whatsapp/inbound/<SMS_WEBHOOK_TOKEN> (même secret que les SMS).
    whatsapp_provider: str = "simulated"
    # Numéro WhatsApp Twilio, ex. +14155238886 (bac à sable).
    twilio_whatsapp_sender: str = ""
    meta_whatsapp_token: str | None = None
    meta_whatsapp_phone_number_id: str | None = None
    # Secret de l'application Meta : contrôle de la signature des notifications reçues.
    meta_app_secret: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _strong_secret(self) -> Self:
        weak = self.secret_key in PLACEHOLDER_SECRETS or len(self.secret_key) < MIN_SECRET_LENGTH
        if self.is_production and weak:
            raise ValueError(
                f"SECRET_KEY doit être une valeur aléatoire d'au moins {MIN_SECRET_LENGTH} "
                'caractères. Exemple : python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
