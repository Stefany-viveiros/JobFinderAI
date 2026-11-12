"""Public job feeds. Source availability and terms can change; failures are isolated."""

import hashlib
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


TIMEOUT = 18

HEADERS = {
    "User-Agent": "JobFinderAI/1.0 (personal job-search tool)"
}


def _digest(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()[:24]


def fetch_remotive():
    response = requests.get(
        "https://remotive.com/api/remote-jobs",
        params={"limit": 100},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    items = response.json().get("jobs", [])
    results = []

    for job in items:
        url = job.get("url") or ""
        if not url:
            continue

        results.append({
            "source": "Remotive",
            "source_id": str(job.get("id") or _digest(url)),
            "title": job.get("title") or "Vaga",
            "company": job.get("company_name") or "Empresa não informada",
            "description": job.get("description") or "",
            "location": job.get("candidate_required_location") or "Remoto",
            "modality": "Remoto",
            "job_type": job.get("job_type") or "Não informado",
            "published_at": job.get("publication_date") or "",
            "url": url,
        })

    return results


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
        if not url:
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

                if not url or url in seen:
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

        if job_url in seen:
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


SOURCES = {
    "Remotive": fetch_remotive,
    "Arbeitnow": fetch_arbeitnow,
    "OkEmprego": fetch_okemprego,
    "Nerdin": fetch_nerdin,
}


# Capacidades reais de cada plataforma. "search_api" = coleta automática implementada;
# "apply_api" = há API autorizada de candidatura (nenhuma das fontes abaixo oferece uma).
SOURCE_INFO = {
    "Remotive": {"mode": "api", "search_api": True, "apply_api": False,
                 "note": "API pública de vagas remotas. Candidatura é feita no site original."},
    "Arbeitnow": {"mode": "api", "search_api": True, "apply_api": False,
                  "note": "API pública (vagas majoritariamente na Europa). Candidatura no site original."},
    "OkEmprego": {"mode": "api", "search_api": True, "apply_api": False,
                  "note": "API de vagas do Brasil. Candidatura no site original."},
    "Nerdin": {"mode": "html", "search_api": True, "apply_api": False,
               "note": "Leitura da página pública de vagas de estágio/júnior. Pode quebrar se o layout mudar."},
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
