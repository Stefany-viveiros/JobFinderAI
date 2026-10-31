from dataclasses import dataclass
import os
from dotenv import load_dotenv

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
