import pytest
import requests

from jobfinder import sources


class FakeResponse:
    def __init__(self, json_data=None, text=""):
        self._json, self.text = json_data, text

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
    assert set(sources.LINK_ONLY_SOURCES) == {"Indeed", "Vagas.com"}
    assert "Indeed" not in sources.SOURCES and "Vagas.com" not in sources.SOURCES
    assert all(not sources.SOURCE_INFO[n]["apply_api"] for n in sources.SOURCE_INFO)
    links = sources.external_search_links(["estágio python"])
    assert {l["source"] for l in links} == {"Indeed", "Vagas.com"}
    assert all(l["url"].startswith("https://") for l in links)
