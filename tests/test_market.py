from jobfinder.market import extract_skills


def names(text):
    return {item["canonical_name"] for item in extract_skills(text)}


def test_aliases_are_normalized_to_one_canonical_skill():
    found = extract_skills("JS, JavaScript, Postgres e PostgreSQL aparecem aqui.")
    assert {item["canonical_name"] for item in found} == {"JavaScript", "PostgreSQL"}


def test_java_does_not_match_inside_javascript():
    assert "Java" not in names("Buscamos pessoa desenvolvedora JavaScript e React.")


def test_repeated_mentions_count_once_per_job():
    found = extract_skills("Python é necessário. Python será usado no backend. PYTHON.")
    assert [item["canonical_name"] for item in found].count("Python") == 1


def test_ambiguous_short_terms_need_context():
    assert "Go" not in names("Go to the office and work with the team.")
    assert "R" not in names("R is the first letter in this sentence.")
    assert "Go" in names("Experiência com Go language é desejável.")
    assert "R" in names("Conhecimento em linguagem R.")


def test_evidence_is_returned_with_source_field():
    found = extract_skills("Experiência com Python e FastAPI.", source_field="description")
    python = next(item for item in found if item["canonical_name"] == "Python")
    assert python["evidence_field"] == "description"
    assert "Python" in python["evidence_text"]
    assert python["extraction_method"] == "dictionary"
