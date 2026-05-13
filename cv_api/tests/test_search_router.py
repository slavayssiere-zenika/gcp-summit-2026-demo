import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from database import get_db
from fastapi.testclient import TestClient
from main import app
from src.auth import security, verify_jwt

os.environ['SECRET_KEY'] = 'testsecret'


async def override_get_db():
    db = AsyncMock()
    yield db


def override_verify_jwt():
    return {"sub": "test", "role": "admin"}


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt
app.dependency_overrides[security] = lambda: MagicMock(credentials="testtoken")

client = TestClient(app)


@pytest.fixture
def mock_httpx(mocker):
    mock = mocker.patch("httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance


@pytest.fixture
def mock_genai(mocker):
    return mocker.patch("src.services.config.client")


def test_search_candidates(mock_genai, mock_httpx, mocker):
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    # Mock Gemini embedding
    emb_res = MagicMock()
    emb_res.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]
    mock_genai.aio.models.embed_content = AsyncMock(return_value=emb_res)

    # Mock Database cosine response
    mock_result = MagicMock()
    mock_result.all.return_value = [
        # R5/R1 : source_url et embedding_model doivent être None (pas MagicMock)
        # pour passer la sérialisation Pydantic du schéma SearchResultItem
        (MagicMock(user_id=1, source_url=None, embedding_model=None), 0.1),
        (MagicMock(user_id=2, source_url=None, embedding_model=None), 0.4),
    ]

    # Separate mock for the scalar() call (total_before_threshold in R6)
    mock_scalar_result = MagicMock()
    mock_scalar_result.scalar.return_value = 5

    # missing_count_stmt uses scalar() too — return 0 for it (first scalar call)
    mock_missing_result = MagicMock()
    mock_missing_result.scalar.return_value = 0

    # execute() is called several times:
    # 1st: missing_count_stmt (.scalar() → 0)
    # 2nd: stmt_filtered or stmt (.all() → results)
    # 3rd: stmt_unfiltered (.scalar() → 5)
    mock_db.execute.side_effect = [mock_missing_result, mock_result, mock_scalar_result]
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock HTTPX enrichment
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"full_name": "Test User",
                                   "email": "test@zenika.com", "username": "test", "is_active": True}
    mock_httpx.get.return_value = mock_resp

    response = client.get("/search?query=test")
    assert response.status_code == 200
    data = response.json()
    items = data.get("items", data)
    assert len(items) == 2
    assert items[0]["user_id"] == 1
    assert items[0]["similarity_score"] == 0.9  # 1.0 - 0.1
    assert items[0]["full_name"] == "Test User"


def test_search_candidates_no_client(mocker):
    mocker.patch("src.services.config.client", None)
    response = client.get("/search?query=test")
    assert response.status_code == 500


def test_search_candidates_embed_fail(mocker):
    mock_genai = mocker.patch("src.services.config.client")
    mock_genai.aio.models.embed_content = AsyncMock(side_effect=Exception("embed error"))
    response = client.get("/search?query=test")
    assert response.status_code == 400
    assert "Embedding search query failed" in response.text
