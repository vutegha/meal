"""Envoi d'e-mails par SMTP (STARTTLS). Sans SMTP_HOST configuré, rien ne part."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(get_settings().smtp_host)


def _send(message: EmailMessage) -> None:
    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def send(to: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not enabled():
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        await asyncio.to_thread(_send, message)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("Échec de l'envoi d'un e-mail")
        return False
