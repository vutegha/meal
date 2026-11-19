"""Chiffrement des secrets gardés en base (secret de double authentification, contact des
plaignants).

Clé dérivée de SECRET_KEY : changer SECRET_KEY rend ces secrets illisibles, et chaque personne
doit alors réactiver sa double authentification (`app.scripts.revoke_sessions --unreadable-totp`
retire les secrets devenus illisibles).
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"wemeal-secrets:" + get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


# --- Champs personnels chiffrés en base (contact des plaignants) ----------------------------
# Clés dérivées de SECRET_KEY, distinctes de celle des secrets de double authentification.

FIELD_PREFIX = "enc1:"


def _field_fernet() -> Fernet:
    digest = hashlib.sha256(b"wemeal-fields:" + get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_field(value: str) -> str:
    return FIELD_PREFIX + _field_fernet().encrypt(value.encode()).decode() if value else ""


def decrypt_field(value: str) -> str:
    """Texte en clair ; une valeur sans préfixe (saisie avant le chiffrement) est rendue telle
    quelle, une valeur devenue illisible (SECRET_KEY changée) devient vide."""
    if not value.startswith(FIELD_PREFIX):
        return value
    try:
        return _field_fernet().decrypt(value[len(FIELD_PREFIX) :].encode()).decode()
    except InvalidToken:
        return ""


def blind_index(value: str) -> str:
    """Empreinte stable (HMAC) d'une valeur : on la retrouve sans la garder en clair."""
    key = hashlib.sha256(b"wemeal-index:" + get_settings().secret_key.encode()).digest()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:40]


def phone_index(text: str) -> str:
    """Empreinte des 9 derniers chiffres d'un numéro (« +243 99 000-0001 » ou « 0990000001 »
    donnent la même) ; vide s'il n'y a pas de numéro."""
    digits = "".join(c for c in text if c.isdigit())
    return blind_index(digits[-9:]) if len(digits) >= 9 else ""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Codes à usage unique (TOTP, RFC 6238 : 6 chiffres, 30 secondes, SHA-1) ----------------

TOTP_STEP = 30


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def totp_now(secret: str, at: float | None = None) -> str:
    return _code(secret, int((at or time.time()) // TOTP_STEP))


def verify_totp(secret: str, code: str, at: float | None = None) -> bool:
    """Accepte le code de la période courante et des périodes voisines (horloge décalée)."""
    code = code.strip().replace(" ", "")
    counter = int((at or time.time()) // TOTP_STEP)
    return any(hmac.compare_digest(_code(secret, counter + delta), code) for delta in (-1, 0, 1))


def totp_uri(secret: str, email: str, issuer: str) -> str:
    from urllib.parse import quote

    return (
        f"otpauth://totp/{quote(issuer)}:{quote(email)}"
        f"?secret={secret}&issuer={quote(issuer)}&digits=6&period={TOTP_STEP}"
    )
