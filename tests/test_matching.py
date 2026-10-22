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
