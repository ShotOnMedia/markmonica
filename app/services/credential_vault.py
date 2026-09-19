from cryptography.fernet import Fernet, InvalidToken
from functools import lru_cache
from app.settings import settings

PREFIX = "enc:v1:"

@lru_cache
def _fernet() -> Fernet:
    if not settings.payment_credentials_encryption_key:
        raise RuntimeError("PAYMENT_CREDENTIALS_ENCRYPTION_KEY is not configured.")
    return Fernet(settings.payment_credentials_encryption_key.encode("ascii"))

def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")

def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt payment provider credential.") from exc

def secret_is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(PREFIX))
