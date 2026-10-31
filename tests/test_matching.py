from types import SimpleNamespace
from jobfinder.matching import score_job


def profile(**kwargs):
    base=dict(technologies="Python, FastAPI",skills="",keywords="",interests="Backend, Estágio",modality="Remoto",location="Brasil",exclude_terms="",weight_keywords=40,weight_area=25,weight_modality=15,weight_location=10,weight_level=10)
    base.update(kwargs); return SimpleNamespace(**base)


def test_matching_is_explainable_and_bounded():
    score,matched,missing=score_job(dict(title="Python Backend Intern",description="FastAPI remote internship",location="Remote",modality="Remoto"),profile())
    assert 0 <= score <= 100
    assert matched
    assert isinstance(missing,list)


def test_excluded_term_blocks_job():
    score,matched,missing=score_job(dict(title="Python Backend Crypto",description="",location="Remote",modality="Remoto"),profile(exclude_terms="crypto"))
    assert score==0
    assert any("excluídos" in x for x in missing)


def test_java_does_not_match_inside_javascript():
    score, matched, missing = score_job(
        {"title": "Estágio Frontend", "description": "JavaScript, React e CSS"},
        profile(technologies="Java"),
    )
    assert not any("Java" in reason for reason in matched)
    assert any("Nenhuma tecnologia" in reason for reason in missing)


def test_missing_mandatory_technology_blocks_preparation_score():
    score, matched, missing = score_job(
        {
            "title": "Estágio Backend Python",
            "description": "Requisito obrigatório: Java. Python é desejável.",
            "location": "Brasil",
            "modality": "Remoto",
            "job_type": "Estágio",
        },
        profile(),
    )
    assert score <= 49
    assert any("obrigatório(s) não identificado(s)" in reason and "java" in reason for reason in missing)


def test_project_technology_counts_as_profile_evidence():
    project_profile = profile(
        technologies="",
        projects="BS Construtora: projeto Full Stack com React, FastAPI e Python.",
    )
    score, matched, missing = score_job(
        {"title": "Estágio Backend Python", "description": "Python, FastAPI e React"},
        project_profile,
    )
    assert any("Tecnologias do perfil" in reason for reason in matched)
    assert score > 0
