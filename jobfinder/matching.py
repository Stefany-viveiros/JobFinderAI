"""Compatibilidade explicável entre vagas e perfil profissional.

A pontuação é determinística: não presume domínio de uma tecnologia só porque
ela aparece em um texto e não confunde nomes parecidos (Java/JavaScript).
"""
import re
import unicodedata


TECHNOLOGY_TERMS = (
    "JavaScript", "TypeScript", "Node.js", "NodeJS", "FastAPI", "Power BI",
    "PostgreSQL", "TensorFlow", "PyTorch", "Google Cloud", "Machine Learning",
    "API REST", "REST API", "HTML5", "CSS3", "C++", "C#", ".NET",
    "Python", "Java", "PHP", "React", "Angular", "Vue", "Django", "Flask",
    "HTML", "CSS", "SQL", "MySQL", "SQLite", "MongoDB", "GitHub", "Git",
    "Docker", "AWS", "Azure", "Excel", "Linux", "Kotlin", "Swift",
    "Flutter", "Android", "iOS", "Spring", "Laravel", "Pandas", "NumPy",
    "Selenium", "Cypress", "Jest", "Figma", "PHP", "Ruby", "Go",
)
MANDATORY_MARKERS = re.compile(
    r"\b(obrigat\w*|necessar\w*|imprescind\w*|must[ -]have|required|"
    r"mandatory|essential|minimum qualifications|requisitos mínimos?|"
    r"requisito mínimo)\b"
)
DESIRABLE_MARKERS = re.compile(
    r"\b(desej[aá]vel|diferencial|nice[ -]to[ -]have|preferred|plus)\b"
)


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
    """Aceita listas separadas por vírgula, ponto e vírgula, barra ou quebra de linha."""
    return [
        normalize(part.strip())
        for part in re.split(r"[,;|\n]+", str(value or ""))
        if part.strip()
    ]


def _contains_phrase(text, phrase):
    """Busca frase inteira: Java não pode casar dentro de JavaScript."""
    phrase = normalize(phrase).strip()
    if not phrase:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pattern, normalize(text)) is not None


def profile_technology_terms(profile):
    """Tecnologias explicitamente listadas ou citadas em projetos/experiência/cursos.

    A presença no perfil é evidência textual, não uma afirmação de nível de domínio.
    """
    explicit = []
    for field in ("technologies", "skills", "keywords"):
        explicit.extend(split_values(getattr(profile, field, "")))

    context = " ".join(
        getattr(profile, field, "") or ""
        for field in ("projects", "experience", "certifications", "course")
    )
    contextual = [
        normalize(item) for item in TECHNOLOGY_TERMS
        if _contains_phrase(context, item)
    ]
    return sorted(set(item for item in explicit + contextual if item))


def _mandatory_technologies(description):
    """Identifica tecnologias citadas em frases com marcadores explícitos de obrigatoriedade."""
    required = set()
    for sentence in re.split(r"[.!?;\n]+", normalize(description)):
        if DESIRABLE_MARKERS.search(sentence):
            continue
        if not MANDATORY_MARKERS.search(sentence):
            continue
        for technology in TECHNOLOGY_TERMS:
            if _contains_phrase(sentence, technology):
                required.add(normalize(technology))
    return sorted(required)


def score_job(job, profile):
    title = normalize(job.get("title"))
    description = normalize(job.get("description"))
    location = normalize(job.get("location"))
    modality = normalize(job.get("modality"))
    job_type = normalize(job.get("job_type"))

    tech = profile_technology_terms(profile)
    haystack = f"{title} {description}"
    found = sorted(term for term in tech if _contains_phrase(haystack, term))

    excluded = split_values(getattr(profile, "exclude_terms", ""))
    blocked = [term for term in excluded if _contains_phrase(haystack, term)]
    if blocked:
        return 0, [], ["Termos excluídos: " + ", ".join(blocked)]

    interests = split_values(getattr(profile, "interests", ""))
    area_hits = [
        item for item in interests
        if _contains_phrase(title, item) or _contains_phrase(description[:2500], item)
    ]

    desired_modalities = split_values(getattr(profile, "modality", ""))
    modality_aliases = {
        "remoto": ("remoto", "remote", "work from home", "home office"),
        "hibrido": ("hibrido", "hybrid"),
        "presencial": ("presencial", "on-site", "onsite", "on site"),
    }
    job_modality_text = " ".join((modality, location, description[:1200]))
    modality_hit = any(
        _contains_phrase(job_modality_text, alias)
        for desired in desired_modalities
        for alias in modality_aliases.get(desired, (desired,))
    )

    desired_locations = normalize(getattr(profile, "location", ""))
    location_hit = bool(
        desired_locations
        and (
            _contains_phrase(location, desired_locations)
            or _contains_phrase(location, "remoto")
            or _contains_phrase(location, "remote")
            or _contains_phrase(description[:1200], "remoto")
            or _contains_phrase(description[:1200], "remote")
        )
    )

    level_terms = (
        "intern", "internship", "estagio", "junior", "entry level",
        "entry-level", "graduate", "trainee", "aprendiz",
    )
    level_hit = any(_contains_phrase(title, term) for term in level_terms) or any(
        _contains_phrase(job_type, term) for term in level_terms
    )

    desired_types = split_values(getattr(profile, "job_types", ""))
    type_hit = any(
        _contains_phrase(title, term) or _contains_phrase(job_type, term)
        for term in desired_types
    )

    weights = {
        "keywords": max(0, int(getattr(profile, "weight_keywords", 40) or 0)),
        "area": max(0, int(getattr(profile, "weight_area", 25) or 0)),
        "modality": max(0, int(getattr(profile, "weight_modality", 15) or 0)),
        "location": max(0, int(getattr(profile, "weight_location", 10) or 0)),
        "level": max(0, int(getattr(profile, "weight_level", 10) or 0)),
    }
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
        matched.append("Tecnologias do perfil também citadas na vaga: " + ", ".join(found[:12]))
    elif tech:
        missing.append("Nenhuma tecnologia identificada no perfil foi localizada no texto da vaga")
    else:
        missing.append("Perfil sem tecnologias identificadas; complete ou revise suas habilidades e projetos")

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

    if level_hit or type_hit:
        matched.append("Indícios de nível/tipo de oportunidade compatível")
    else:
        missing.append("Nível da vaga não confirmado; verifique os requisitos")

    required = _mandatory_technologies(description)
    unconfirmed_required = [item for item in required if item not in tech]
    if unconfirmed_required:
        # Não afirma que a pessoa não sabe a tecnologia: apenas impede a preparação
        # automática quando o currículo/perfil não comprova um requisito obrigatório.
        percentage = min(percentage, 49)
        missing.append(
            "Requisito(s) obrigatório(s) não identificado(s) no perfil — confirme antes de se candidatar: "
            + ", ".join(unconfirmed_required)
        )

    if not description.strip():
        missing.append("A fonte não forneceu descrição suficiente para análise")
    missing.append("Pontuação é uma triagem inicial; revise os requisitos e a candidatura antes de enviar")

    return percentage, matched, missing
