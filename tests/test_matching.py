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


def test_matching_includes_technologies_from_structured_projects_and_education():
    project = SimpleNamespace(technologies="React, PostgreSQL")
    education = SimpleNamespace(course="Engenharia da Computação")
    score, matched, missing = score_job(
        {"title": "Estágio React Developer", "description": "React and PostgreSQL", "location": "Remote", "modality": "Remoto"},
        profile(technologies="", skills="", keywords="", portfolio_projects=[project], educations=[education]),
    )
    assert score > 0
    assert any("react" in item or "postgresql" in item for item in matched)



def test_requirement_diagnosis_separates_required_desirable_and_evidence_origins():
    from jobfinder.matching import diagnose_job_requirements

    completed_project = SimpleNamespace(
        id=17,
        name="API de catálogo",
        description="Serviço desenvolvido com React e PostgreSQL.",
        technologies="React, PostgreSQL",
        status="Concluído",
    )
    profile_data = profile(
        technologies="Python",
        skills="",
        keywords="",
        portfolio_projects=[completed_project],
        experiences=[],
        courses=[],
        certifications_items=[],
        educations=[],
        experience="",
        projects="",
        certifications="",
    )
    result = diagnose_job_requirements(
        "Python é obrigatório. React é desejável. Docker é necessário para a função.",
        profile_data,
    )
    by_name = {item["name"]: item for item in result["requirements"]}

    assert by_name["python"]["requirement_type"] == "mandatory"
    assert by_name["python"]["status"] == "declared"
    assert by_name["react"]["requirement_type"] == "desirable"
    assert by_name["react"]["status"] == "evidenced"
    assert by_name["react"]["evidence"][0]["source_type"] == "completed_project"
    assert by_name["react"]["evidence"][0]["source_id"] == 17
    assert by_name["docker"]["requirement_type"] == "mandatory"
    assert by_name["docker"]["status"] == "not_identified"
    assert "não significa ausência de conhecimento" in result["notice"]


def test_requirement_diagnosis_does_not_confuse_java_and_javascript():
    from jobfinder.matching import diagnose_job_requirements

    result = diagnose_job_requirements(
        "JavaScript é obrigatório para esta oportunidade.",
        profile(technologies="Java", skills="", keywords=""),
    )
    assert len(result["requirements"]) == 1
    assert result["requirements"][0]["name"] == "javascript"
    assert result["requirements"][0]["status"] == "not_identified"


def test_requirement_classifier_marks_conflicting_language_as_ambiguous():
    from jobfinder.matching import classify_job_requirements

    result = classify_job_requirements(
        "Python é obrigatório e também listado como desejável nesta vaga."
    )
    assert result[0]["name"] == "python"
    assert result[0]["requirement_type"] == "ambiguous"

def test_requirement_diagnosis_ignores_human_dismissed_evidence():
    from jobfinder.matching import diagnose_job_requirements

    project = SimpleNamespace(
        id=91,
        name="API",
        description="Projeto construído com React.",
        technologies="React",
        status="Concluído",
    )
    result = diagnose_job_requirements(
        "React é desejável.",
        profile(
            technologies="",
            skills="",
            keywords="",
            portfolio_projects=[project],
            experiences=[],
            courses=[],
            certifications_items=[],
            educations=[],
            experience="",
            projects="",
            certifications="",
        ),
        dismissed_evidence_keys={("portfolio_project:91", "react")},
    )
    requirement = result["requirements"][0]
    assert requirement["name"] == "react"
    assert requirement["status"] == "not_identified"
    assert requirement["evidence"] == []
