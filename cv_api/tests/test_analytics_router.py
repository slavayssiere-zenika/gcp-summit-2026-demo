import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from database import get_db
from fastapi.testclient import TestClient
from main import app
from src.auth import security, verify_jwt
from src.cvs.schemas import CVImportStep, CVResponse
from src.cvs.models import CVProfile

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

def test_recalculate_tree(mocker):
    mocker.patch("src.cvs.task_state.TreeTaskState.is_task_running", new=AsyncMock(return_value=False))
    mocker.patch("src.cvs.task_state.TreeTaskState.initialize_task", new=AsyncMock())

    response = client.post("/recalculate_tree", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["message"] == "Calcul interactif de l'arbre lancé"




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




def test_reanalyze_returns_json_immediately(mocker):
    """
    UC6 — /reanalyze retourne du JSON immédiat (pas de streaming SSE).
    Vérifie : status 200, body JSON avec pending_reset et sync_triggered.
    Vérifie également que PATCH /files/{id} est bien appelé avec status=PENDING
    et que POST /sync est déclenché.
    """
    _make_reanalyze_mocks(mocker)

    mock_httpx = mocker.patch("httpx.AsyncClient")
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

    mock_httpx = mocker.patch("httpx.AsyncClient")
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

    mock_httpx = mocker.patch("httpx.AsyncClient")
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

    mock_httpx = mocker.patch("httpx.AsyncClient")
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
    mock_httpx = mocker.patch("httpx.AsyncClient")
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




def _make_extraction_scores_mocks(mocker, has_score=True):
    mock_db = AsyncMock()
    mock_cv = MagicMock(spec=CVProfile)
    mock_cv.id = 1
    mock_cv.user_id = 10
    mock_cv.source_tag = "Nantes"
    mock_cv.current_role = "Lead Dev"
    mock_cv.extraction_reliability_score = 95.0 if has_score else None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_cv]
    mock_db.execute.return_value = mock_result
    
    # Pour le func.count()
    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 1
    mock_db.execute.side_effect = [mock_count_result, mock_result]
    
    app.dependency_overrides[get_db] = lambda: mock_db
    return mock_db



def test_extraction_scores_calculated(mocker):
    """Vérifie que /extraction-scores retourne bien les profils calculés et enrichit via users_api."""
    _make_extraction_scores_mocks(mocker, has_score=True)

    mock_httpx = mocker.patch("httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci

    users_mock = MagicMock(status_code=200)
    users_mock.json.return_value = {
        "full_name": "Jean Dupont",
        "email": "jean.dupont@zenika.com",
        "is_anonymous": False
    }
    ci.get.return_value = users_mock

    response = client.get("/extraction-scores?status=calculated", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["full_name"] == "Jean Dupont"
    assert data["items"][0]["extraction_reliability_score"] == 95.0




def test_extraction_scores_uncalculated(mocker):
    """Vérifie le paramètre status=uncalculated."""
    _make_extraction_scores_mocks(mocker, has_score=False)

    mock_httpx = mocker.patch("httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci
    
    users_mock = MagicMock(status_code=200)
    users_mock.json.return_value = {"full_name": "Alice Wonderland"}
    ci.get.return_value = users_mock

    response = client.get("/extraction-scores?status=uncalculated", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["extraction_reliability_score"] is None
    assert data["items"][0]["full_name"] == "Alice Wonderland"




def test_extraction_scores_users_api_failure(mocker):
    """Si users_api est injoignable, l'endpoint doit retourner 200 avec Inconnu/Erreur."""
    _make_extraction_scores_mocks(mocker, has_score=True)

    mock_httpx = mocker.patch("httpx.AsyncClient")
    ci = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = ci
    ci.get.side_effect = Exception("network timeout")

    response = client.get("/extraction-scores", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["full_name"] == "Erreur"


def _make_reanalyze_mocks(mocker, source_url="https://docs.google.com/document/d/GFILE123/edit"):
    """Helper : prépare un CVProfile en base et retourne le mock_db."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_cv = MagicMock(spec=CVProfile)
    mock_cv.id = 1
    mock_cv.user_id = 10
    mock_cv.source_url = source_url
    mock_cv.source_tag = "Nantes"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_cv]
    mock_db.execute.return_value = mock_result
    app.dependency_overrides[get_db] = lambda: mock_db
    return mock_db




