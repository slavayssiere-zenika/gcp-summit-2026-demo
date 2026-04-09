import os
os.environ['SECRET_KEY'] = 'testsecret'
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import json

from main import app
from database import get_db
from src.auth import verify_jwt
from src.cvs.models import CVProfile

# 1. Provide dependency overrides for testing
async def override_get_db():
    db = AsyncMock()
    yield db

def override_verify_jwt():
    return {"sub": "test", "role": "admin"}

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt

client = TestClient(app)

# 2. Basic Tests
def test_health(mocker):
    mocker.patch("database.check_db_connection", new=AsyncMock(return_value=True))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_get_spec_success(mocker):
    mocker.patch("builtins.open", mocker.mock_open(read_data="# Spec doc"))
    response = client.get("/spec")
    assert response.status_code == 200
    assert "# Spec doc" in response.text

def test_get_spec_fail(mocker):
    mocker.patch("builtins.open", side_effect=Exception("Not found"))
    response = client.get("/spec")
    assert response.status_code == 200
    assert "# Specification introuvable" in response.text

# 3. Router Tests with Mocks
@pytest.fixture
def mock_httpx(mocker):
    mock = mocker.patch("src.cvs.router.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance

@pytest.fixture
def mock_genai(mocker):
    return mocker.patch("src.cvs.router.client")

def test_get_user_cv(mocker):
    # Mocking db.query
    mock_db = AsyncMock()
    mock_profile = MagicMock(user_id=1, source_url="http://test.com/cv.pdf", source_tag=None, imported_by_id=None)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_profile
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result
    
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.get("/user/1")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 1
    assert data["source_url"] == "http://test.com/cv.pdf"
    
    # Not found case
    mock_scalars.first.return_value = None
    response = client.get("/user/2")
    assert response.status_code == 404

def test_search_candidates(mock_genai, mock_httpx, mocker):
    mock_db = AsyncMock()
    # Mock Gemini embedding
    emb_res = MagicMock()
    emb_res.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]
    mock_genai.models.embed_content.return_value = emb_res
    
    # Mock Database cosine response
    mock_result = MagicMock()
    mock_result.all.return_value = [(MagicMock(user_id=1), 0.1), (MagicMock(user_id=2), 0.4)]
    mock_db.execute.return_value = mock_result
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock HTTPX enrichment
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"full_name": "Test User", "email": "test@zenika.com", "username": "test", "is_active": True}
    mock_httpx.get.return_value = mock_resp

    response = client.get("/search?query=test")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["user_id"] == 1
    assert data[0]["similarity_score"] == 0.9  # 1.0 - 0.1
    assert data[0]["full_name"] == "Test User"

def test_import_and_analyze_cv(mocker):
    # Setup Mocks
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    # Mocking _fetch_cv_content
    mocker.patch("src.cvs.router._fetch_cv_content", return_value="Dummy CV Text")

    # Mocking Gemini Client
    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.models.generate_content.return_value.text = '{"is_cv": true, "first_name": "John", "last_name": "Doe", "email": "john.doe@test.com", "competencies": [{"name": "Python", "parent": "Lang"}]}'
    mock_genai.models.embed_content.return_value.embeddings = [MagicMock(values=[0.1, 0.2])]
    
    # Mock HTTP responses
    mock_resp_prompts = MagicMock()
    mock_resp_prompts.json.return_value = {"value": "Prompt"}
    
    mock_resp_users = MagicMock()
    mock_resp_users.status_code = 200
    mock_resp_users.json.return_value = {"items": [], "id": 1} # user doesn't exist
    
    mock_resp_comps = MagicMock()
    mock_resp_comps.status_code = 200
    mock_resp_comps.json.return_value = {"items": []}
    
    mock_resp_create = MagicMock()
    mock_resp_create.status_code = 200
    mock_resp_create.json.return_value = {"id": 1}

    def get_side_effect(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        if "prompts_api" in url:
            return mock_resp_prompts
        if "/users/" in url:
            return mock_resp_users
        if "/competencies/" in url:
            return mock_resp_comps
        return MagicMock(status_code=200)

    def post_side_effect(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        if "/users/" in url or "/competencies/" in url:
            return mock_resp_create
        return MagicMock(status_code=200)
    
    client_instance.get.side_effect = get_side_effect
    client_instance.post.side_effect = post_side_effect

    # Make Request
    response = client.post("/import", json={"url": "http://docs.google.com/document/d/123/edit"}, headers={"Authorization": "Bearer token"})
    
    assert response.status_code == 200
    assert "Success" in response.json()["message"]
    assert response.json()["user_id"] == 1

def test_recalculate_tree(mocker):
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_profile = MagicMock(raw_content="My CV content")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_profile]
    mock_db.execute.return_value = mock_result
    
    mocker.patch("jose.jwt.decode", return_value={"role": "admin"})
    
    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.models.generate_content.return_value.text = '{"some": "tree"}'
    
    mock_resp_prompts = MagicMock(status_code=200)
    mock_resp_prompts.json.return_value = {"value": "Prompt {{EXISTING_COMPETENCIES}}"}
    
    mock_resp_comps = MagicMock(status_code=200)
    mock_resp_comps.json.return_value = {"items": [{"name": "Java"}]}

    def side_effect(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        if "prompts_api" in url:
            return mock_resp_prompts
        if "/competencies/" in url:
            return mock_resp_comps
        return MagicMock(status_code=200)
    
    client_instance.get.side_effect = side_effect
    
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json() == {"tree": {"some": "tree"}}


def test_fetch_cv_content_internal_url(mocker):
    response = client.post("/import", json={"url": "http://localhost/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 400
    assert "Internal URLs are not allowed" in response.text

def test_fetch_cv_content_invalid_scheme(mocker):
    response = client.post("/import", json={"url": "ftp://test.com/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 400
    assert "Invalid URL scheme" in response.text

def test_import_cv_no_auth(mocker):
    response = client.post("/import", json={"url": "http://test.com/cv.pdf"})
    assert response.status_code == 401

def test_import_cv_genai_not_configured(mocker):
    # force client to None
    mocker.patch("src.cvs.router.client", None)
    mocker.patch("src.cvs.router._fetch_cv_content", return_value="text")
    response = client.post("/import", json={"url": "http://test.com/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 500
    assert "GenAI Client not configured" in response.text

def test_import_cv_prompt_fail(mocker):
    mocker.patch("src.cvs.router.client", MagicMock())
    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    client_instance.get.side_effect = Exception("HTTP fetch failed")
    mocker.patch("src.cvs.router._fetch_cv_content", return_value="text")
    response = client.post("/import", json={"url": "http://test.com/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 500
    assert "Cannot fetch generic prompt" in response.text

def test_search_candidates_no_client(mocker):
    mocker.patch("src.cvs.router.client", None)
    response = client.get("/search?query=test")
    assert response.status_code == 500

def test_search_candidates_embed_fail(mocker):
    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.models.embed_content.side_effect = Exception("embed error")
    response = client.get("/search?query=test")
    assert response.status_code == 400
    assert "Embedding search query failed" in response.text

def test_recalculate_tree_no_auth(mocker):
    response = client.post("/recalculate_tree")
    assert response.status_code == 403

def test_recalculate_tree_bad_token(mocker):
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer badtoken"})
    assert response.status_code == 403

def test_recalculate_tree_not_admin(mocker):
    mocker.patch("jose.jwt.decode", return_value={"role": "user"})
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 403

def test_recalculate_tree_no_client(mocker):
    mocker.patch("jose.jwt.decode", return_value={"role": "admin"})
    mocker.patch("src.cvs.router.client", None)
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 500

def test_recalculate_tree_no_profiles(mocker):
    mocker.patch("src.cvs.router.client", MagicMock())
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    mocker.patch("jose.jwt.decode", return_value={"role": "admin"})
    
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 404


def test_import_cv_not_a_cv_boolean_check(mocker):
    # Setup Mocks
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mocker.patch("src.cvs.router._fetch_cv_content", return_value="This is a cake recipe, not a resume.")

    # Mocking Gemini Client to return is_cv false
    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.models.generate_content.return_value.text = '{"is_cv": false, "first_name": null, "last_name": null, "email": null, "competencies": []}'
    
    # Mock HTTP responses for prompts_api
    mock_resp_prompts = MagicMock()
    mock_resp_prompts.json.return_value = {"value": "Prompt"}
    
    def get_side_effect(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        if "prompts_api" in url:
            return mock_resp_prompts
        return MagicMock(status_code=200)
    
    client_instance.get.side_effect = get_side_effect

    # Make Request
    response = client.post("/import", json={"url": "http://docs.google.com/document/d/123/edit"}, headers={"Authorization": "Bearer token"})
    
    assert response.status_code == 400
    assert "Not a CV" in response.json()["detail"]
