"""Compatibilidade explicável entre vagas e perfil profissional."""
import re
import unicodedata


def normalize(value):
    """Normaliza texto para facilitar comparações."""
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value.lower()


def terms(text):
    """Extrai palavras e tecnologias, preservando símbolos comuns de linguagens."""
    return {
        normalize(x)
        for x in re.findall(r"[a-zA-ZÀ-ÿ0-9+#.]+", str(text or ""))
        if len(x) > 2
    }


def split_values(value):
    return [
        normalize(part.strip())
        for part in str(value or "").split(",")
        if part.strip()
    ]


def score_job(job, profile):
    title = normalize(job.get("title"))
    description = normalize(job.get("description"))
    location = normalize(job.get("location"))
    modality = normalize(job.get("modality"))
    job_type = normalize(job.get("job_type"))

    # Informações reais do perfil que podem ser comparadas com a vaga.
    tech_text = " ".join([
        getattr(profile, "technologies", "") or "",
        getattr(profile, "skills", "") or "",
        getattr(profile, "keywords", "") or "",
    ])
    tech = terms(tech_text)
    haystack = f"{title} {description}"
    found = sorted(term for term in tech if term in haystack)

    excluded = split_values(getattr(profile, "exclude_terms", ""))
    blocked = [term for term in excluded if term in haystack]
    if blocked:
        return 0, [], ["Termos excluídos: " + ", ".join(blocked)]

    interests = split_values(getattr(profile, "interests", ""))
    area_hits = [
        item for item in interests
        if item in title or item in description[:2500]
    ]

    desired_modalities = split_values(getattr(profile, "modality", ""))
    modality_aliases = {
        "remoto": ("remoto", "remote", "work from home"),
        "hibrido": ("hibrido", "hybrid"),
        "presencial": ("presencial", "on-site", "onsite", "on site"),
    }
    normalized_modality = normalize(modality)
    modality_hit = any(
        alias in normalized_modality
        for desired in desired_modalities
        for alias in modality_aliases.get(desired, (desired,))
    )

    desired_locations = normalize(getattr(profile, "location", ""))
    location_hit = bool(
        desired_locations
        and (
            desired_locations in location
            or "remoto" in location
            or "remote" in location
        )
    )

    level_terms = (
        "intern", "internship", "estagio", "junior", "entry level",
        "entry-level", "graduate", "trainee", "aprendiz",
    )
    level_hit = any(term in title for term in level_terms) or any(
        term in description[:1800] for term in level_terms
    )

    desired_types = split_values(getattr(profile, "job_types", ""))
    type_hit = any(
        term in title or term in job_type
        for term in desired_types
    )

    # Pesos são normalizados: a soma pode ser qualquer valor.
    weights = {
        "keywords": max(0, int(getattr(profile, "weight_keywords", 40) or 0)),
        "area": max(0, int(getattr(profile, "weight_area", 25) or 0)),
        "modality": max(0, int(getattr(profile, "weight_modality", 15) or 0)),
        "location": max(0, int(getattr(profile, "weight_location", 10) or 0)),
        "level": max(0, int(getattr(profile, "weight_level", 10) or 0)),
    }

    # Se o usuário cadastrou tipos de vaga, parte do peso de nível
    # também considera estágio/júnior explicitamente.
    total = sum(weights.values()) or 1
    earned = (
        weights["keywords"] * (len(found) / max(1, len(tech)))
        + weights["area"] * (1 if area_hits else 0)
        + weights["modality"] * (1 if modality_hit else 0)
        + weights["location"] * (1 if location_hit else 0)
        + weights["level"] * (1 if level_hit or type_hit else 0)
    )
    percentage = min(100, round(100 * earned / total))

    matched = []
    missing = []

    if found:
        matched.append("Termos técnicos encontrados: " + ", ".join(found[:12]))
    elif tech:
        missing.append("Nenhuma tecnologia cadastrada foi localizada no texto da vaga")

    if area_hits:
        matched.append("Área relacionada: " + ", ".join(area_hits[:5]))
    elif interests:
        missing.append("Área de interesse não identificada claramente")

    if modality_hit:
        matched.append("Modalidade compatível com o perfil")
    else:
        missing.append("Modalidade não confirmada como compatível")

    if location_hit:
        matched.append("Localização compatível ou indicação de vaga remota")
    elif desired_locations:
        missing.append("Localização não confirmada")

    if level_hit:
        matched.append("Indícios de estágio, júnior ou nível de entrada")
    elif type_hit:
        matched.append("Tipo de oportunidade relacionado ao perfil")
    else:
        missing.append("Nível da vaga não confirmado; verifique os requisitos")

    if not description.strip():
        missing.append("A fonte não forneceu descrição suficiente para análise")

    # Não temos como confirmar elegibilidade, senioridade ou domínio
    # apenas pela descrição. Esses pontos precisam ser verificados.
    missing.append("Confira os requisitos obrigatórios antes de se candidatar")

    return percentage, matched, missing
