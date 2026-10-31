import json
from types import SimpleNamespace

from jobfinder import resume_ai


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "name": "Marina da Silva",
                            "course": "ADS",
                            "technologies": "Python, React",
                            "experience": "",
                            "unexpected_field": "não deve entrar no perfil",
                        })
                    }]
                }
            }]
        }


def test_gemini_extracts_only_allowed_nonempty_fields(monkeypatch):
    monkeypatch.setattr(
        resume_ai,
        "settings",
        SimpleNamespace(gemini_api_key="test-key", gemini_model="gemini-3.8-flash"),
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(resume_ai.requests, "post", fake_post)
    result = resume_ai.analyze_resume_with_gemini("Currículo completo de teste")

    assert result == {
        "name": "Marina da Silva",
        "course": "ADS",
        "technologies": "Python, React",
    }
    assert "Currículo completo de teste" in captured["kwargs"]["json"]["contents"][0]["parts"][0]["text"]
    assert captured["kwargs"]["timeout"] == 60


def test_gemini_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        resume_ai,
        "settings",
        SimpleNamespace(gemini_api_key="", gemini_model="gemini-3.8-flash"),
    )
    try:
        resume_ai.analyze_resume_with_gemini("texto")
    except resume_ai.ResumeAIError as exc:
        assert "GEMINI_API_KEY" in str(exc)
    else:
        raise AssertionError("A ausência da chave deveria gerar erro")
