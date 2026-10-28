"""Normalização de URLs, chaves de deduplicação e filtro de nível/área (estágio e júnior)."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .matching import normalize

TRACKING_PREFIXES = ("utm_", "ref", "fbclid", "gclid", "mc_", "source", "src")
UNKNOWN_COMPANY = "empresa nao informada"


def normalize_url(url: str) -> str:
    """Forma canônica para comparar links: sem fragmento, sem parâmetros de rastreio e sem '/' final."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith(TRACKING_PREFIXES)]
    cleaned = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"),
                          urlencode(query), ""))
    return cleaned.lower()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize(value)).strip()


LEGAL_SUFFIXES = {"ltda", "sa", "s", "a", "inc", "llc", "gmbh", "eireli", "me", "epp", "corp", "co", "ag", "ltd"}


def _company_slug(company: str) -> str:
    words = _slug(company).split()
    while len(words) > 1 and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def dedupe_key(title: str, company: str) -> str | None:
    """Detecta a mesma vaga publicada em fontes diferentes. Sem empresa conhecida não há chave
    (evita fundir vagas de empresas distintas com o mesmo título)."""
    company_slug = _company_slug(company)
    title_slug = _slug(title)
    if not title_slug or not company_slug or company_slug == UNKNOWN_COMPANY:
        return None
    return f"{title_slug}|{company_slug}"


# Os padrões abaixo rodam sobre texto normalizado (minúsculo e sem acentos).
SENIOR_RE = re.compile(
    r"\b(senior|sr|pleno|pl|mid[- ]?level|lead|staff|principal|head|manager|gerente|"
    r"coordenador|coordenadora|especialista|specialist|architect|arquiteto|diretor|director)\b")
INTERN_RE = re.compile(r"(estagi|\bintern\b|\binterns\b|internship|working student|werkstudent|praktikum)")
JUNIOR_RE = re.compile(r"(\bjunior\b|\bjr\b|entry[- ]level|\bgraduate\b|\btrainee\b)")
TECH_RE = re.compile(
    r"(software|developer|desenvolv|programador|programacao|engenheir[oa] de (software|dados)|"
    r"front[- ]?end|back[- ]?end|full[- ]?stack|\bweb\b|\bpython\b|javascript|typescript|\bphp\b|"
    r"\breact\b|node\.?js|\bapi\b|mobile|android|\bios\b|flutter|"
    r"\bdados\b|\bdata\b|machine learning|\bia\b|\bai\b|inteligencia artificial|automacao|"
    r"\bqa\b|devops|\bti\b|tecnologia|sistemas|informatica)")
# 'engineer' sozinho é amplo demais: descarta engenharias não relacionadas a software.
NON_TECH_ENGINEER_RE = re.compile(r"(sales|customer|support|mechanical|civil|chemical|electrical|"
                                  r"manufacturing|hardware|field|solutions) engineer")


def detect_level(title: str, description: str = "", job_type: str = "") -> str:
    """Retorna 'estagio', 'junior' ou 'outro'. Decide pelo título/tipo; descrição só por frases claras."""
    title_n = normalize(title)
    head = f"{title_n} {normalize(job_type)}"
    if INTERN_RE.search(head):
        return "estagio"
    if SENIOR_RE.search(title_n):
        return "outro"
    if JUNIOR_RE.search(head):
        return "junior"
    intro = normalize(str(description or "")[:400])
    if re.search(r"(vaga de estagio|estagio em|internship position)", intro):
        return "estagio"
    if re.search(r"(vaga junior|junior position)", intro):
        return "junior"
    return "outro"


def is_tech_role(title: str, description: str = "") -> bool:
    """Área de tecnologia decidida pelo TÍTULO. A descrição não entra: textos de vagas de produção,
    jurídico etc. citam 'sistemas', 'TI' e 'data' de passagem e geravam falsos positivos."""
    title_n = normalize(title)
    if NON_TECH_ENGINEER_RE.search(title_n):
        return False
    return bool(TECH_RE.search(title_n))


def classify_level(title: str, description: str = "", job_type: str = "") -> str:
    """Valor gravado em Job.level: 'estagio'/'junior' somente se a vaga for de tecnologia; senão 'outro'."""
    level = detect_level(title, description, job_type)
    return level if level != "outro" and is_tech_role(title, description) else "outro"


def is_target_job(item: dict) -> bool:
    """Estágio ou júnior na área de tecnologia."""
    return classify_level(item.get("title"), item.get("description"), item.get("job_type")) != "outro"
