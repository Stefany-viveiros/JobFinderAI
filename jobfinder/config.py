from dataclasses import dataclass
import os
from dotenv import load_dotenv
from urllib.parse import urlsplit

load_dotenv()


@dataclass(frozen=True)
class Settings:
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    smtp_to: str = os.getenv("SMTP_TO", "")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    timezone: str = os.getenv("TIMEZONE", "America/Sao_Paulo")
    # Caminho opcional de um PDF do currículo a anexar em candidaturas por e-mail.
    # O arquivo fica FORA do repositório; nunca versione currículos.
    cv_path: str = os.getenv("CV_PATH", "")
    # Credenciais Gemini ficam somente no ambiente; nunca versionar a chave.
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    @property
    def smtp_ready(self) -> bool:
        return all([self.smtp_host, self.smtp_port, self.smtp_from, self.smtp_to])

    @property
    def smtp_can_send_applications(self) -> bool:
        """Envio de candidaturas exige remetente e login; SMTP_TO (lembretes) é irrelevante."""
        return all([self.smtp_host, self.smtp_port, self.smtp_from,
                    self.smtp_username, self.smtp_password])


settings = Settings()


def parse_cors_origins(raw: str) -> list[str]:
    """Valida origens CORS explícitas; nunca combina wildcard com credenciais."""
    origins = [item.strip().rstrip("/") for item in (raw or "").split(",") if item.strip()]
    if not origins:
        raise ValueError("CORS_ORIGINS precisa conter ao menos uma origem explícita.")
    if "*" in origins:
        raise ValueError("CORS_ORIGINS não aceita wildcard quando credenciais/cookies estão habilitados.")

    validated = []
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"Origem CORS inválida: {origin!r}. Informe somente esquema e host, sem caminho.")
        if parsed.scheme == "http" and parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Origens CORS HTTP são permitidas somente para desenvolvimento local; use HTTPS.")
        normalized = f"{parsed.scheme}://{parsed.netloc}".lower()
        if normalized not in validated:
            validated.append(normalized)
    return validated
