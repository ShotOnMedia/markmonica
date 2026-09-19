from cryptography.fernet import Fernet
from app.services import credential_vault

def test_payment_secret_round_trip(monkeypatch):
    key=Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(credential_vault.settings,"payment_credentials_encryption_key",key)
    credential_vault._fernet.cache_clear()
    encrypted=credential_vault.encrypt_secret("super-secret")
    assert encrypted.startswith("enc:v1:")
    assert "super-secret" not in encrypted
    assert credential_vault.decrypt_secret(encrypted)=="super-secret"

def test_plaintext_legacy_secret_can_be_read():
    assert credential_vault.decrypt_secret("legacy-secret")=="legacy-secret"
