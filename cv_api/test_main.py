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
from src.cvs.task_state import tree_task_manager

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
    mock_db.add = MagicMock()
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
    mock_db.add = MagicMock()
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
    mock_db.add = MagicMock()
    mock_db.execute.return_value = MagicMock()
    mock_db.execute.return_value.scalars.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    # Mocking _fetch_cv_content
    mocker.patch("src.services.cv_import_service._fetch_cv_content", return_value="Dummy CV Text")

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
    assert "succès" in data["message"]
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
    """Un CV de plus de 100000 chars doit déclencher un warning 'download' + statut warning."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute.return_value = MagicMock()
    mock_db.execute.return_value.scalars.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db

    long_text = "A" * 101000  # dépasse le seuil réel de 100000 caractères du router
    mocker.patch("src.services.cv_import_service._fetch_cv_content", return_value=long_text)

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
        if "/users/" in url or "search" in url: return users_mock
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
    assert download_step["status"] == "warning", (
        f"Un doc >100000 chars doit produire step 'download' en warning. "
        f"Statut actuel: {download_step['status']} — seuil router: 100000 chars"
    )
    assert any("tronqué" in w.lower() or "100000" in w for w in data["warnings"]), \
        f"Le warning de troncature doit être dans CVResponse.warnings. Warnings actuels: {data['warnings']}"


def test_import_cv_steps_on_zero_competencies(mocker):
    """Quand le LLM extrait 0 compétences, llm_parse doit être en warning."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute.return_value = MagicMock()
    mock_db.execute.return_value.scalars.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db

    mocker.patch("src.services.cv_import_service._fetch_cv_content", return_value="Short legal document")

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
    mocker.patch("src.cvs.task_state.TreeTaskState.is_task_running", new=AsyncMock(return_value=False))
    mocker.patch("src.cvs.task_state.TreeTaskState.initialize_task", new=AsyncMock())
    
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["message"] == "Calcul interactif de l'arbre lancé"


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
    mocker.patch("src.services.cv_import_service._fetch_cv_content", return_value="text")
    mocker.patch("os.path.exists", return_value=False)
    response = client.post("/import", json={"url": "http://test.com/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 500
    assert "GenAI Client not configured" in response.text

def test_import_cv_prompt_fail(mocker):
    """
    Quand le prompt HTTP échoue ET qu'aucun fichier fallback n'existe,
    l'API doit retourner HTTP 500 avec 'Cannot fetch generic prompt'.
    """
    # Client GenAI valide (AsyncMock) — l'erreur doit survenir avant l'appel LLM
    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.aio.models.generate_content = AsyncMock()
    mock_genai.aio.models.embed_content = AsyncMock()

    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    # Le GET vers prompts_api lève une exception réseau
    client_instance.get.side_effect = Exception("HTTP fetch failed")

    mocker.patch("src.services.cv_import_service._fetch_cv_content", return_value="text")
    # Pas de fichier fallback disponible
    mocker.patch("os.path.exists", return_value=False)
    # Vider le cache prompt pour forcer le fetching HTTP
    import src.services.cv_import_service as cv_import_service
    cv_import_service._CV_CACHE["prompt"]["value"] = None
    cv_import_service._CV_CACHE["prompt"]["expires"] = __import__('datetime').datetime.min.replace(tzinfo=__import__('datetime').timezone.utc)

    response = client.post("/import", json={"url": "http://test.com/cv.pdf"}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 500
    assert "Cannot fetch generic prompt" in response.text, \
        f"Le message d'erreur attendu est absent. Reçu: {response.text[:300]}"

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
    mocker.patch("src.cvs.task_state.TreeTaskState.is_task_running", new=AsyncMock(return_value=False))
    mocker.patch("src.cvs.task_state.TreeTaskState.initialize_task", new=AsyncMock())
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"

def test_recalculate_tree_already_running(mocker):
    mocker.patch("jose.jwt.decode", return_value={"role": "admin"})
    mocker.patch("src.cvs.task_state.TreeTaskState.is_task_running", new=AsyncMock(return_value=True))
    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200
    assert response.json()["message"] == "Un calcul de l'arbre est déjà en cours"


def test_import_cv_not_a_cv_boolean_check(mocker):
    # Setup Mocks
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute.return_value = MagicMock()
    mock_db.execute.return_value.scalars.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mocker.patch("src.services.cv_import_service._fetch_cv_content", return_value="This is a cake recipe, not a resume.")

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


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Nomenclature Zenika : folder_name dans /import
# ═══════════════════════════════════════════════════════════════════════════════

def _make_full_import_mocks(mocker, first_name="Jean", last_name="Dupont", email="jean.dupont@zenika.com"):
    """Helper : configure tous les mocks nécessaires pour un import CV complet."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute.return_value = MagicMock()
    mock_db.execute.return_value.scalars.return_value.first.return_value = None
    mock_db.add = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mocker.patch("src.services.cv_import_service._fetch_cv_content", return_value="Contenu du CV de test")

    mock_genai = mocker.patch("src.cvs.router.client")
    mock_genai.aio.models.generate_content = AsyncMock()
    mock_genai.aio.models.generate_content.return_value.text = (
        f'{{"is_cv": true, "first_name": "{first_name}", "last_name": "{last_name}", '
        f'"email": "{email}", "summary": "Expert", "current_role": "Dev", '
        f'"years_of_experience": 5, "competencies": [{{"name": "Python", "parent": "Lang"}}], '
        f'"missions": [], "is_anonymous": false}}'
    )
    mock_genai.aio.models.embed_content = AsyncMock()
    mock_genai.aio.models.embed_content.return_value.embeddings = [MagicMock(values=[0.1, 0.2])]

    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci

    prompt_mock = MagicMock()
    prompt_mock.raise_for_status = MagicMock()
    prompt_mock.json.return_value = {"value": "Prompt systeme"}

    users_mock = MagicMock(status_code=200)
    users_mock.json.return_value = {"items": []}

    create_mock = MagicMock(status_code=200)
    create_mock.json.return_value = {"id": 42}

    comps_mock = MagicMock(status_code=200)
    comps_mock.json.return_value = {"items": []}

    def get_se(*a, **kw):
        url = a[0] if a else kw.get("url", "")
        if "prompts_api" in url:
            return prompt_mock
        if "/users/" in url or "search" in url:
            return users_mock
        if "/competencies/" in url:
            return comps_mock
        return MagicMock(status_code=200)

    def post_se(*a, **kw):
        return create_mock

    ci.get.side_effect = get_se
    ci.post.side_effect = post_se
    return ci


def test_import_cv_with_folder_name_zenika_nomenclature(mocker):
    """
    UC1 — Import avec folder_name 'Prénom Nom' : le user_resolve doit réussir
    et extracted_info doit contenir folder_name.
    """
    _make_full_import_mocks(mocker)

    response = client.post(
        "/import",
        json={
            "url": "http://docs.google.com/document/d/abc123/edit",
            "folder_name": "Marie Dupont"
        },
        headers={"Authorization": "Bearer token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 42
    assert "steps" in data
    assert "warnings" in data

    # extracted_info doit porter folder_name
    if data.get("extracted_info"):
        assert data["extracted_info"].get("folder_name") == "Marie Dupont"

    # Aucun step ne doit être en erreur
    error_steps = [s for s in data["steps"] if s["status"] == "error"]
    assert not error_steps, f"Des steps sont en erreur: {error_steps}"


def test_import_cv_folder_name_priority_over_llm(mocker):
    """
    UC2 — folder_name fait foi sur l'identité LLM.
    LLM renvoie 'Pierre Martin', folder_name = 'Marie Durand'.
    Un warning divergence doit apparaître ET folder_name doit être utilisé.
    """
    ci = _make_full_import_mocks(mocker, first_name="Pierre", last_name="Martin")

    # Simuler que la recherche par folder_name ('Marie Durand') trouve l'utilisateur ID 99
    folder_match_mock = MagicMock(status_code=200)
    folder_match_mock.json.return_value = {
        "items": [{"id": 99, "first_name": "Marie", "last_name": "Durand", "email": "marie.durand@zenika.com"}]
    }

    create_mock = MagicMock(status_code=200)
    create_mock.json.return_value = {"id": 99}

    def get_se(*a, **kw):
        url = a[0] if a else kw.get("url", "")
        if "prompts_api" in url:
            m = MagicMock(); m.raise_for_status = MagicMock(); m.json.return_value = {"value": "P"}; return m
        if "search" in url:
            return folder_match_mock
        if "/competencies/" in url:
            m = MagicMock(status_code=200); m.json.return_value = {"items": []}; return m
        return MagicMock(status_code=200)

    ci.get.side_effect = get_se
    ci.post.side_effect = lambda *a, **kw: create_mock

    response = client.post(
        "/import",
        json={
            "url": "http://docs.google.com/document/d/diverge456/edit",
            "folder_name": "Marie Durand"
        },
        headers={"Authorization": "Bearer token"}
    )
    assert response.status_code == 200
    data = response.json()

    # Un warning de divergence doit être présent
    divergence_warnings = [w for w in data.get("warnings", []) if "divergence" in w.lower() or "dossier" in w.lower()]
    assert divergence_warnings, (
        f"Un warning de divergence LLM/dossier attendu. Warnings reçus: {data.get('warnings')}"
    )

    # L'étape folder_identity doit être présente (statut warning)
    folder_step = next((s for s in data["steps"] if s["step"] == "folder_identity"), None)
    assert folder_step is not None, "L'étape 'folder_identity' doit être présente en cas de divergence"
    assert folder_step["status"] == "warning"


def test_import_cv_folder_name_single_word_ignored(mocker):
    """
    UC3 — Un folder_name mono-composant (trigramme, alias) est ignoré pour l'identité.
    Pas de warning divergence, résolution LLM classique.
    """
    _make_full_import_mocks(mocker)

    response = client.post(
        "/import",
        json={
            "url": "http://docs.google.com/document/d/mono789/edit",
            "folder_name": "JDU"   # trigramme — 1 seul mot
        },
        headers={"Authorization": "Bearer token"}
    )
    assert response.status_code == 200
    data = response.json()

    # Aucun warning de divergence dossier/LLM
    divergence_warnings = [w for w in data.get("warnings", []) if "divergence" in w.lower()]
    assert not divergence_warnings, f"Pas de warning divergence attendu pour un trigramme. Reçu: {divergence_warnings}"

    # Pas d'étape folder_identity (pas de divergence détectée)
    folder_step = next((s for s in data["steps"] if s["step"] == "folder_identity"), None)
    assert folder_step is None, "Pas d'étape folder_identity attendue pour un nom mono-composant"


def test_import_cv_without_folder_name_llm_fallback(mocker):
    """
    UC4 — Import sans folder_name (frontend manuel, MCP sans hint) :
    la résolution LLM classique doit fonctionner normalement.
    """
    _make_full_import_mocks(mocker)

    response = client.post(
        "/import",
        json={"url": "http://docs.google.com/document/d/nofolder/edit"},
        headers={"Authorization": "Bearer token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 42

    # Aucune étape folder_identity (aucun dossier fourni)
    folder_step = next((s for s in data["steps"] if s["step"] == "folder_identity"), None)
    assert folder_step is None, "Pas d'étape folder_identity attendue sans folder_name"


def test_import_cv_schema_folder_name_optional():
    """
    UC5 — folder_name est optionnel dans CVImportRequest (rétrocompatibilité).
    Un payload sans folder_name ne doit pas provoquer d'erreur de validation.
    """
    from src.cvs.schemas import CVImportRequest
    req = CVImportRequest(url="https://docs.google.com/document/d/abc/edit")
    assert req.folder_name is None

    req2 = CVImportRequest(url="https://docs.google.com/document/d/abc/edit", folder_name="Alice Martin")
    assert req2.folder_name == "Alice Martin"



# ═══════════════════════════════════════════════════════════════════════════════
# Tests — /reanalyze : Pipeline Pub/Sub unifié (plus de SSE)
# UC6 : reset PENDING + /sync déclenché
# UC7 : URL sans google_file_id → skipped_manual
# UC8 : drive_api inaccessible → mode dégradé, retour JSON 200
# UC9 : aucun CV en base → message re-découverte Drive
# ═══════════════════════════════════════════════════════════════════════════════

def _make_reanalyze_mocks(mocker, source_url="https://docs.google.com/document/d/GFILE123/edit"):
    """Helper : prépare un CVProfile en base et retourne le mock_db."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_cv = MagicMock()
    mock_cv.id = 1
    mock_cv.user_id = 10
    mock_cv.source_url = source_url
    mock_cv.source_tag = "Nantes"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_cv]
    mock_db.execute.return_value = mock_result
    app.dependency_overrides[get_db] = lambda: mock_db
    return mock_db


def test_reanalyze_returns_json_immediately(mocker):
    """
    UC6 — /reanalyze retourne du JSON immédiat (pas de streaming SSE).
    Vérifie : status 200, body JSON avec pending_reset et sync_triggered.
    Vérifie également que PATCH /files/{id} est bien appelé avec status=PENDING
    et que POST /sync est déclenché.
    """
    _make_reanalyze_mocks(mocker)

    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci

    # Service token
    svc_mock = MagicMock(status_code=200)
    svc_mock.json.return_value = {"access_token": "svc-token"}

    # Nettoyage compétences
    clear_mock = MagicMock(status_code=204)

    # PATCH /files/GFILE123 → 200
    patch_mock = MagicMock(status_code=200)

    # POST /sync → 200
    sync_mock = MagicMock(status_code=200)

    # reset-sync
    reset_mock = MagicMock(status_code=200)

    def post_se(*a, **kw):
        url = a[0] if a else kw.get("url", "")
        if "service-token" in url:
            return svc_mock
        if "/sync" in url:
            return sync_mock
        if "reset-sync" in url:
            return reset_mock
        return MagicMock(status_code=200)

    def delete_se(*a, **kw):
        return clear_mock

    def patch_se(*a, **kw):
        return patch_mock

    ci.post.side_effect = post_se
    ci.delete.side_effect = delete_se
    ci.patch.side_effect = patch_se

    response = client.post("/reanalyze", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    data = response.json()

    # Réponse JSON structurée
    assert "pending_reset" in data, "pending_reset manquant dans la réponse"
    assert "sync_triggered" in data, "sync_triggered manquant dans la réponse"
    assert "count" in data, "count manquant dans la réponse"
    assert "users_cleared" in data, "users_cleared manquant dans la réponse"

    # 1 CV avec google_file_id → 1 PENDING reset
    assert data["pending_reset"] == 1, f"1 CV attendu en PENDING. Reçu: {data['pending_reset']}"
    assert data["skipped_manual"] == 0

    # /sync doit avoir été déclenché
    assert data["sync_triggered"] is True, "sync_triggered doit être True"

    # Vérifier que PATCH /files/GFILE123 a été appelé avec status=PENDING
    patch_calls = [c for c in ci.patch.call_args_list if "GFILE123" in str(c)]
    assert patch_calls, "PATCH /files/GFILE123 doit être appelé pour reset PENDING"
    patch_kwargs = patch_calls[0][1] if patch_calls[0][1] else {}
    patch_body = patch_kwargs.get("json", {})
    assert patch_body.get("status") == "PENDING", f"Le PATCH doit envoyer status=PENDING. Reçu: {patch_body}"

    # Vérifier que DELETE /clear a été appelé pour le user_id=10
    delete_calls = [c for c in ci.delete.call_args_list if "/user/10/clear" in str(c)]
    assert delete_calls, "DELETE /user/10/clear doit être appelé pour nettoyer les compétences"


def test_reanalyze_url_without_google_doc_id(mocker):
    """
    UC7 — /reanalyze : si la source_url n'est pas un Google Doc (pas de /d/{id}),
    le CV est compté dans skipped_manual et aucun PATCH n'est émis.
    """
    _make_reanalyze_mocks(mocker, source_url="https://externe.pdf")

    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci

    svc_mock = MagicMock(status_code=200)
    svc_mock.json.return_value = {"access_token": "svc-token"}
    ci.post.side_effect = lambda *a, **kw: svc_mock
    ci.delete.return_value = MagicMock(status_code=204)
    ci.patch.return_value = MagicMock(status_code=200)

    response = client.post("/reanalyze", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    data = response.json()

    assert data["skipped_manual"] == 1, f"1 CV manuel attendu dans skipped_manual. Reçu: {data['skipped_manual']}"
    assert data["pending_reset"] == 0, f"Aucun PENDING attendu pour URL non-GDoc. Reçu: {data['pending_reset']}"

    # Aucun PATCH /files/ ne doit être émis
    patch_calls = [c for c in ci.patch.call_args_list if "/files/" in str(c)]
    assert not patch_calls, f"Aucun PATCH /files attendu pour URL externe. Appels: {patch_calls}"


def test_reanalyze_drive_api_unavailable_degraded(mocker):
    """
    UC8 — /reanalyze : si drive_api est inaccessible pour le PATCH ou /sync,
    le endpoint retourne quand même 200 avec sync_triggered=False (mode dégradé).
    """
    _make_reanalyze_mocks(mocker)

    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci

    svc_mock = MagicMock(status_code=200)
    svc_mock.json.return_value = {"access_token": "svc-token"}

    def post_se(*a, **kw):
        url = a[0] if a else kw.get("url", "")
        if "service-token" in url:
            return svc_mock
        # /sync et /reset-sync lèvent une exception réseau
        raise ConnectionError("drive_api unreachable")

    def patch_se(*a, **kw):
        raise ConnectionError("drive_api unreachable")

    ci.post.side_effect = post_se
    ci.delete.return_value = MagicMock(status_code=204)
    ci.patch.side_effect = patch_se

    response = client.post("/reanalyze", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    data = response.json()

    # Mode dégradé : sync_triggered=False mais pas d'erreur 5xx
    assert data["sync_triggered"] is False, "sync_triggered doit être False si /sync est injoignable"
    assert "message" in data


def test_reanalyze_no_cvs_in_db(mocker):
    """
    UC9 — /reanalyze : aucun CV en base → retour immédiat avec message indiquant
    qu'une re-découverte Drive a été ordonnée.
    """
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []  # Aucun CV
    mock_db.execute.return_value = mock_result
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci
    ci.post.return_value = MagicMock(status_code=200)

    response = client.post("/reanalyze", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 0
    assert data["pending_reset"] == 0
    assert "re-découverte" in data["message"].lower() or "drive" in data["message"].lower(), \
        f"Le message doit mentionner la re-découverte Drive. Reçu: {data['message']}"


def test_reanalyze_status_proxies_drive_api(mocker):
    """
    Vérifie que GET /reanalyze/status proxyfie vers drive_api /status
    et retourne le résultat tel quel.
    """
    mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci

    drive_status = {
        "PENDING": 3, "QUEUED": 1, "PROCESSING": 0,
        "IMPORTED_CV": 12, "ERROR": 0
    }
    status_mock = MagicMock(status_code=200)
    status_mock.json.return_value = drive_status
    ci.get.return_value = status_mock

    response = client.get("/reanalyze/status", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    data = response.json()
    assert data == drive_status

    # Vérifier que l'appel vers drive_api /status est bien effectué
    get_calls = [c for c in ci.get.call_args_list if "/status" in str(c)]
    assert get_calls, "GET /status doit être appelé sur drive_api"


def test_reanalyze_not_admin(mocker):
    """
    /reanalyze doit retourner 403 si le rôle n'est pas admin.
    """
    app.dependency_overrides[verify_jwt] = lambda: {"role": "user", "sub": "alice"}
    try:
        response = client.post("/reanalyze", headers={"Authorization": "Bearer token"})
        assert response.status_code == 403
    finally:
        app.dependency_overrides[verify_jwt] = override_verify_jwt


