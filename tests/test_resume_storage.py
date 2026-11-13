import pytest
from cryptography.fernet import Fernet

from jobfinder import resume_storage


def test_resume_storage_encrypts_and_decrypts_bytes(monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_KEY", Fernet.generate_key().decode("ascii"))
    original = b"%PDF-1.7\nprivate resume bytes"
    encrypted = resume_storage.encrypt_resume(original)
    assert encrypted.encode("ascii") != original
    assert resume_storage.decrypt_resume(encrypted) == original
    assert resume_storage.digest_resume(original) == resume_storage.digest_resume(original)


def test_resume_storage_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("RESUME_STORAGE_KEY", raising=False)
    with pytest.raises(resume_storage.ResumeStorageError, match="RESUME_STORAGE_KEY"):
        resume_storage.encrypt_resume(b"resume")


def test_resume_storage_rejects_invalid_key_and_ciphertext(monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_KEY", "invalid")
    with pytest.raises(resume_storage.ResumeStorageError, match="inválida"):
        resume_storage.encrypt_resume(b"resume")
    monkeypatch.setenv("RESUME_STORAGE_KEY", Fernet.generate_key().decode("ascii"))
    with pytest.raises(resume_storage.ResumeStorageError, match="descriptografar"):
        resume_storage.decrypt_resume("not-a-valid-token")


def test_resume_storage_sanitizes_filename_and_content_type():
    assert resume_storage.safe_filename(r"C:\\Users\\Ana\\curriculo.pdf") == "curriculo.pdf"
    assert resume_storage.resume_content_type("curriculo.pdf") == "application/pdf"
    assert resume_storage.resume_content_type("curriculo.docx").endswith("wordprocessingml.document")
    with pytest.raises(resume_storage.ResumeStorageError, match="PDF ou DOCX"):
        resume_storage.resume_content_type("curriculo.exe")
