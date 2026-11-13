from dataclasses import dataclass
import os
from dotenv import load_dotenv
from urllib.parse import urlsplit

load_dotenv()


def _read_bool(name: str, default: str) -> bool:
    value = os.getenv(name, default).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} deve ser true ou false.")
    return value == "true"


def validate_session_configuration(app_env: str, session_hours: int, cookie_secure: bool) -> None:
    environment = (app_env or "").strip().lower()
    if environment not in {"development", "test", "staging", "production"}:
        raise ValueError("APP_ENV deve ser development, test, staging ou production.")
    if not 1 <= int(session_hours) <= 720:
        raise ValueError("SESSION_HOURS deve estar entre 1 e 720 horas.")
    if environment in {"staging", "production"} and not cookie_secure:
        raise ValueError("COOKIE_SECURE=true é obrigatório em staging e production.")


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
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    session_hours: int = int(os.getenv("SESSION_HOURS", "24"))
    cookie_secure: bool = _read_bool("COOKIE_SECURE", "true")

    @property
    def smtp_ready(self) -> bool:
        return all([self.smtp_host, self.smtp_port, self.smtp_from, self.smtp_to])

    @property
    def smtp_can_send_applications(self) -> bool:
        """Envio de candidaturas exige remetente e login; SMTP_TO (lembretes) é irrelevante."""
        return all([self.smtp_host, self.smtp_port, self.smtp_from,
                    self.smtp_username, self.smtp_password])


settings = Settings()
validate_session_configuration(settings.app_env, settings.session_hours, settings.cookie_secure)


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
        try:
            parsed.port  # força validação de portas, inclusive valores fora do intervalo
        except ValueError as exc:
            raise ValueError(f"Porta inválida na origem CORS: {origin!r}.") from exc
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
