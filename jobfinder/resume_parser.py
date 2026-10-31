"""Extração conservadora de informações de currículos PDF e DOCX."""
from __future__ import annotations

import io
import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader


MAX_TEXT_CHARS = 60_000
TECHNOLOGIES = [
    "Python", "JavaScript", "TypeScript", "Java", "C#", "PHP", "C++", "C",
    "React", "Angular", "Vue", "Node.js", "FastAPI", "Django", "Flask",
    "HTML5", "HTML", "CSS3", "CSS", "SQL", "MySQL", "PostgreSQL", "SQLite",
    "MongoDB", "Git", "GitHub", "Docker", "AWS", "Azure", "Google Cloud",
    "Power BI", "Excel", "TensorFlow", "PyTorch", "Linux",
]


def _read_text(content: bytes, suffix: str) -> str:
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("O PDF está protegido por senha. Envie uma cópia desbloqueada.")
        pages = []
        for page in reader.pages[:30]:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)
    if suffix == ".docx":
        document = Document(io.BytesIO(content))
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    raise ValueError("Formato não suportado. Envie um arquivo PDF ou DOCX.")


def _section(text: str, headings: tuple[str, ...]) -> str:
    lines = text.splitlines()
    start = None
    stop_words = (
        "formação", "educação", "experiência", "histórico profissional",
        "projetos", "habilidades", "competências", "certificações", "cursos",
        "idiomas", "contato", "objetivo",
    )
    for index, line in enumerate(lines):
        normalized = re.sub(r"[^a-zá-ú ]", "", line.lower()).strip()
        if any(h in normalized for h in headings):
            start = index + 1
            break
    if start is None:
        return ""
    collected = []
    for line in lines[start:]:
        normalized = re.sub(r"[^a-zá-ú ]", "", line.lower()).strip()
        if normalized and any(w in normalized for w in stop_words):
            break
        if line.strip():
            collected.append(line.strip())
    return "\n".join(collected).strip()


def extract_resume_text(content: bytes, filename: str) -> str:
    """Extrai o texto integral do currículo para análise semântica por IA."""
    suffix = Path(filename or "").suffix.lower()
    text = _read_text(content, suffix)
    text = re.sub(r"[ \t]+", " ", text)
    text = text[:MAX_TEXT_CHARS]
    if len(text.strip()) < 20:
        raise ValueError(
            "Não foi possível extrair texto. O arquivo pode ser uma digitalização; "
            "tente um PDF pesquisável ou DOCX."
        )
    return text


def _section_lines(text: str, headings: tuple[str, ...]) -> list[str]:
    lines = text.splitlines()
    stop_words = (
        "formação", "educação", "experiência", "histórico profissional",
        "projetos", "habilidades", "competências", "certificações", "cursos",
        "idiomas", "contato", "objetivo",
    )
    start = None
    for index, line in enumerate(lines):
        normalized = re.sub(r"[^a-zá-ú ]", "", line.lower()).strip()
        if any(h in normalized for h in headings):
            start = index + 1
            break
    if start is None:
        return []
    result = []
    for line in lines[start:]:
        normalized = re.sub(r"[^a-zá-ú ]", "", line.lower()).strip()
        if normalized and any(w in normalized for w in stop_words):
            break
        if line.strip():
            result.append(line.strip(" •-\t"))
    return result


def parse_resume(content: bytes, filename: str) -> dict:
    suffix = Path(filename or "").suffix.lower()
    text = _read_text(content, suffix)
    text = re.sub(r"[ \t]+", " ", text)
    text = text[:MAX_TEXT_CHARS]
    if len(text.strip()) < 20:
        raise ValueError("Não foi possível extrair texto. O arquivo pode ser uma digitalização; tente um PDF pesquisável ou DOCX.")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result: dict[str, str] = {}

    email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone = re.search(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-. ]?\d{4}", text)
    if lines and len(lines[0]) <= 90 and not re.search(r"@|https?://|\d{4}", lines[0]):
        result["name"] = lines[0]
    found_tech = []
    lower_text = text.lower()
    for tech in TECHNOLOGIES:
        clean = tech.strip()
        if clean and re.search(r"(?<![\w+#])" + re.escape(clean.lower()) + r"(?![\w+#])", lower_text):
            if clean not in found_tech:
                found_tech.append(clean)
    if found_tech:
        result["technologies"] = ", ".join(found_tech)

    education = _section(text, ("formação acadêmica", "formação", "educação"))
    experience = _section(text, ("experiência profissional", "experiência", "histórico profissional"))
    projects = _section(text, ("projetos", "portfólio"))
    skills = _section(text, ("habilidades técnicas", "habilidades", "competências"))
    certifications = _section(text, ("certificações", "cursos"))
    if education:
        result["course"] = education[:200]
        education_lines = _section_lines(text, ("formação acadêmica", "formação", "educação"))
        records = []
        for line in education_lines:
            parts = [part.strip() for part in re.split(r"\s+[|–—-]\s+", line) if part.strip()]
            if parts:
                records.append({
                    "course": parts[0][:200],
                    "institution": parts[1][:200] if len(parts) > 1 else "",
                    "degree": "",
                    "status": "",
                    "start_date": "",
                    "end_date": "",
                    "description": "",
                })
        if records:
            result["educations"] = records
    if experience:
        result["experience"] = experience[:5000]
    if projects:
        result["projects"] = projects[:5000]
        project_lines = _section_lines(text, ("projetos", "portfólio"))
        if project_lines:
            result["portfolio_projects"] = [
                {"name": line[:220], "description": "", "technologies": "", "repository_url": "", "demo_url": "", "status": ""}
                for line in project_lines
            ]
    if skills:
        result["skills"] = skills[:3000]
    if certifications:
        result["certifications"] = certifications[:3000]
        course_lines = _section_lines(text, ("cursos", "cursos complementares"))
        if course_lines:
            result["courses"] = [
                {"name": line[:220], "provider": "", "workload": "", "completed_at": "", "status": "", "credential_url": ""}
                for line in course_lines
            ]
        certification_lines = _section_lines(text, ("certificações", "certificados"))
        if certification_lines:
            result["certifications_items"] = [
                {"name": line[:220], "issuer": "", "issued_at": "", "expires_at": "", "credential_id": "", "credential_url": ""}
                for line in certification_lines
            ]
    # O texto original nunca é gravado automaticamente: os campos extraídos
    # são sugestões que a pessoa revisa antes de salvar o perfil.
    return result
