"""Cofre de credenciais SMTP por conta usando Fernet.

SMTP_CREDENTIALS_KEY deve conter uma chave Fernet gerada fora do repositório.
Sem chave válida, a aplicação falha fechada: nenhuma senha é armazenada em claro.
"""
import os

from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = os.getenv("SMTP_CREDENTIALS_KEY", "").strip()
    if not key:
        raise CredentialEncryptionError(
            "SMTP_CREDENTIALS_KEY não configurada; armazenamento seguro indisponível."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise CredentialEncryptionError("SMTP_CREDENTIALS_KEY inválida.") from exc


def encrypt_password(password: str) -> str:
    if not password:
        raise CredentialEncryptionError("A senha SMTP não pode ficar vazia.")
    return _fernet().encrypt(password.encode("utf-8")).decode("ascii")


def decrypt_password(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
        raise CredentialEncryptionError(
            "Não foi possível descriptografar a credencial SMTP; verifique a chave configurada."
        ) from exc
