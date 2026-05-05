import pytest
from pydantic import ValidationError
from datetime import datetime
from src.prompts.schemas import (
    PromptCreate,
    PromptUpdate,
    Prompt,
    PaginatedPromptsResponse,
    AnalysisResponse,
    ErrorReport
)

def test_prompt_create():
    p = PromptCreate(key="system_prompt", value="Tu es un assistant.")
    assert p.key == "system_prompt"
    assert p.value == "Tu es un assistant."

    with pytest.raises(ValidationError):
        PromptCreate(key="system_prompt")  # Missing value

def test_prompt_update():
    p = PromptUpdate(value="New value")
    assert p.value == "New value"

def test_prompt():
    p = Prompt(key="test", value="test", updated_at=datetime(2023, 1, 1))
    assert p.key == "test"
    assert p.updated_at is not None

def test_paginated_prompts_response():
    p = Prompt(key="test", value="test")
    resp = PaginatedPromptsResponse(prompts=[p], total=1, skip=0, limit=10)
    assert resp.total == 1
    assert resp.limit == 10
    assert len(resp.prompts) == 1

def test_analysis_response():
    r = AnalysisResponse(original_prompt="A", improved_prompt="B", promptfoo_report={"score": 100})
    assert r.original_prompt == "A"
    assert r.promptfoo_report["score"] == 100

def test_error_report():
    e = ErrorReport(service_name="cv_api", error_message="crash")
    assert e.service_name == "cv_api"
    assert e.context is None

    with pytest.raises(ValidationError):
        ErrorReport(service_name="cv_api") # Missing error_message
