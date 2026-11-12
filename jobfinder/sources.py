"""Public job feeds. Source availability and terms can change; failures are isolated."""

import hashlib
import re
import threading
import time
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


TIMEOUT = 18

_JOBICY_CACHE_TTL = 60 * 60
_JOBICY_CACHE = {"expires_at": 0.0, "items": None}
_JOBICY_CACHE_LOCK = threading.Lock()

HEADERS = {
    "User-Agent": "JobFinderAI/1.0 (personal job-search tool)"
}


def _is_safe_job_url(value: str) -> bool:
    """Aceita apenas URLs web absolutas, sem credenciais ou caracteres de controle."""
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if any(ord(char) < 32 or char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _digest(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()[:24]


def fetch_arbeitnow():
    response = requests.get(
        "https://www.arbeitnow.com/api/job-board-api",
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    items = response.json().get("data", [])
    results = []

    for job in items:
        url = job.get("url") or ""
        if not _is_safe_job_url(url):
            continue

        remote = bool(job.get("remote"))
        job_types = job.get("job_types") or ["Não informado"]

        results.append({
            "source": "Arbeitnow",
            "source_id": str(job.get("slug") or _digest(url)),
            "title": job.get("title") or "Vaga",
            "company": job.get("company_name") or "Empresa não informada",
            "description": job.get("description") or "",
            "location": job.get("location") or (
                "Remoto" if remote else "Não informada"
            ),
            "modality": "Remoto" if remote else "Não informada",
            "job_type": job_types[0],
            "published_at": job.get("created_at") or "",
            "url": url,
        })

    return results


def fetch_okemprego():
    """Search Brazilian job listings through the OkEmprego API."""
    api_url = "https://www.okemprego.com/api/v1/jobs"

    queries = [
        "desenvolvedor",
        "estágio tecnologia",
        "frontend",
        "backend",
        "Python",
        "dados",
    ]

    results = []
    seen = set()

    for query in queries:
        try:
            response = requests.get(
                api_url,
                params={
                    "country": "BR",
                    "q": query,
                    "perPage": 50,
                    "sort": "newest",
                },
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            response.raise_for_status()

            payload = response.json()
            jobs = payload.get("data", [])

            for job in jobs:
                url = job.get("url") or ""

                if not _is_safe_job_url(url) or url in seen:
                    continue

                seen.add(url)

                location = job.get("location") or {}
                city = location.get("municipality") or {}
                region = location.get("region") or {}

                if isinstance(city, dict):
                    city = city.get("name") or ""

                if isinstance(region, dict):
                    region = region.get("name") or ""

                remote_value = job.get("remote")

                modality = {
                    "full": "Remoto",
                    "hybrid": "Híbrido",
                    "onsite": "Presencial",
                }.get(remote_value, "Não informada")

                results.append({
                    "source": "OkEmprego",
                    "source_id": str(job.get("id") or _digest(url)),
                    "title": job.get("title") or "Vaga",
                    "company": job.get("company") or "Empresa não informada",
                    "description": job.get("description") or "",
                    "location": ", ".join(
                        part for part in [city, region] if part
                    ) or "Brasil",
                    "modality": modality,
                    "job_type": job.get("contractType") or "Não informado",
                    "published_at": job.get("postedAt") or "",
                    "url": url,
                })

        except (requests.RequestException, ValueError, AttributeError):
            # Uma busca com falha não impede as demais.
            continue

    return results


def fetch_nerdin():
    """Collect technology-related listings from Nerdin's public internship/junior page."""
    base_url = "https://www.nerdin.com.br/"
    page_url = urljoin(base_url, "vagas-estagio-junior.php")

    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    seen = set()

    tech_keywords = (
        "tecnologia",
        "desenvolvedor",
        "desenvolvimento",
        "programador",
        "programação",
        "software",
        "frontend",
        "front-end",
        "backend",
        "back-end",
        "full stack",
        "fullstack",
        "python",
        "javascript",
        "java",
        "dados",
        "data",
        "cibersegurança",
        "cybersecurity",
        "segurança da informação",
        "suporte",
        "service desk",
        "help desk",
        "infraestrutura",
        "devops",
        "cloud",
        "banco de dados",
        "dba",
        "qa",
        "quality assurance",
        "sistemas",
        "estágio de ti",
        "estagiário de ti",
        "estagiaria de ti",
        "inteligência artificial",
        "automação",
        "redes",
        "mobile",
        "android",
        "ios",
        "ux",
        "ui",
    )

    for card in soup.select(".vaga-card"):
        title_element = card.select_one(".vaga-titulo")
        if not title_element:
            continue

        # Remove the "Nova" badge from the title.
        for badge in title_element.select(".vaga-nova-badge"):
            badge.decompose()

        title = title_element.get_text(" ", strip=True)
        title_lower = title.lower()

        hashtags = [
            tag.get_text(" ", strip=True).lstrip("#")
            for tag in card.select(".vaga-hashtags a")
        ]

        searchable_text = (
            title_lower + " " + " ".join(hashtags).lower()
        )

        if not any(keyword in searchable_text for keyword in tech_keywords):
            continue

        relative_url = card.get("data-href")

        if not relative_url:
            link = card.select_one("a.btn-ver-vaga[href]")
            relative_url = link.get("href") if link else None

        if not relative_url:
            continue

        job_url = urljoin(base_url, relative_url)

        if not _is_safe_job_url(job_url) or job_url in seen:
            continue

        seen.add(job_url)

        company_element = card.select_one(".vaga-empresa-nome")
        location_element = card.select_one(".vaga-local-linha")
        salary_element = card.select_one(".vaga-salario-destaque")
        summary_element = card.select_one(".vaga-resumo-linha")
        time_element = card.select_one("time[datetime]")

        company = (
            company_element.get_text(" ", strip=True)
            if company_element
            else "Empresa não informada"
        )

        location = (
            location_element.get_text(" ", strip=True)
            if location_element
            else "Não informada"
        )

        salary = (
            salary_element.get_text(" ", strip=True)
            if salary_element
            else ""
        )

        summary = (
            summary_element.get_text(" ", strip=True)
            if summary_element
            else ""
        )

        published_at = (
            time_element.get("datetime", "")
            if time_element
            else ""
        )

        location_lower = location.lower()

        if any(
            word in location_lower
            for word in ("home office", "remoto", "remote")
        ):
            modality = "Remoto"
        elif "híbrido" in location_lower or "hybrid" in location_lower:
            modality = "Híbrido"
        elif any(
            word in location_lower
            for word in ("presencial", "onsite", "on-site")
        ):
            modality = "Presencial"
        else:
            modality = "Não informada"

        id_match = re.search(r"(\d+)(?:\.php)?$", relative_url)
        source_id = (
            id_match.group(1)
            if id_match
            else _digest(job_url)
        )

        description_parts = [
            part for part in (summary, salary) if part
        ]

        if hashtags:
            description_parts.append(
                "Tecnologias/temas: " + ", ".join(hashtags)
            )

        results.append({
            "source": "Nerdin",
            "source_id": str(source_id),
            "title": title,
            "company": company,
            "description": " | ".join(description_parts),
            "location": location,
            "modality": modality,
            "job_type": (
                summary.split("•")[0].strip()
                if summary
                else "Não informado"
            ),
            "published_at": published_at,
            "url": job_url,
        })

    return results


def fetch_empregare():
    """Busca vagas ativas na API pública de jobboards Empregare (sem autenticação)."""
    endpoint = "https://pdv.empregare.com/api/pt-br/vagas/buscar-novo"
    queries = ("estágio tecnologia", "desenvolvedor júnior")
    results = []
    seen = set()

    for query in queries:
        for page in (1, 2):
            response = requests.get(
                endpoint,
                params={"Query": query, "Ordenacao": 0, "ItensPagina": 30, "Pagina": page},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            model = payload.get("model") or {}
            for job in model.get("dados") or []:
                job_id = str(job.get("id") or "")
                raw_url = job.get("url") or (f"/v{job_id}" if job_id else "")
                if not raw_url:
                    continue
                url = urljoin("https://www.empregare.com/", raw_url)
                if not _is_safe_job_url(url) or url in seen:
                    continue
                seen.add(url)

                cities = job.get("cidades") or []
                if isinstance(cities, str):
                    cities = [cities]
                remote_text = job.get("trabalhoRemotoTexto") or ""
                remote_flag = job.get("trabalhoRemoto")
                remote_label = str(remote_text).lower()
                if remote_flag is True or "remoto" in remote_label:
                    modality = "Remoto"
                elif "híbr" in remote_label or "hibrid" in remote_label:
                    modality = "Híbrido"
                elif cities:
                    modality = "Presencial"
                else:
                    modality = "Não informada"

                published = job.get("data") or job.get("dataCadastro") or ""
                if not published and job.get("timestamp"):
                    try:
                        from datetime import datetime, timezone
                        published = datetime.fromtimestamp(
                            int(job["timestamp"]), tz=timezone.utc
                        ).isoformat()
                    except (TypeError, ValueError, OSError):
                        published = ""

                results.append({
                    "source": "Empregare",
                    "source_id": job_id or _digest(url),
                    "title": job.get("titulo") or "Vaga",
                    "company": job.get("empresa") or "Empresa não informada",
                    "description": job.get("chamada") or "",
                    "location": ", ".join(str(city) for city in cities if city) or "Brasil",
                    "modality": modality,
                    "job_type": job.get("nivel") or job.get("tipoProcessoSeletivo") or "Não informado",
                    "published_at": str(published),
                    "url": url,
                })
            if page >= int(model.get("totalPaginas") or page):
                break

    return results


def _xml_child_text(element, name):
    """Obtém texto por nome local, tolerando namespaces e caixa."""
    for child in list(element):
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name == name.lower():
            return (child.text or "").strip()
    return ""


def fetch_empregando_brasil():
    """Consome o feed XML público para parceiros do Empregando Brasil."""
    import xml.etree.ElementTree as ET

    response = requests.get(
        "https://empregandobrasil.com.br/feeds/partners/jobs.xml",
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    content = response.content
    if len(content) > 8 * 1024 * 1024:
        raise ValueError("Feed Empregando Brasil excedeu o limite de 8 MB.")
    root = ET.fromstring(content)
    results = []
    seen = set()

    for element in root.iter():
        if element is root:
            continue
        fields = {
            child.tag.rsplit("}", 1)[-1].lower()
            for child in list(element)
        }
        if not {"id", "title", "url"} <= fields:
            continue
        job_id = _xml_child_text(element, "id")
        url = _xml_child_text(element, "url")
        if not _is_safe_job_url(url) or url in seen:
            continue
        seen.add(url)
        city = _xml_child_text(element, "city")
        state = _xml_child_text(element, "state")
        description_html = _xml_child_text(element, "description")
        description = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
        published = _xml_child_text(element, "published") or _xml_child_text(element, "created")
        results.append({
            "source": "Empregando Brasil",
            "source_id": job_id or _digest(url),
            "title": _xml_child_text(element, "title") or "Vaga",
            "company": _xml_child_text(element, "company") or "Empresa não informada",
            "description": description,
            "location": ", ".join(part for part in (city, state) if part) or "Brasil",
            "modality": "Não informada",
            "job_type": "Não informado",
            "published_at": published,
            "url": url,
        })

    return results


def fetch_jobicy():
    """Busca vagas remotas na API pública do Jobicy (cache local de uma hora)."""
    now = time.monotonic()
    with _JOBICY_CACHE_LOCK:
        if _JOBICY_CACHE["items"] is not None and now < _JOBICY_CACHE["expires_at"]:
            return [dict(item) for item in _JOBICY_CACHE["items"]]

        response = requests.get(
            "https://jobicy.com/api/jobs",
            params={"count": 200},
            headers={**HEADERS, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") is False:
            raise RuntimeError(payload.get("error") or "A API Jobicy informou falha.")
        results = []
        for job in payload.get("jobs") or []:
            url = job.get("url") or ""
            if not _is_safe_job_url(url):
                continue
            job_types = job.get("jobType") or []
            if isinstance(job_types, str):
                job_types = [job_types]
            description_html = job.get("jobDescription") or job.get("jobExcerpt") or ""
            description = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
            results.append({
                "source": "Jobicy",
                "source_id": str(job.get("id") or _digest(url)),
                "title": job.get("jobTitle") or "Vaga",
                "company": job.get("companyName") or "Empresa não informada",
                "description": description,
                "location": job.get("jobGeo") or "Remoto",
                "modality": "Remoto",
                "job_type": ", ".join(str(value) for value in job_types) or "Não informado",
                "published_at": job.get("pubDate") or "",
                "url": url,
            })
        _JOBICY_CACHE["items"] = [dict(item) for item in results]
        _JOBICY_CACHE["expires_at"] = now + _JOBICY_CACHE_TTL
        return results

def fetch_remoteok():
    """Consome o feed JSON público do Remote OK, preservando a URL canônica."""
    response = requests.get(
        "https://remoteok.com/api",
        headers={**HEADERS, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Formato inesperado no feed Remote OK.")
    results = []
    for job in payload:
        if not isinstance(job, dict) or not job.get("id"):
            # O primeiro elemento do feed pode conter metadados/aviso legal.
            continue
        url = job.get("url") or ""
        if not _is_safe_job_url(url):
            continue
        tags = job.get("tags") or []
        description_html = job.get("description") or ""
        description = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
        results.append({
            "source": "Remote OK",
            "source_id": str(job["id"]),
            "title": job.get("position") or job.get("title") or "Vaga",
            "company": job.get("company") or "Empresa não informada",
            "description": description,
            "location": job.get("location") or "Remoto",
            "modality": "Remoto",
            "job_type": ", ".join(str(tag) for tag in tags) or "Não informado",
            "published_at": job.get("date") or "",
            "url": url,
        })
    return results


SOURCES = {
    "Arbeitnow": fetch_arbeitnow,
    "OkEmprego": fetch_okemprego,
    "Nerdin": fetch_nerdin,
    "Empregare": fetch_empregare,
    "Empregando Brasil": fetch_empregando_brasil,
    "Jobicy": fetch_jobicy,
    "Remote OK": fetch_remoteok,
}


# Capacidades reais de cada plataforma. "search_api" = coleta automática implementada;
# "apply_api" = há API autorizada de candidatura (nenhuma das fontes abaixo oferece uma).
SOURCE_INFO = {
    "Remotive": {"mode": "link_only", "search_api": False, "apply_api": False,
                 "note": "A API restringe a redistribuição em sites de terceiros. Abra o portal original; integração automática depende de autorização escrita."},
    "Arbeitnow": {"mode": "api", "search_api": True, "apply_api": False,
                  "note": "API pública (vagas majoritariamente na Europa). Candidatura no site original."},
    "OkEmprego": {"mode": "api", "search_api": True, "apply_api": False,
                  "note": "API de vagas do Brasil. Candidatura no site original."},
    "Nerdin": {"mode": "html", "search_api": True, "apply_api": False,
               "note": "Leitura da página pública de vagas de estágio/júnior. Pode quebrar se o layout mudar."},
    "Empregare": {"mode": "api", "search_api": True, "apply_api": False,
                   "note": "API pública de vagas ativas; candidatura segue no link canônico do portal."},
    "Empregando Brasil": {"mode": "api", "search_api": True, "apply_api": False,
                          "note": "Feed XML público para parceiros, atualizado a cada 12 horas; candidatura no anunciante."},
    "Jobicy": {"mode": "api", "search_api": True, "apply_api": False,
                "note": "API JSON pública de vagas remotas dos últimos sete dias; exige crédito à Jobicy e link canônico."},
    "Remote OK": {"mode": "api", "search_api": True, "apply_api": False,
                  "note": "Feed JSON público de vagas remotas; exige crédito à fonte e link para o anúncio original."},
    "Indeed": {"mode": "link_only", "search_api": False, "apply_api": False,
               "note": "Sem API pública de busca/candidatura (só parceiros aprovados) e os termos proíbem "
                       "raspagem. Use os links de busca e cadastre a vaga manualmente."},
    "Vagas.com": {"mode": "link_only", "search_api": False, "apply_api": False,
                  "note": "Portal de vagas. Sem conector autorizado configurado; abra a busca no portal e finalize a candidatura no site."},
    "LinkedIn": {"mode": "link_only", "search_api": False, "apply_api": False,
                 "note": "Acesso a APIs de vagas depende de aprovação/parceria. O JobFinder abre a busca; não coleta nem automatiza login/candidatura."},
    "Gupy": {"mode": "link_only", "search_api": False, "apply_api": False,
             "note": "ATS de empresas. A API documentada é destinada à integração com páginas de carreira de clientes e exige token da empresa; não é uma API pública agregadora."},
    "InfoJobs": {"mode": "link_only", "search_api": False, "apply_api": False,
                 "note": "Busca externa no portal; candidatura e etapas são concluídas no site."},
    "Catho": {"mode": "link_only", "search_api": False, "apply_api": False,
              "note": "Busca externa no portal; candidatura e etapas são concluídas no site."},
    "Sólides Vagas": {"mode": "link_only", "search_api": False, "apply_api": False,
                      "note": "Portal/ATS; busca externa e candidatura no ambiente da empresa."},
    "Trabalha Brasil": {"mode": "link_only", "search_api": False, "apply_api": False,
                        "note": "Busca externa no portal; candidatura no site original."},
    "Empregos.com.br": {"mode": "link_only", "search_api": False, "apply_api": False,
                        "note": "Busca externa no portal; candidatura no site original."},
    "Glassdoor": {"mode": "link_only", "search_api": False, "apply_api": False,
                  "note": "Busca externa; use também avaliações e informações da empresa no portal."},
    "Jooble": {"mode": "link_only", "search_api": False, "apply_api": False,
               "note": "Agregador; busca externa no portal. Vagas podem se repetir em outras fontes."},
    "CIEE": {"mode": "link_only", "search_api": False, "apply_api": False,
             "note": "Portal de estágio e aprendizagem; candidatura exige fluxo e cadastro próprios."},
    "Nube": {"mode": "link_only", "search_api": False, "apply_api": False,
             "note": "Portal de estágio; candidatura exige fluxo e cadastro próprios."},
    "Companhia de Estágios": {"mode": "link_only", "search_api": False, "apply_api": False,
                              "note": "Portal de estágio e trainee; candidatura no ambiente próprio."},
    "99jobs": {"mode": "link_only", "search_api": False, "apply_api": False,
               "note": "Portal de carreiras; candidatura no ambiente próprio."},
    "GeekHunter": {"mode": "link_only", "search_api": False, "apply_api": False,
                   "note": "Plataforma especializada em tecnologia; cadastro e candidatura no ambiente próprio."},
    "Programathor": {"mode": "link_only", "search_api": False, "apply_api": False,
                     "note": "Portal especializado em tecnologia; candidatura no site original."},
    "Trampos": {"mode": "link_only", "search_api": False, "apply_api": False,
                "note": "Portal de vagas criativas e digitais; candidatura no site original."},
    "Remotar": {"mode": "link_only", "search_api": False, "apply_api": False,
                "note": "Portal de vagas remotas; candidatura no site original."},
    "Emprega Brasil / SINE": {"mode": "link_only", "search_api": False, "apply_api": False,
                              "note": "Serviço público de intermediação; consulta e candidatura seguem o fluxo oficial."},
    "Revelo": {"mode": "link_only", "search_api": False, "apply_api": False,
               "note": "Plataforma de talentos; disponibilidade e fluxo de cadastro devem ser confirmados no portal."},
}

LINK_ONLY_SOURCES = [name for name, info in SOURCE_INFO.items() if info["mode"] == "link_only"]


def external_search_links(terms=None):
    """Gera atalhos de busca para portais sem conector autorizado.

    Esses links não representam coleta automática nem candidatura automática.
    """
    from urllib.parse import quote_plus

    terms = [t.strip() for t in (terms or [
        "estágio desenvolvimento de software",
        "desenvolvedor júnior",
    ]) if t and t.strip()]
    if not terms:
        terms = ["estágio desenvolvimento de software"]

    templates = {
        "Remotive": "https://remotive.com/remote-jobs",
        "LinkedIn": "https://www.linkedin.com/jobs/search/?keywords={q}",
        "Indeed": "https://br.indeed.com/jobs?q={q}",
        "Gupy": "https://www.google.com/search?q=site%3Agupy.io%2Fjobs+{q}",
        "InfoJobs": "https://www.infojobs.com.br/vagas-de-{q}.aspx",
        "Catho": "https://www.catho.com.br/vagas/{q}/",
        "Vagas.com": "https://www.vagas.com.br/",
        "Sólides Vagas": "https://www.google.com/search?q=site%3Avagas.solides.com.br+{q}",
        "Trabalha Brasil": "https://www.trabalhabrasil.com.br/vagas-empregos/",
        "Empregos.com.br": "https://www.empregos.com.br/vagas/",
        "Glassdoor": "https://www.glassdoor.com.br/Vaga/",
        "Jooble": "https://br.jooble.org/SearchResult?ukw={q}",
        "CIEE": "https://portal.ciee.org.br/",
        "Nube": "https://www.nube.com.br/",
        "Companhia de Estágios": "https://www.ciadeestagios.com.br/",
        "99jobs": "https://www.99jobs.com/",
        "GeekHunter": "https://www.geekhunter.com.br/",
        "Programathor": "https://programathor.com.br/",
        "Trampos": "https://trampos.co/",
        "Remotar": "https://remotar.com.br/",
        "Emprega Brasil / SINE": "https://servicos.mte.gov.br/",
        "Revelo": "https://www.revelo.com.br/",
    }
    query = " ".join(terms)
    encoded = quote_plus(query)
    links = []
    for source, template in templates.items():
        url = template.format(q=encoded) if "{q}" in template else template
        links.append({"source": source, "query": query, "url": url})
    return links


def collect_selected(names):
    results = []
    errors = []

    for name in names:
        fetch_function = SOURCES.get(name)

        if fetch_function is None:
            continue

        try:
            results.extend(fetch_function())
        except Exception as exc:
            errors.append(
                f"{name}: {type(exc).__name__}: {exc}"
            )

    return results, errors
