"""Análise semântica de currículos com a API Gemini."""
from __future__ import annotations

import json
import requests

from .config import settings


PROFILE_FIELDS = {
    "name": "Nome completo, exatamente como aparece no currículo.",
    "course": "Curso ou formação acadêmica.",
    "institution": "Instituição de ensino.",
    "academic_stage": "Período, semestre ou situação acadêmica, somente se informado.",
    "technologies": "Tecnologias, linguagens, frameworks e ferramentas citadas.",
    "skills": "Habilidades técnicas e comportamentais explicitamente descritas.",
    "experience": "Experiências profissionais, atividades, empresas e períodos.",
    "projects": "Projetos acadêmicos ou pessoais e suas tecnologias/objetivos.",
    "certifications": "Cursos, certificações e formações complementares.",
    "keywords": "Palavras-chave profissionais relevantes extraídas do currículo.",
}

RECORD_FIELDS = {
    "educations": {
        "course": "Nome do curso ou formação.",
        "institution": "Instituição de ensino.",
        "degree": "Nível: tecnólogo, bacharelado, licenciatura, pós-graduação etc.",
        "status": "Em andamento, concluído ou trancado, somente se explícito.",
        "start_date": "Data ou ano de início, como escrito.",
        "end_date": "Data ou ano de conclusão ou previsão, como escrito.",
        "description": "Detalhes relevantes explicitamente informados.",
    },
    "experiences": {
        "company": "Nome da empresa ou organização.",
        "role": "Cargo ou função.",
        "employment_type": "Tipo de vínculo, se informado.",
        "location": "Localidade, se informada.",
        "start_date": "Data ou ano de início.",
        "end_date": "Data ou ano de término.",
        "is_current": "true somente se o currículo indicar que é atual.",
        "description": "Atividades e responsabilidades descritas.",
    },
    "courses": {
        "name": "Nome do curso livre ou formação complementar.",
        "provider": "Instituição ou plataforma que ofereceu.",
        "workload": "Carga horária como escrita.",
        "completed_at": "Data de conclusão, se informada.",
        "status": "Concluído ou em andamento, somente se explícito.",
        "credential_url": "URL da credencial, se houver.",
    },
    "certifications_items": {
        "name": "Nome da certificação.",
        "issuer": "Entidade emissora.",
        "issued_at": "Data de emissão.",
        "expires_at": "Data de validade.",
        "credential_id": "Identificador da credencial.",
        "credential_url": "URL da credencial.",
    },
    "portfolio_projects": {
        "name": "Nome do projeto acadêmico ou pessoal.",
        "description": "Objetivo e funcionalidades descritos.",
        "technologies": "Tecnologias explicitamente utilizadas.",
        "repository_url": "URL do repositório.",
        "demo_url": "URL da demonstração.",
        "status": "Status do projeto, somente se informado.",
    },
}
RECORD_SCHEMA = {
    "educations": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {k: {"type": "STRING"} for k in RECORD_FIELDS["educations"]}}},
    "experiences": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {**{k: {"type": "STRING"} for k in RECORD_FIELDS["experiences"] if k != "is_current"}, "is_current": {"type": "BOOLEAN"}}}},
    "courses": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {k: {"type": "STRING"} for k in RECORD_FIELDS["courses"]}}},
    "certifications_items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {k: {"type": "STRING"} for k in RECORD_FIELDS["certifications_items"]}}},
    "portfolio_projects": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {k: {"type": "STRING"} for k in RECORD_FIELDS["portfolio_projects"]}}},
}

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        **{key: {"type": "STRING", "description": description} for key, description in PROFILE_FIELDS.items()},
        **RECORD_SCHEMA,
    },
    "required": [*PROFILE_FIELDS.keys(), *RECORD_FIELDS.keys()],
}


class ResumeAIError(Exception):
    """Falha ao analisar o currículo com o provedor de IA."""


def analyze_resume_with_gemini(resume_text: str) -> dict:
    if not settings.gemini_api_key:
        raise ResumeAIError("A chave GEMINI_API_KEY não está configurada no ambiente do servidor.")

    prompt = (
        "Você é um analisador rigoroso de currículos para preenchimento de perfil profissional. "
        "Leia TODO o currículo abaixo e extraia os dados solicitados. "
        "Regras obrigatórias: não invente nem deduza experiência, tecnologias, cursos, datas, "
        "instituições ou competências; não transforme objetivo profissional em experiência; "
        "não confunda projetos com empregos; preserve nomes e períodos como escritos. "
        "Se uma informação não estiver explícita, não a invente nem a complete. "
        "Retorne TODAS as formações, experiências, cursos, certificações e projetos como "
        "itens separados nos respectivos arrays; nunca una registros diferentes em um único item. "
        "Não classifique curso livre como graduação nem certificação como curso sem evidência. "
        "Preserve status e períodos como escritos. "
        "Responda somente no formato JSON solicitado.\n\n"
        "CURRÍCULO COMPLETO:\n" + resume_text
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{settings.gemini_model}:generateContent"
    )
    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA,
                    "temperature": 0.1,
                },
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or []
        raw = next((part.get("text") for part in parts if part.get("text")), "")
        if not raw:
            raise ResumeAIError("O Gemini não retornou conteúdo para análise.")
        extracted = json.loads(raw)
    except ResumeAIError:
        raise
    except requests.Timeout as exc:
        raise ResumeAIError("O Gemini demorou demais para analisar o currículo. Tente novamente.") from exc
    except requests.RequestException as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            try:
                detail = exc.response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                pass
        raise ResumeAIError(detail or "Não foi possível conectar à API do Gemini.") from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ResumeAIError("A resposta do Gemini veio em um formato inesperado.") from exc

    if not isinstance(extracted, dict):
        raise ResumeAIError("A resposta do Gemini não contém um objeto de perfil válido.")

    # Lista permitida: nenhum campo inesperado pode chegar ao perfil.
    result = {
        key: str(extracted.get(key) or "").strip()
        for key in PROFILE_FIELDS
        if str(extracted.get(key) or "").strip()
    }
    for collection, allowed_fields in RECORD_FIELDS.items():
        raw_items = extracted.get(collection)
        if not isinstance(raw_items, list):
            continue
        items = []
        for raw_item in raw_items[:100]:
            if not isinstance(raw_item, dict):
                continue
            item = {}
            for field in allowed_fields:
                value = raw_item.get(field)
                if field == "is_current":
                    item[field] = value is True
                elif isinstance(value, (str, int, float)):
                    item[field] = str(value).strip()
                else:
                    item[field] = ""
            if any(value is True or (isinstance(value, str) and value) for value in item.values()):
                items.append(item)
        if items:
            result[collection] = items
    return result
