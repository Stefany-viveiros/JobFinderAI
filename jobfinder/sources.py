
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
