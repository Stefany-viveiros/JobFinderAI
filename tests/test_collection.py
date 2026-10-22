from types import SimpleNamespace

from jobfinder.service import prepare_ranked_items


def profile():
    return SimpleNamespace(
        technologies="Python, FastAPI",
        skills="",
        keywords="",
        interests="Backend, Estágio",
        modality="Remoto",
        location="Brasil",
        exclude_terms="",
        weight_keywords=40,
        weight_area=25,
        weight_modality=15,
        weight_location=10,
        weight_level=10,
    )


def test_collection_removes_duplicates_and_respects_limit():
    items = [
        {
            "url": "https://example.com/low",
            "title": "Outra oportunidade",
            "description": "Vaga sem tecnologias específicas",
            "modality": "Presencial",
            "location": "Portugal",
        },
        {
            "url": "https://example.com/python",
            "title": "Estágio Python Backend",
            "description": "Python FastAPI internship remote",
            "modality": "Remoto",
            "location": "Brasil",
        },
        {
            "url": "https://example.com/python/",
            "title": "Cópia da oportunidade",
            "description": "Python FastAPI",
        },
        {
            "url": "https://example.com/existing",
            "title": "Vaga já salva",
            "description": "Python Backend",
        },
    ]

    ranked, duplicates, eligible = prepare_ranked_items(
        items,
        profile(),
        existing_urls=["https://example.com/existing"],
        limit=1,
    )

    assert len(ranked) == 1
    assert ranked[0]["item"]["url"] == "https://example.com/python"
    assert duplicates == 2
    assert eligible == 2


def test_collection_caps_limit_at_80():
    items = [
        {
            "url": f"https://example.com/{i}",
            "title": "Python Backend Internship",
            "description": "Python FastAPI remote internship",
            "modality": "Remoto",
            "location": "Brasil",
        }
        for i in range(100)
    ]

    ranked, duplicates, eligible = prepare_ranked_items(
        items, profile(), limit=80
    )

    assert len(ranked) == 80
    assert duplicates == 0
    assert eligible == 100
