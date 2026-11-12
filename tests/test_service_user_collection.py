from sqlalchemy import select

from jobfinder.models import Job, JobMatch
from jobfinder.service import collect_for_user


def test_collect_for_user_deduplicates_tracking_variants(db, test_user, ready_profile):
    result = collect_for_user(
        db,
        [
            {
                "source": "Fonte A",
                "source_id": "a-1",
                "title": "Estágio Backend Python",
                "company": "Empresa Exemplo",
                "description": "Desenvolvimento com Python e FastAPI",
                "location": "Remoto",
                "modality": "Remoto",
                "job_type": "Estágio",
                "published_at": "2026-11-12",
                "url": "https://empresas.example/vaga/123?utm_source=feed",
            },
            {
                "source": "Fonte B",
                "source_id": "b-9",
                "title": "Estágio Backend Python — mesma vaga em outra fonte",
                "company": "Outra empresa",
                "description": "Vaga duplicada com URL canônica equivalente",
                "location": "Brasil",
                "modality": "Não informada",
                "job_type": "Estágio",
                "published_at": "2026-11-12",
                "url": "https://EMPRESAS.example/vaga/123#candidatar",
            },
        ],
        user_id=test_user.id,
        only_target=True,
    )

    jobs = db.scalars(select(Job)).all()
    matches = db.scalars(
        select(JobMatch).where(JobMatch.user_id == test_user.id)
    ).all()

    assert result["saved"] == 1
    assert result["duplicates"] == 1
    assert len(jobs) == 1
    assert len(matches) == 1
