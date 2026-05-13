from src.services.utils import build_taxonomy_context, _coerce_to_str, _clean_llm_json, _chunk_text, _build_distilled_content


def test_build_taxonomy_context():
    items = [
        {"id": 1, "name": "Language", "parent_id": None},
        {"id": 2, "name": "Python", "parent_id": 1, "aliases": "py, python3"},
        {"id": 3, "name": "Java", "parent_id": 1}
    ]

    text, parents, leaves = build_taxonomy_context(items)
    assert parents == 1
    assert leaves == 2
    assert "Python, py, python3, Java" in text
    assert "Language" not in text


def test_coerce_to_str_dict():
    val1 = {"summary": "My Summary"}
    assert _coerce_to_str(val1) == "My Summary"

    val2 = {"other": "value"}
    assert _coerce_to_str(val2) == '{"other": "value"}'


def test_coerce_to_str_list():
    val = ["A", "B"]
    assert _coerce_to_str(val) == "A\nB"


def test_clean_llm_json_markdown():
    text = "```json\n{\"test\": 1}\n```"
    assert _clean_llm_json(text) == '{"test": 1}'

    text2 = "```\n{\"test\": 1}\n```"
    assert _clean_llm_json(text2) == '{"test": 1}'

    text3 = "{\"test\": 1,}"
    assert _clean_llm_json(text3) == '{"test": 1}'

    text4 = "[\"test\",]"
    assert _clean_llm_json(text4) == '["test"]'


def test_chunk_text_empty():
    assert _chunk_text("") == []


def test_chunk_text_short():
    assert _chunk_text("short test") == ["short test"]


def test_chunk_text_long():
    text = " ".join(["word"] * 200)
    chunks = _chunk_text(text, chunk_size=150, overlap=20)
    assert len(chunks) == 2
    assert len(chunks[0].split()) == 150
    assert len(chunks[1].split()) == 70


def test_build_distilled_content():
    cv = {
        "current_role": "Dev",
        "years_of_experience": 5,
        "summary": "Summary",
        "competencies": [{"name": "Java"}],
        "educations": [{"degree": "BSc", "school": "MIT"}],
        "missions": [{"title": "Dev", "company": "Zenika", "skills": ["Java"]}]
    }

    distilled = _build_distilled_content(cv)
    assert "ROLE: Dev" in distilled
    assert "COMPETENCIES: Java" in distilled
    assert "EDUCATIONS: BSc @ MIT" in distilled
    assert "Dev @ Zenika | Java" in distilled
