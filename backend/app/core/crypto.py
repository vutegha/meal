"""Chiffrement des secrets gardés en base (secret de double authentification).

Clé dérivée de SECRET_KEY : changer SECRET_KEY rend ces secrets illisibles, et chaque personne
doit alors réactiver sa double authentification.
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
