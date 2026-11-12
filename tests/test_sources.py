import pytest
import requests

from jobfinder import sources


class FakeResponse:
    def __init__(self, json_data=None, text=""):
        self._json, self.text = json_data, text
        self.content = text.encode("utf-8")

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def test_remotive_is_normalized(monkeypatch):
    payload = {"jobs": [{"id": 7, "url": "https://remotive.com/j/7", "title": "Junior Python Dev",
                         "company_name": "ACME", "description": "<p>Python</p>", "job_type": "full_time",
                         "candidate_required_location": "Brazil", "publication_date": "2026-10-01"},
                        {"id": 8, "title": "sem url"}]}
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload))
    jobs = sources.fetch_remotive()
    assert len(jobs) == 1 and jobs[0]["source"] == "Remotive" and jobs[0]["modality"] == "Remoto"
    assert jobs[0]["url"] == "https://remotive.com/j/7"


def test_arbeitnow_is_normalized(monkeypatch):
    payload = {"data": [{"slug": "s1", "url": "https://arbeitnow.com/s1", "title": "Intern", "company_name": "X",
                         "remote": True, "job_types": ["Internship"], "location": "Berlin"}]}
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload))
    job = sources.fetch_arbeitnow()[0]
    assert job["job_type"] == "Internship" and job["modality"] == "Remoto"


NERDIN_HTML = """
<div class="vaga-card" data-href="vaga-123.php">
  <div class="vaga-titulo">Estágio em Desenvolvimento <span class="vaga-nova-badge">Nova</span></div>
  <div class="vaga-empresa-nome">Empresa X</div><div class="vaga-local-linha">Home office</div>
  <div class="vaga-resumo-linha">Estágio • 6h/dia</div><time datetime="2026-10-20"></time>
  <div class="vaga-hashtags"><a>#python</a></div></div>
<div class="vaga-card" data-href="vaga-124.php"><div class="vaga-titulo">Estágio em Direito</div></div>
"""


def test_nerdin_parser_keeps_only_tech_cards(monkeypatch):
    # HTML sintético que segue os seletores usados pelo código; não é uma captura do site real.
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(text=NERDIN_HTML))
    jobs = sources.fetch_nerdin()
    assert [j["title"] for j in jobs] == ["Estágio em Desenvolvimento"]
    assert jobs[0]["modality"] == "Remoto" and jobs[0]["source_id"] == "123"


def test_one_failing_source_does_not_break_collection(monkeypatch):
    monkeypatch.setitem(sources.SOURCES, "Quebrada", lambda: (_ for _ in ()).throw(RuntimeError("fora do ar")))
    monkeypatch.setitem(sources.SOURCES, "Boa", lambda: [{"url": "https://ok.test/1", "title": "t"}])
    items, errors = sources.collect_selected(["Quebrada", "Boa"])
    assert len(items) == 1 and "Quebrada" in errors[0] and "fora do ar" in errors[0]


def test_indeed_and_vagascom_are_link_only_and_never_fetched():
    assert {"Indeed", "Vagas.com", "LinkedIn", "Gupy", "InfoJobs", "CIEE", "Nube"} <= set(sources.LINK_ONLY_SOURCES)
    assert all(name not in sources.SOURCES for name in sources.LINK_ONLY_SOURCES)
    assert all(not sources.SOURCE_INFO[n]["apply_api"] for n in sources.SOURCE_INFO)
    links = sources.external_search_links(["estágio python"])
    assert {"Indeed", "Vagas.com", "LinkedIn", "Gupy", "InfoJobs"} <= {l["source"] for l in links}
    assert all(l["url"].startswith("https://") for l in links)


def test_brazilian_portal_catalog_is_link_only_and_never_claims_auto_apply():
    expected = {
        "LinkedIn", "Gupy", "InfoJobs", "Catho", "Sólides Vagas",
        "Trabalha Brasil", "Empregos.com.br", "Glassdoor", "Jooble",
        "CIEE", "Nube", "Companhia de Estágios", "99jobs", "GeekHunter",
        "Programathor", "Trampos", "Remotar", "Emprega Brasil / SINE",
    }
    assert expected <= set(sources.SOURCE_INFO)
    for name in expected:
        assert sources.SOURCE_INFO[name]["mode"] == "link_only"
        assert sources.SOURCE_INFO[name]["search_api"] is False
        assert sources.SOURCE_INFO[name]["apply_api"] is False


def test_empregare_public_api_is_normalized_and_deduplicated(monkeypatch):
    payload = {
        "sucesso": True,
        "model": {
            "totalPaginas": 1,
            "dados": [{
                "id": 42, "url": "/v42", "titulo": "Estágio em Desenvolvimento",
                "chamada": "Atuação com Python", "empresa": "Empresa Y",
                "nivel": "Estágio", "trabalhoRemoto": True,
                "trabalhoRemotoTexto": "Trabalho remoto", "cidades": ["São Paulo"],
                "timestamp": 1794000000,
            }],
        },
    }
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: (calls.append(k) or FakeResponse(payload)))
    jobs = sources.fetch_empregare()
    assert len(jobs) == 1
    assert jobs[0]["source"] == "Empregare"
    assert jobs[0]["source_id"] == "42"
    assert jobs[0]["url"] == "https://www.empregare.com/v42"
    assert jobs[0]["modality"] == "Remoto"
    assert jobs[0]["job_type"] == "Estágio"
    assert len(calls) == 2
    assert calls[0]["params"]["ItensPagina"] == 30


def test_empregando_brasil_xml_feed_is_normalized(monkeypatch):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <jobs><job><id>abc-1</id><title>Estágio Python</title>
    <url>https://empregandobrasil.com.br/vaga/abc-1</url><company>Empresa Z</company>
    <city>São Paulo</city><state>SP</state><published>2026-11-10</published>
    <description><![CDATA[<p>Desenvolvimento com <b>Python</b>.</p>]]></description>
    </job></jobs>"""
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(text=xml))
    jobs = sources.fetch_empregando_brasil()
    assert len(jobs) == 1
    assert jobs[0]["source"] == "Empregando Brasil"
    assert jobs[0]["location"] == "São Paulo, SP"
    assert jobs[0]["description"] == "Desenvolvimento com Python ."
    assert jobs[0]["published_at"] == "2026-11-10"


def test_empregando_brasil_rejects_oversized_feed(monkeypatch):
    response = FakeResponse(text="<jobs/>")
    response.content = b"x" * (8 * 1024 * 1024 + 1)
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)
    with pytest.raises(ValueError, match="8 MB"):
        sources.fetch_empregando_brasil()
