from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


_fernet = Fernet(settings.app_encryption_key)


def encrypt_token(token: str) -> str:
    return _fernet.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(token_encrypted: str) -> str:
    try:
        return _fernet.decrypt(token_encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted token") from exc
