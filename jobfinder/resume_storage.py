"""Cofre de arquivos de currículo por usuário, cifrados com chave Fernet dedicada."""
import hashlib
import os
from pathlib import PurePath

from cryptography.fernet import Fernet, InvalidToken


class ResumeStorageError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = os.getenv("RESUME_STORAGE_KEY", "").strip()
    if not key:
        raise ResumeStorageError(
            "RESUME_STORAGE_KEY não configurada; armazenamento seguro de currículo indisponível."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ResumeStorageError("RESUME_STORAGE_KEY inválida.") from exc


def safe_filename(filename: str) -> str:
    # Remove caminhos POSIX/Windows e caracteres de controle do nome persistido.
    leaf = str(filename or "curriculo").replace("\\", "/").split("/")[-1]
    leaf = "".join(ch for ch in leaf if ch.isprintable() and ch not in '<>:"|?*')
    leaf = leaf.strip().strip(".")[:255]
    return leaf or "curriculo"


def encrypt_resume(content: bytes) -> str:
    if not content:
        raise ResumeStorageError("O currículo está vazio.")
    return _fernet().encrypt(content).decode("ascii")


def decrypt_resume(token: str) -> bytes:
    try:
        return _fernet().decrypt(token.encode("ascii"))
    except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
        raise ResumeStorageError(
            "Não foi possível descriptografar o currículo; verifique RESUME_STORAGE_KEY."
        ) from exc


def digest_resume(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def resume_content_type(filename: str) -> str:
    suffix = PurePath(safe_filename(filename)).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    raise ResumeStorageError("Somente arquivos PDF ou DOCX podem ser armazenados.")
