"""Taxonomia determinística e extração auditável de competências em vagas.

A presença de um termo é evidência textual, não prova de domínio ou proficiência.
"""
import re
from .matching import normalize


# Termos ambíguos (Go, R, C, .NET) só são aceitos com limites/contexto explícitos.
SKILL_CATALOG = [
    {"name": "Python", "category": "language", "aliases": ["python"]},
    {"name": "JavaScript", "category": "language", "aliases": ["javascript", "java script", "js", "ecmascript"]},
    {"name": "TypeScript", "category": "language", "aliases": ["typescript", "ts"]},
    {"name": "Java", "category": "language", "aliases": ["java"]},
    {"name": "C#", "category": "language", "aliases": ["c#", "c sharp"]},
    {"name": "C++", "category": "language", "aliases": ["c++", "cpp"]},
    {"name": "PHP", "category": "language", "aliases": ["php"]},
    {"name": "Ruby", "category": "language", "aliases": ["ruby"]},
    {"name": "Kotlin", "category": "language", "aliases": ["kotlin"]},
    {"name": "Swift", "category": "language", "aliases": ["swift"]},
    {"name": "Go", "category": "language", "aliases": ["golang", "go language"]},
    {"name": "R", "category": "language", "aliases": ["r language", "linguagem r"]},
    {"name": "React", "category": "framework", "aliases": ["react", "react.js", "reactjs"]},
    {"name": "Angular", "category": "framework", "aliases": ["angular", "angular.js", "angularjs"]},
    {"name": "Vue.js", "category": "framework", "aliases": ["vue", "vue.js", "vuejs"]},
    {"name": "Node.js", "category": "framework", "aliases": ["node", "node.js", "nodejs"]},
    {"name": "FastAPI", "category": "framework", "aliases": ["fastapi"]},
    {"name": "Django", "category": "framework", "aliases": ["django"]},
    {"name": "Flask", "category": "framework", "aliases": ["flask"]},
    {"name": "Spring Boot", "category": "framework", "aliases": ["spring boot", "springboot"]},
    {"name": "Laravel", "category": "framework", "aliases": ["laravel"]},
    {"name": "Flutter", "category": "framework", "aliases": ["flutter"]},
    {"name": "Pandas", "category": "library", "aliases": ["pandas"]},
    {"name": "NumPy", "category": "library", "aliases": ["numpy"]},
    {"name": "TensorFlow", "category": "library", "aliases": ["tensorflow"]},
    {"name": "PyTorch", "category": "library", "aliases": ["pytorch"]},
    {"name": "SQL", "category": "database", "aliases": ["sql"]},
    {"name": "PostgreSQL", "category": "database", "aliases": ["postgresql", "postgres", "postgre sql"]},
    {"name": "MySQL", "category": "database", "aliases": ["mysql"]},
    {"name": "SQLite", "category": "database", "aliases": ["sqlite"]},
    {"name": "MongoDB", "category": "database", "aliases": ["mongodb", "mongo db"]},
    {"name": "Redis", "category": "database", "aliases": ["redis"]},
    {"name": "AWS", "category": "cloud", "aliases": ["aws", "amazon web services"]},
    {"name": "Azure", "category": "cloud", "aliases": ["azure", "microsoft azure"]},
    {"name": "Google Cloud", "category": "cloud", "aliases": ["google cloud", "gcp"]},
    {"name": "Docker", "category": "tool", "aliases": ["docker"]},
    {"name": "Kubernetes", "category": "tool", "aliases": ["kubernetes", "k8s"]},
    {"name": "Git", "category": "tool", "aliases": ["git"]},
    {"name": "GitHub", "category": "tool", "aliases": ["github", "git hub"]},
    {"name": "Linux", "category": "tool", "aliases": ["linux"]},
    {"name": "Power BI", "category": "tool", "aliases": ["power bi", "powerbi"]},
    {"name": "Excel", "category": "tool", "aliases": ["excel", "microsoft excel"]},
    {"name": "Machine Learning", "category": "practice", "aliases": ["machine learning", "aprendizado de maquina"]},
    {"name": "REST API", "category": "practice", "aliases": ["rest api", "api rest", "apis rest"]},
    {"name": "HTML", "category": "web", "aliases": ["html", "html5"]},
    {"name": "CSS", "category": "web", "aliases": ["css", "css3"]},
]

# Aliases genéricos são desativados aqui e só aceitos em expressões não ambíguas.
AMBIGUOUS_ALIASES = {"go", "r", "c", ".net", "node"}


def _pattern(alias):
    escaped = re.escape(normalize(alias))
    return re.compile(r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])")


def _evidence(text, start, end, radius=90):
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return " ".join(text[left:right].split())[:220]


def extract_skills(text, source_field="description"):
    """Retorna uma ocorrência por competência canônica, com trecho de evidência."""
    original = str(text or "")
    normalized = normalize(original)
    found = {}

    for skill in SKILL_CATALOG:
        matches = []
        for alias in skill["aliases"]:
            if alias in AMBIGUOUS_ALIASES:
                continue
            for match in _pattern(alias).finditer(normalized):
                matches.append(match)

        # Aliases curtos e ambíguos só são aceitos em construções explícitas.
        for alias in skill["aliases"]:
            if alias == "go":
                patterns = [r"\bgo\s+(?:language|programming|programming language)\b",
                            r"\blinguagem\s+go\b"]
            elif alias == "r":
                patterns = [r"\br\s+(?:language|programming|programming language)\b",
                            r"\blinguagem\s+r\b"]
            elif alias == "node":
                patterns = [r"\bnode\s*\.\s*js\b", r"\bnodejs\b"]
            else:
                patterns = []
            for pattern in patterns:
                matches.extend(re.finditer(pattern, normalized))

        if not matches:
            continue
        match = max(matches, key=lambda item: (item.end() - item.start()))
        found[skill["name"]] = {
            "canonical_name": skill["name"],
            "category": skill["category"],
            "evidence_text": _evidence(original, match.start(), match.end()),
            "evidence_field": source_field,
            "extraction_method": "dictionary",
            "confidence": 1.0,
        }

    return sorted(found.values(), key=lambda item: (item["category"], item["canonical_name"]))


def taxonomy_version():
    """Versão inicial da taxonomia; deve ser incrementada quando aliases/regras mudarem."""
    return "2026-10-01"
