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
from src.cvs.schemas import CVImportStep, CVResponse

# 1. Provide dependency overrides for testing
async def override_get_db():
    db = AsyncMock()
    yield db

def override_verify_jwt():
    return {"sub": "test", "role": "admin"}

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt
from src.auth import security
app.dependency_overrides[security] = lambda: MagicMock(credentials="testtoken")

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
    mock_scalars.all.return_value = [mock_profile]
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result
    
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.get("/user/1")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["user_id"] == 1
    assert data[0]["source_url"] == "http://test.com/cv.pdf"
    
    # Not found case
    mock_scalars.all.return_value = []
    response = client.get("/user/2")
    assert response.status_code == 404

def test_search_candidates(mock_genai, mock_httpx, mocker):
    mock_db = AsyncMock()
    # Mock Gemini embedding
    emb_res = MagicMock()
    emb_res.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]
    mock_genai.aio.models.embed_content = AsyncMock(return_value=emb_res)
    
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
    mock_genai.aio.models.generate_content = AsyncMock()
    mock_genai.aio.models.generate_content.return_value.text = '{"is_cv": true, "first_name": "John", "last_name": "Doe", "email": "john.doe@test.com", "summary": "Expert Python", "current_role": "Dev", "years_of_experience": 5, "competencies": [{"name": "Python", "parent": "Lang"}], "missions": [], "is_anonymous": false}'
    mock_genai.aio.models.embed_content = AsyncMock()
    mock_genai.aio.models.embed_content.return_value.embeddings = [MagicMock(values=[0.1, 0.2])]
    
    # Mock HTTP responses
    mock_resp_prompts = MagicMock()
    mock_resp_prompts.raise_for_status = MagicMock()
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
    data = response.json()
    assert "Success" in data["message"]
    assert data["user_id"] == 1

    # ── Vérification des nouvelles propriétés steps / warnings ──
    assert "steps" in data, "CVResponse doit contenir 'steps'"
    assert "warnings" in data, "CVResponse doit contenir 'warnings'"
    assert isinstance(data["steps"], list), "steps doit être une liste"
    assert isinstance(data["warnings"], list), "warnings doit être une liste"

    # Vérifier que les étapes clés sont présentes et au statut 'success'
    step_keys = {s["step"] for s in data["steps"]}
    assert "download" in step_keys, "L'étape 'download' doit être présente"
    assert "llm_parse" in step_keys, "L'étape 'llm_parse' doit être présente"
    assert "user_resolve" in step_keys, "L'étape 'user_resolve' doit être présente"
    assert "db_save" in step_keys, "L'étape 'db_save' doit être présente"

    for step in data["steps"]:
        assert step["status"] in {"success", "warning", "error"}, f"Statut inattendu: {step['status']}"
        assert "label" in step, "Chaque step doit avoir un 'label'"
        assert "step" in step, "Chaque step doit avoir un 'step' (identifiant)"


def test_import_cv_steps_on_truncated_document(mocker):
    """Un CV de plus de 8000 chars doit déclencher un warning 'download' + statut warning."""
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    long_text = "A" * 9000
    mocker.patch("src.cvs.router._fetch_cv_content", return_value=long_text)

    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.aio.models.generate_content = AsyncMock()
    mock_genai.aio.models.generate_content.return_value.text = '{"is_cv": true, "first_name": "Jane", "last_name": "Smith", "email": "jane@test.com", "summary": "Expert", "current_role": "Lead", "years_of_experience": 3, "competencies": [{"name": "Java"}], "missions": [], "is_anonymous": false}'
    mock_genai.aio.models.embed_content = AsyncMock()
    mock_genai.aio.models.embed_content.return_value.embeddings = [MagicMock(values=[0.1])]

    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci

    prompt_mock = MagicMock(); prompt_mock.raise_for_status = MagicMock(); prompt_mock.json.return_value = {"value": "P"}
    users_mock = MagicMock(status_code=200); users_mock.json.return_value = {"items": []}
    create_mock = MagicMock(status_code=200); create_mock.json.return_value = {"id": 99}
    comps_mock = MagicMock(status_code=200); comps_mock.json.return_value = {"items": []}

    def get_se(*a, **kw):
        url = a[0] if a else kw.get("url", "")
        if "prompts_api" in url: return prompt_mock
        if "/users/" in url: return users_mock
        if "/competencies/" in url: return comps_mock
        return MagicMock(status_code=200)
    def post_se(*a, **kw): return create_mock

    ci.get.side_effect = get_se
    ci.post.side_effect = post_se

    response = client.post("/import", json={"url": "http://docs.google.com/d/long"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    data = response.json()

    download_step = next((s for s in data["steps"] if s["step"] == "download"), None)
    assert download_step is not None
    assert download_step["status"] == "warning", "Un doc >8000 chars doit produire step 'download' en warning"
    assert any("tronqué" in w.lower() or "8000" in w for w in data["warnings"]), \
        "Le warning de troncature doit être dans CVResponse.warnings"


def test_import_cv_steps_on_zero_competencies(mocker):
    """Quand le LLM extrait 0 compétences, llm_parse doit être en warning."""
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mocker.patch("src.cvs.router._fetch_cv_content", return_value="Short legal document")

    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.aio.models.generate_content = AsyncMock()
    # LLM retourne is_cv=true mais 0 compétences
    mock_genai.aio.models.generate_content.return_value.text = '{"is_cv": true, "first_name": "Alice", "last_name": "Boo", "email": "a@b.com", "summary": "Expert", "current_role": "Dev", "years_of_experience": 1, "competencies": [], "missions": [], "is_anonymous": false}'
    mock_genai.aio.models.embed_content = AsyncMock()
    mock_genai.aio.models.embed_content.return_value.embeddings = [MagicMock(values=[0.1])]

    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci

    prompt_mock = MagicMock(); prompt_mock.raise_for_status = MagicMock(); prompt_mock.json.return_value = {"value": "P"}
    users_mock = MagicMock(status_code=200); users_mock.json.return_value = {"items": []}
    create_mock = MagicMock(status_code=200); create_mock.json.return_value = {"id": 42}
    comps_mock = MagicMock(status_code=200); comps_mock.json.return_value = {"items": []}

    def get_se(*a, **kw):
        url = a[0] if a else kw.get("url", "")
        if "prompts_api" in url: return prompt_mock
        if "/users/" in url: return users_mock
        if "/competencies/" in url: return comps_mock
        return MagicMock(status_code=200)
    def post_se(*a, **kw): return create_mock

    ci.get.side_effect = get_se
    ci.post.side_effect = post_se

    response = client.post("/import", json={"url": "http://docs.google.com/d/zero"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    data = response.json()
    
    llm_step = next((s for s in data["steps"] if s["step"] == "llm_parse"), None)
    assert llm_step is not None
    assert llm_step["status"] == "warning", "0 compétences doit passer llm_parse en 'warning'"
    assert any("compétence" in w.lower() for w in data["warnings"]), \
        "Le warning '0 compétences' doit être dans CVResponse.warnings"


def test_import_cv_steps_structure(mocker):
    """Vérifie que CVImportStep respecte le schéma Pydantic attendu."""
    step = CVImportStep(
        step="download",
        label="Téléchargement du document",
        status="success",
        duration_ms=423,
        detail="5000 caractères"
    )
    assert step.step == "download"
    assert step.label == "Téléchargement du document"
    assert step.status == "success"
    assert step.duration_ms == 423
    assert step.detail == "5000 caractères"


def test_cv_response_has_steps_and_warnings():
    """Vérifie que CVResponse peut porter des steps et warnings sans erreur Pydantic."""
    r = CVResponse(
        message="OK",
        user_id=1,
        competencies_assigned=3,
        steps=[
            CVImportStep(step="download", label="Téléchargement", status="success", duration_ms=100),
            CVImportStep(step="llm_parse", label="Analyse IA", status="warning", duration_ms=5000, detail="0 compétences"),
        ],
        warnings=["Doc tronqué", "Email absent"]
    )
    assert len(r.steps) == 2
    assert r.steps[0].step == "download"
    assert r.steps[1].status == "warning"
    assert len(r.warnings) == 2
    assert "Doc tronqué" in r.warnings
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
    mock_genai.aio.models.generate_content = AsyncMock()
    mock_genai.aio.models.generate_content.return_value.text = '{"some": "tree"}'
    
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
    assert response.json()["tree"] == {"some": "tree"}


def test_fetch_cv_content_internal_url(mocker):
    response = client.post("/import", json={"url": "http://localhost/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 400
    assert "Internal URLs are not allowed" in response.text

def test_fetch_cv_content_invalid_scheme(mocker):
    response = client.post("/import", json={"url": "ftp://test.com/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 400
    assert "Invalid URL scheme" in response.text

def test_import_cv_no_auth(mocker):
    original_jwt = app.dependency_overrides.get(verify_jwt)
    original_sec = app.dependency_overrides.get(security)
    app.dependency_overrides.pop(verify_jwt, None)
    app.dependency_overrides.pop(security, None)
    response = client.post("/import", json={"url": "http://test.com/cv.pdf"})
    assert response.status_code == 401
    app.dependency_overrides[verify_jwt] = original_jwt
    app.dependency_overrides[security] = original_sec

def test_import_cv_genai_not_configured(mocker):
    # force client to None
    mocker.patch("src.cvs.router.client", None)
    mocker.patch("src.cvs.router._fetch_cv_content", return_value="text")
    mocker.patch("os.path.exists", return_value=False)
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
    mocker.patch("os.path.exists", return_value=False)
    response = client.post("/import", json={"url": "http://test.com/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 500
    assert "Cannot fetch generic prompt" in response.text

def test_search_candidates_no_client(mocker):
    mocker.patch("src.cvs.router.client", None)
    response = client.get("/search?query=test")
    assert response.status_code == 500

def test_search_candidates_embed_fail(mocker):
    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.aio.models.embed_content = AsyncMock(side_effect=Exception("embed error"))
    response = client.get("/search?query=test")
    assert response.status_code == 400
    assert "Embedding search query failed" in response.text

def test_recalculate_tree_no_auth(mocker):
    original_jwt = app.dependency_overrides.get(verify_jwt)
    original_sec = app.dependency_overrides.get(security)
    app.dependency_overrides.pop(verify_jwt, None)
    app.dependency_overrides.pop(security, None)
    response = client.post("/recalculate_tree")
    assert response.status_code in [401, 403]
    app.dependency_overrides[verify_jwt] = original_jwt
    app.dependency_overrides[security] = original_sec

def test_recalculate_tree_bad_token(mocker):
    original_jwt = app.dependency_overrides.get(verify_jwt)
    original_sec = app.dependency_overrides.get(security)
    app.dependency_overrides.pop(verify_jwt, None)
    app.dependency_overrides.pop(security, None)
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer badtoken"})
    assert response.status_code in [401, 403]
    app.dependency_overrides[verify_jwt] = original_jwt
    app.dependency_overrides[security] = original_sec

def test_recalculate_tree_not_admin(mocker):
    app.dependency_overrides[verify_jwt] = lambda: {"role": "user"}
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer valid"})
    app.dependency_overrides[verify_jwt] = override_verify_jwt
    assert response.status_code in [401, 403]

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
    mock_genai.aio.models.generate_content = AsyncMock()
    mock_genai.aio.models.generate_content.return_value.text = '{"is_cv": false, "first_name": null, "last_name": null, "email": null, "competencies": []}'
    
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
