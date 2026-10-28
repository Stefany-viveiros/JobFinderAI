import json

from jobfinder.load_profile import load_profile
from jobfinder.service import get_profile


def test_load_profile_validates_saves_and_rescores(db, tmp_path):
    from tests.conftest import make_job
    job = make_job(db, title="Estágio Python", description="Python", compatibility=0)
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"name": "Ana", "technologies": "Python", "interests": "Estágio"}), encoding="utf-8")
    load_profile(str(f))
    db.expire_all()
    assert get_profile(db).name == "Ana"
    db.refresh(job)
    assert job.compatibility > 0
