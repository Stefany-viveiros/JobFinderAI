import pytest

from jobfinder.filters import classify_level, dedupe_key, detect_level, is_target_job, normalize_url


@pytest.mark.parametrize("title,expected", [
    ("Estágio em Desenvolvimento de Software", "estagio"),
    ("Estagiário de TI", "estagio"),
    ("Internship Data Analyst", "estagio"),
    ("Desenvolvedor Python Júnior", "junior"),
    ("Vaga Dev Jr React", "junior"),
    ("Senior Python Developer", "outro"),
    ("Desenvolvedor Pleno", "outro"),
    ("Software Engineer", "outro"),
])
def test_detect_level(title, expected):
    assert detect_level(title) == expected


def test_target_requires_tech_area_by_title():
    assert is_target_job({"title": "Estágio em Desenvolvimento Backend"})
    assert not is_target_job({"title": "Estagiário de Produção", "description": "operamos sistemas de TI e data centers"})
    assert not is_target_job({"title": "Junior Sales Engineer"})
    assert classify_level("Estágio em Marketing") == "outro"


def test_url_normalization_ignores_tracking_slash_case_and_fragment():
    a = normalize_url("HTTPS://Exemplo.com/vaga/1/?utm_source=x&id=7#topo")
    b = normalize_url("https://exemplo.com/vaga/1?id=7")
    assert a == b
    assert normalize_url("https://exemplo.com/vaga/1?id=8") != b


def test_dedupe_key_matches_same_job_across_sources_and_skips_unknown_company():
    assert dedupe_key("Estágio Python!", "ACME Ltda.") == dedupe_key("estagio  python", "acme ltda")
    assert dedupe_key("Estágio Python", "ACME") == dedupe_key("Estágio Python", "ACME Ltda")
    assert dedupe_key("Estágio Python", "Empresa não informada") is None
    assert dedupe_key("Estágio Python", "Outra Empresa") != dedupe_key("Estágio Python", "ACME Ltda")


@pytest.mark.parametrize("title", [
    "Estágio Analista de Dados",
    "Júnior Data Analyst",
    "Estágio em Business Intelligence",
    "Analista de BI Júnior",
    "Estágio em QA e Testes de Software",
    "Suporte Técnico Júnior",
    "Estágio em Segurança da Informação",
    "Desenvolvedor RPA Júnior",
])
def test_expanded_technology_roles_are_included(title):
    assert is_target_job({"title": title})


def test_non_technology_roles_are_still_excluded():
    assert not is_target_job({"title": "Estágio em Recursos Humanos"})
    assert not is_target_job({"title": "Analista Financeiro Júnior"})
