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
    "Selenium", "Cypress", "Jest", "Figma", "Ruby", "Golang",
)
MANDATORY_MARKERS = re.compile(
    r"\b(obrigat\w*|necessar\w*|imprescind\w*|must[ -]have|required|"
    r"mandatory|essential|minimum qualifications|requisitos minimos?|"
    r"requisito minimo)\b"
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
    explicit = split_values(getattr(profile, "technologies", ""))
    context = " ".join(
        getattr(profile, field, "") or ""
        for field in (
            "technologies", "skills", "keywords", "projects",
            "experience", "certifications", "course",
        )
    )
    contextual = [
        normalize(item) for item in TECHNOLOGY_TERMS
        if _contains_phrase(context, item)
    ]
    return sorted(set(item for item in explicit + contextual if item))


def _mandatory_technologies(description):
    """Identifica tecnologias próximas a marcadores explícitos de obrigatoriedade."""
    required = set()
    for sentence in re.split(r"[.!?;\n]+", normalize(description)):
        mandatory = list(MANDATORY_MARKERS.finditer(sentence))
        if not mandatory:
            continue
        desirable = list(DESIRABLE_MARKERS.finditer(sentence))
        for technology in TECHNOLOGY_TERMS:
            pattern = r"(?<![a-z0-9])" + re.escape(normalize(technology)) + r"(?![a-z0-9])"
            for match in re.finditer(pattern, sentence):
                def distance(marker):
                    if marker.end() < match.start():
                        return match.start() - marker.end()
                    if marker.start() > match.end():
                        return marker.start() - match.end()
                    return 0

                required_distance = min(distance(marker) for marker in mandatory)
                desirable_distance = min(
                    (distance(marker) for marker in desirable),
                    default=float("inf"),
                )
                if required_distance <= desirable_distance:
                    required.add(normalize(technology))
    return sorted(required)

def score_job(job, profile):
    title = normalize(job.get("title"))
    description = normalize(job.get("description"))
    location = normalize(job.get("location"))
    modality = normalize(job.get("modality"))
    job_type = normalize(job.get("job_type"))

    # Informações reais do perfil que podem ser comparadas com a vaga.
    project_technologies = " ".join(
        str(getattr(item, "technologies", "") or "")
        for item in (getattr(profile, "portfolio_projects", []) or [])
    )
    course_names = " ".join(
        str(getattr(item, "name", "") or "")
        for item in (getattr(profile, "courses", []) or [])
    )
    education_names = " ".join(
        str(getattr(item, "course", "") or "")
        for item in (getattr(profile, "educations", []) or [])
    )
    tech_text = " ".join([
        getattr(profile, "technologies", "") or "",
        getattr(profile, "skills", "") or "",
        getattr(profile, "keywords", "") or "",
        project_technologies,
        course_names,
        education_names,
    ])
    tech = terms(tech_text)
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


COMPLETED_VALUES = {"concluído", "concluido", "completed", "finalizado"}
IN_PROGRESS_VALUES = {"em andamento", "em desenvolvimento", "em curso", "em estudo", "in progress"}


def _requirement_classification(sentence: str, match: re.Match) -> str:
    mandatory = list(MANDATORY_MARKERS.finditer(sentence))
    desirable = list(DESIRABLE_MARKERS.finditer(sentence))
    if mandatory and desirable:
        # Dois marcadores conflitantes na mesma frase não permitem afirmar a prioridade.
        return "ambiguous"
    if mandatory:
        return "mandatory"
    if desirable:
        return "desirable"
    return "unspecified"


def classify_job_requirements(description: str) -> list[dict]:
    """Extrai tecnologias e classifica obrigatoriedade somente quando o texto dá indício."""
    found = {}
    clean = re.sub(r"<[^>]*>", " ", str(description or ""))
    for sentence in re.split(r"[.!?;\\n]+", normalize(clean)):
        for technology in TECHNOLOGY_TERMS:
            phrase = normalize(technology)
            pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
            for match in re.finditer(pattern, sentence):
                classification = _requirement_classification(sentence, match)
                previous = found.get(phrase)
                if previous is None:
                    found[phrase] = classification
                elif previous != classification and classification != "unspecified":
                    found[phrase] = "ambiguous"
    labels = {
        "mandatory": "Obrigatório (marcador textual)",
        "desirable": "Desejável (marcador textual)",
        "unspecified": "Obrigatoriedade não especificada",
        "ambiguous": "Classificação ambígua",
    }
    return [
        {
            "name": name,
            "requirement_type": requirement_type,
            "requirement_label": labels[requirement_type],
        }
        for name, requirement_type in sorted(found.items())
    ]


def _excerpt(text: str, technology: str, limit: int = 220) -> str:
    raw = re.sub(r"<[^>]*>", " ", str(text or ""))
    match = re.search(
        r"(?<![a-z0-9])" + re.escape(technology) + r"(?![a-z0-9])",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return raw.strip()[:limit]
    start = max(0, match.start() - 80)
    end = min(len(raw), match.end() + 100)
    result = raw[start:end].strip()
    return ("…" if start else "") + result + ("…" if end < len(raw) else "")


def _profile_sources(profile) -> list[dict]:
    """Retorna textos e origens do perfil sem combinar contextos de registros diferentes."""
    sources = []
    for item in getattr(profile, "experiences", []) or []:
        label = " — ".join(x for x in (
            (getattr(item, "role", "") or "").strip(),
            (getattr(item, "company", "") or "").strip(),
        ) if x) or "Experiência profissional"
        sources.append({
            "source_type": "professional_experience",
            "source_label": label,
            "source_id": getattr(item, "id", None),
            "text": " ".join((getattr(item, "role", "") or "", getattr(item, "company", "") or "", getattr(item, "description", "") or "")),
        })

    for item in getattr(profile, "portfolio_projects", []) or []:
        state = (getattr(item, "status", "") or "").strip().casefold()
        if state in COMPLETED_VALUES:
            source_type = "completed_project"
        elif state in IN_PROGRESS_VALUES:
            source_type = "ongoing_project"
        else:
            source_type = "project_status_ambiguous"
        sources.append({
            "source_type": source_type,
            "source_label": (getattr(item, "name", "") or "Projeto").strip(),
            "source_id": getattr(item, "id", None),
            "text": " ".join((getattr(item, "name", "") or "", getattr(item, "description", "") or "", getattr(item, "technologies", "") or "")),
        })

    for item in getattr(profile, "courses", []) or []:
        state = (getattr(item, "status", "") or "").strip().casefold()
        if state in COMPLETED_VALUES:
            source_type = "completed_course"
        elif state in IN_PROGRESS_VALUES:
            source_type = "ongoing_course"
        else:
            source_type = "course_status_ambiguous"
        sources.append({
            "source_type": source_type,
            "source_label": " — ".join(x for x in (
                (getattr(item, "name", "") or "").strip(),
                (getattr(item, "provider", "") or "").strip(),
            ) if x) or "Curso",
            "source_id": getattr(item, "id", None),
            "text": " ".join((getattr(item, "name", "") or "", getattr(item, "provider", "") or "")),
        })

    for item in getattr(profile, "certifications_items", []) or []:
        sources.append({
            "source_type": "certification_record",
            "source_label": " — ".join(x for x in (
                (getattr(item, "name", "") or "").strip(),
                (getattr(item, "issuer", "") or "").strip(),
            ) if x) or "Certificação",
            "source_id": getattr(item, "id", None),
            "text": " ".join((getattr(item, "name", "") or "", getattr(item, "issuer", "") or "")),
        })

    for item in getattr(profile, "educations", []) or []:
        sources.append({
            "source_type": "education_record",
            "source_label": " — ".join(x for x in (
                (getattr(item, "course", "") or "").strip(),
                (getattr(item, "institution", "") or "").strip(),
            ) if x) or "Formação acadêmica",
            "source_id": getattr(item, "id", None),
            "text": " ".join((getattr(item, "course", "") or "", getattr(item, "institution", "") or "", getattr(item, "description", "") or "")),
        })

    legacy_fields = (
        ("legacy_experience", "Experiência (campo legado)", "experience"),
        ("legacy_project", "Projeto (campo legado)", "projects"),
        ("legacy_certification", "Certificação (campo legado)", "certifications"),
        ("self_declared", "Tecnologias declaradas", "technologies"),
        ("self_declared", "Habilidades declaradas", "skills"),
        ("self_declared", "Palavras-chave declaradas", "keywords"),
    )
    for source_type, label, field in legacy_fields:
        value = getattr(profile, field, "") or ""
        if value.strip():
            sources.append({
                "source_type": source_type,
                "source_label": label,
                "source_id": None,
                "text": value,
            })
    return sources


def diagnose_job_requirements(
    description: str,
    profile,
    *,
    self_assessed_skill_names: set[str] | None = None,
) -> dict:
    """Relaciona requisitos textuais da vaga às origens registradas no perfil."""
    requirements = classify_job_requirements(description)
    sources = _profile_sources(profile)
    self_assessed = {normalize(item) for item in (self_assessed_skill_names or set())}
    evidenced_sources = {
        "professional_experience", "completed_project", "completed_course",
        "certification_record", "education_record", "legacy_experience",
        "legacy_project", "legacy_certification",
    }
    source_labels = {
        "professional_experience": "Experiência profissional",
        "completed_project": "Projeto concluído",
        "ongoing_project": "Projeto em andamento",
        "completed_course": "Curso concluído",
        "ongoing_course": "Curso em andamento",
        "certification_record": "Certificação cadastrada",
        "education_record": "Formação acadêmica",
        "legacy_experience": "Experiência (campo legado)",
        "legacy_project": "Projeto (campo legado)",
        "legacy_certification": "Certificação (campo legado)",
        "self_declared": "Declarada no perfil",
        "project_status_ambiguous": "Projeto com situação não reconhecida",
        "course_status_ambiguous": "Curso com situação não reconhecida",
    }
    result = []
    counts = {}
    for requirement in requirements:
        name = requirement["name"]
        matched = [
            source for source in sources
            if _contains_phrase(source["text"], name)
        ]
        evidence = [
            {
                "source_type": source["source_type"],
                "source_label": source["source_label"],
                "source_id": source["source_id"],
                "excerpt": _excerpt(source["text"], name),
            }
            for source in matched
        ]
        source_types = {item["source_type"] for item in evidence}
        if source_types & evidenced_sources:
            status = "evidenced"
            status_label = "Evidência textual em registro do perfil"
        elif source_types & {"ongoing_project", "ongoing_course"}:
            status = "in_development"
            status_label = "Em desenvolvimento ou aprendizagem"
        elif "self_declared" in source_types:
            status = "declared"
            status_label = "Declarada no perfil"
        elif source_types & {"project_status_ambiguous", "course_status_ambiguous"}:
            status = "ambiguous"
            status_label = "Origem ou situação ambígua"
        elif name in self_assessed:
            status = "self_assessed"
            status_label = "Autoavaliada em desafio"
        else:
            status = "not_identified"
            status_label = "Não identificada nos registros disponíveis"

        if status == "evidenced":
            recommendation = "Revise o registro e, se possível, apresente o artefato ou resultado correspondente."
        elif status == "self_assessed":
            recommendation = "Há autoavaliação registrada; fortaleça-a com artefato e revisão independente."
        elif status == "declared":
            recommendation = "A competência está declarada; adicione um projeto ou exemplo concreto para contextualizá-la."
        elif status == "in_development":
            recommendation = "Conclua a atividade em andamento e registre o resultado como evidência."
        elif requirement["requirement_type"] == "desirable":
            recommendation = "Requisito desejável: avalie desenvolver esta competência; sua ausência não elimina a vaga."
        elif requirement["requirement_type"] == "mandatory":
            recommendation = "Não há evidência identificada no perfil. Confirme sua experiência real antes de decidir; ausência de registro não significa ausência de conhecimento."
        elif status == "ambiguous":
            recommendation = "Revise a situação do registro para esclarecer o contexto desta competência."
        else:
            recommendation = "Verifique a descrição completa e atualize o perfil se houver experiência relevante."

        result.append({
            **requirement,
            "status": status,
            "status_label": status_label,
            "evidence": evidence,
            "recommendation": recommendation,
        })
        counts[status] = counts.get(status, 0) + 1

    return {
        "requirements": result,
        "counts": counts,
        "notice": (
            "O diagnóstico identifica menções e registros textuais; não mede proficiência nem probabilidade de contratação. "
            "A ausência de menção não significa ausência de conhecimento. A classificação obrigatório/desejável é baseada "
            "em marcadores explícitos da descrição e deve ser revisada quando o texto for ambíguo."
        ),
    }
