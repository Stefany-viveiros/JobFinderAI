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

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        key: {"type": "STRING", "description": description}
        for key, description in PROFILE_FIELDS.items()
    },
    "required": list(PROFILE_FIELDS.keys()),
}


class ResumeAIError(Exception):
    """Falha ao analisar o currículo com o provedor de IA."""


def analyze_resume_with_gemini(resume_text: str) -> dict[str, str]:
    if not settings.gemini_api_key:
        raise ResumeAIError("A chave GEMINI_API_KEY não está configurada no ambiente do servidor.")

    prompt = (
        "Você é um analisador rigoroso de currículos para preenchimento de perfil profissional. "
        "Leia TODO o currículo abaixo e extraia os dados solicitados. "
        "Regras obrigatórias: não invente nem deduza experiência, tecnologias, cursos, datas, "
        "instituições ou competências; não transforme objetivo profissional em experiência; "
        "não confunda projetos com empregos; preserve nomes e períodos como escritos. "
        "Se uma informação não estiver explícita, retorne string vazia. "
        "Resuma cada seção com fidelidade, mantendo detalhes úteis e tecnologias. "
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
            params={"key": settings.gemini_api_key},
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
    return {
        key: str(extracted.get(key) or "").strip()
        for key in PROFILE_FIELDS
        if str(extracted.get(key) or "").strip()
    }
