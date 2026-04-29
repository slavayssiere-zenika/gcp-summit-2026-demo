import os
os.environ['SECRET_KEY'] = 'testsecret'
os.environ["CV_API_URL"] = "http://test-cv"

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock
import httpx
from fastapi.testclient import TestClient

from main import app
from database import get_db
from src.auth import verify_jwt, security
from mcp_server import call_tool, mcp_auth_header_var

# ── Overrides ──────────────────────────────────────────────────────────────────

async def override_get_db():
    db = AsyncMock()
    yield db

def override_verify_jwt():
    return {"sub": "test-admin", "role": "admin"}

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt
app.dependency_overrides[security] = lambda: MagicMock(credentials="testtoken")

client = TestClient(app)


# ══════════════════════════════════════════════════════════════════════════════
# 1. BulkReanalyseTaskManager — State Machine
# ══════════════════════════════════════════════════════════════════════════════

class TestBulkReanalyseTaskManager:

    def test_initial_state_via_initialize(self):
        """La classe existe et possède les méthodes attendues."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        mgr = BulkReanalyseTaskManager()
        assert hasattr(mgr, "initialize")
        assert hasattr(mgr, "get_status")
        assert hasattr(mgr, "is_running")
        assert hasattr(mgr, "reset")
        assert hasattr(mgr, "update_progress")

    def test_redis_key_constant(self):
        """La clé Redis est bien définie."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        assert BulkReanalyseTaskManager.KEY == "cv:bulk_reanalyse:status"

    @pytest.mark.asyncio
    async def test_get_status_returns_none_when_empty(self, mocker):
        """get_status() retourne None quand Redis est vide."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mgr = BulkReanalyseTaskManager()
        mgr._redis = mock_redis
        result = await mgr.get_status()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_status_deserializes_json(self, mocker):
        """get_status() désérialise le JSON stocké dans Redis."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        stored = {
            "status": "batch_running",
            "total_cvs": 50,
            "applying_current": 0,
            "error_count": 0,
            "skipped_count": 0,
            "total_tokens_input": 1000,
            "total_tokens_output": 500,
            "logs": ["step1"],
            "errors": [],
            "error": None,
            "batch_job_id": "jobs/abc",
            "dest_uri": None,
            "start_time": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "end_time": None,
        }
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(stored))
        mgr = BulkReanalyseTaskManager()
        mgr._redis = mock_redis
        result = await mgr.get_status()
        assert result["status"] == "batch_running"
        assert result["total_cvs"] == 50

    @pytest.mark.asyncio
    async def test_is_running_false_when_no_status(self, mocker):
        """is_running() retourne False quand aucun job n'existe."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mgr = BulkReanalyseTaskManager()
        mgr._redis = mock_redis
        assert await mgr.is_running() is False

    @pytest.mark.asyncio
    async def test_is_running_true_for_active_statuses(self, mocker):
        """is_running() retourne True pour building, uploading, batch_running, applying."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        mgr = BulkReanalyseTaskManager()
        for active_status in ["building", "uploading", "batch_running", "applying"]:
            stored = {
                "status": active_status,
                "updated_at": datetime.now().isoformat(),  # récent → pas zombie
            }
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=json.dumps(stored))
            mgr._redis = mock_redis
            assert await mgr.is_running() is True, f"{active_status} doit être actif"

    @pytest.mark.asyncio
    async def test_is_running_false_for_terminal_statuses(self, mocker):
        """is_running() retourne False pour idle, completed, error."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        mgr = BulkReanalyseTaskManager()
        for terminal in ["idle", "completed", "error"]:
            stored = {"status": terminal, "updated_at": datetime.now().isoformat()}
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=json.dumps(stored))
            mgr._redis = mock_redis
            assert await mgr.is_running() is False, f"{terminal} ne doit pas être actif"

    @pytest.mark.asyncio
    async def test_watchdog_zombie_detection(self, mocker):
        """is_running() doit détecter une tâche zombie et retourner False."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        mgr = BulkReanalyseTaskManager()
        # Updated_at il y a 181 minutes → zombie (seuil = 180 min)
        old_time = (datetime.now() - timedelta(minutes=181)).isoformat()
        stored = {
            "status": "batch_running",
            "updated_at": old_time,
            "applying_current": 0,
            "error_count": 0,
            "skipped_count": 0,
            "total_tokens_input": 0,
            "total_tokens_output": 0,
            "logs": [],
            "errors": [],
            "error": None,
            "batch_job_id": None,
            "dest_uri": None,
            "start_time": old_time,
            "end_time": None,
            "total_cvs": 10,
        }
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(stored))
        mock_redis.set = AsyncMock()
        mgr._redis = mock_redis
        result = await mgr.is_running()
        assert result is False  # zombie détecté → déverrouillage

    @pytest.mark.asyncio
    async def test_reset_deletes_redis_key(self, mocker):
        """reset() doit supprimer la clé Redis."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        mgr = BulkReanalyseTaskManager()
        mgr._redis = mock_redis
        await mgr.reset()
        mock_redis.delete.assert_awaited_once_with(BulkReanalyseTaskManager.KEY)

    @pytest.mark.asyncio
    async def test_update_progress_increments_counters(self, mocker):
        """update_progress() doit incrémenter les compteurs correctement."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        initial = {
            "status": "applying",
            "applying_current": 5,
            "error_count": 1,
            "skipped_count": 0,
            "total_tokens_input": 1000,
            "total_tokens_output": 200,
            "logs": [],
            "errors": [],
            "error": None,
            "batch_job_id": None,
            "dest_uri": None,
            "start_time": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "end_time": None,
            "total_cvs": 100,
        }
        saved = {}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(initial))
        async def capture(k, v, ex=None): saved.update(json.loads(v))
        mock_redis.set = AsyncMock(side_effect=capture)
        mgr = BulkReanalyseTaskManager()
        mgr._redis = mock_redis

        await mgr.update_progress(
            applying_current_inc=3,
            error_count_inc=1,
            tokens_input_inc=500,
            tokens_output_inc=100,
            new_log="CV 8 traité"
        )
        assert saved["applying_current"] == 8   # 5 + 3
        assert saved["error_count"] == 2         # 1 + 1
        assert saved["total_tokens_input"] == 1500
        assert saved["total_tokens_output"] == 300
        assert any("CV 8 traité" in log for log in saved["logs"])

    @pytest.mark.asyncio
    async def test_update_progress_sets_end_time_on_completed(self, mocker):
        """update_progress(status='completed') doit fixer end_time."""
        from src.cvs.bulk_task_state import BulkReanalyseTaskManager
        initial = {
            "status": "applying", "applying_current": 100, "error_count": 0,
            "skipped_count": 0, "total_tokens_input": 0, "total_tokens_output": 0,
            "logs": [], "errors": [], "error": None, "batch_job_id": None,
            "dest_uri": None, "start_time": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(), "end_time": None, "total_cvs": 100,
        }
        saved = {}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(initial))
        async def capture(k, v, ex=None): saved.update(json.loads(v))
        mock_redis.set = AsyncMock(side_effect=capture)
        mgr = BulkReanalyseTaskManager()
        mgr._redis = mock_redis
        await mgr.update_progress(status="completed")
        assert saved["status"] == "completed"
        assert saved["end_time"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# 2. Endpoints HTTP
# ══════════════════════════════════════════════════════════════════════════════

class TestBulkReanalyseEndpoints:

    def test_status_idle(self, mocker):
        """GET /bulk-reanalyse/status doit retourner idle quand aucun job actif."""
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.get_status",
                     new=AsyncMock(return_value=None))
        r = client.get("/bulk-reanalyse/status", headers={"Authorization": "Bearer token"})
        assert r.status_code == 200
        assert r.json()["status"] == "idle"

    def test_status_batch_running(self, mocker):
        """GET /bulk-reanalyse/status retourne les stats Vertex en batch_running."""
        state = {
            "status": "batch_running", "total_cvs": 100, "applying_current": 0,
            "error_count": 0, "skipped_count": 0, "logs": [], "errors": [],
            "total_tokens_input": 50000, "total_tokens_output": 10000,
            "batch_job_id": "proj/jobs/123", "dest_uri": None,
            "start_time": datetime.now().isoformat(), "updated_at": datetime.now().isoformat(),
            "end_time": None, "error": None,
        }
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.get_status",
                     new=AsyncMock(return_value=state))
        r = client.get("/bulk-reanalyse/status", headers={"Authorization": "Bearer token"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "batch_running"
        assert data["total_cvs"] == 100

    def test_status_requires_auth(self):
        """GET /bulk-reanalyse/status doit renvoyer 401 sans JWT."""
        jwt_orig = app.dependency_overrides.pop(verify_jwt, None)
        sec_orig = app.dependency_overrides.pop(security, None)
        r = client.get("/bulk-reanalyse/status")
        assert r.status_code == 401
        if jwt_orig: app.dependency_overrides[verify_jwt] = jwt_orig
        if sec_orig: app.dependency_overrides[security] = sec_orig

    def test_start_returns_202_when_idle(self, mocker):
        """POST /bulk-reanalyse/start doit retourner 202 si aucun job en cours."""
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.is_running",
                     new=AsyncMock(return_value=False))
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.initialize",
                     new=AsyncMock(return_value={"status": "building"}))
        # Mock DB pour SELECT COUNT(*) FROM cv_profiles
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 42
        mock_db.execute = AsyncMock(return_value=count_result)
        app.dependency_overrides[get_db] = lambda: mock_db

        mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
        ci = AsyncMock()
        mock_httpx.return_value.__aenter__.return_value = ci
        svc = MagicMock(status_code=200)
        svc.json.return_value = {"access_token": "svc-token"}
        ci.post.return_value = svc
        r = client.post("/bulk-reanalyse/start", headers={"Authorization": "Bearer token"})
        assert r.status_code == 202
        data = r.json()
        assert data.get("total_cvs") == 42

        # Remettre l'override DB par défaut
        app.dependency_overrides[get_db] = override_get_db

    def test_start_returns_409_when_running(self, mocker):
        """POST /bulk-reanalyse/start doit retourner 409 si job déjà actif."""
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.is_running",
                     new=AsyncMock(return_value=True))
        r = client.post("/bulk-reanalyse/start", headers={"Authorization": "Bearer token"})
        assert r.status_code == 409

    def test_start_requires_admin_role(self, mocker):
        """POST /bulk-reanalyse/start doit retourner 403 pour non-admin."""
        app.dependency_overrides[verify_jwt] = lambda: {"sub": "u", "role": "rh"}
        r = client.post("/bulk-reanalyse/start", headers={"Authorization": "Bearer token"})
        assert r.status_code in [401, 403]
        app.dependency_overrides[verify_jwt] = override_verify_jwt

    def test_cancel_idle_resets_gracefully(self, mocker):
        """
        POST /bulk-reanalyse/cancel sur un état idle retourne 200 (reset gracieux).
        Le cancel ne lève pas d'erreur — il réinitialise toujours l'état.
        """
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.get_status",
                     new=AsyncMock(return_value=None))
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.reset", new=AsyncMock())
        r = client.post("/bulk-reanalyse/cancel", headers={"Authorization": "Bearer token"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True

    def test_cancel_running_job_resets_state(self, mocker):
        """POST /bulk-reanalyse/cancel doit appeler reset() si job actif."""
        state = {
            "status": "batch_running",
            "batch_job_id": "projects/p/locations/eu/batchPredictionJobs/abc",
        }
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.is_running",
                     new=AsyncMock(return_value=True))
        mocker.patch("src.cvs.router.bulk_reanalyse_manager.get_status",
                     new=AsyncMock(return_value=state))
        cancel_mock = mocker.patch("src.cvs.router.bulk_reanalyse_manager.cancel_soft",
                                  new=AsyncMock(return_value={"dest_uri": "gs://..."}))
        mock_httpx = mocker.patch("src.cvs.router.httpx.AsyncClient")
        ci = AsyncMock()
        mock_httpx.return_value.__aenter__.return_value = ci
        ci.post.return_value = MagicMock(status_code=200)
        r = client.post("/bulk-reanalyse/cancel", headers={"Authorization": "Bearer token"})
        assert r.status_code == 200
        cancel_mock.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# 3. MCP Tools
# ══════════════════════════════════════════════════════════════════════════════

class TestBulkReanalyseMcpTools:

    @pytest.mark.asyncio
    async def test_start_bulk_success(self, mocker):
        """start_bulk_cv_reanalyse doit appeler POST /bulk-reanalyse/start."""
        mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
        ci = AsyncMock()
        mock_httpx.return_value.__aenter__.return_value = ci
        resp = MagicMock(status_code=202)
        resp.json.return_value = {"message": "Pipeline lancé", "status": "building"}
        resp.raise_for_status = MagicMock()
        ci.post.return_value = resp
        mcp_auth_header_var.set("Bearer token")
        result = await call_tool(name="start_bulk_cv_reanalyse", arguments={})
        assert result[0].text
        assert "/bulk-reanalyse/start" in str(ci.post.call_args)

    @pytest.mark.asyncio
    async def test_start_bulk_conflict_409(self, mocker):
        """start_bulk_cv_reanalyse : 409 → message lisible."""
        mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
        ci = AsyncMock()
        mock_httpx.return_value.__aenter__.return_value = ci
        err_resp = MagicMock(status_code=409, text="déjà en cours")
        ci.post.side_effect = httpx.HTTPStatusError("409", request=MagicMock(), response=err_resp)
        mcp_auth_header_var.set("Bearer token")
        result = await call_tool(name="start_bulk_cv_reanalyse", arguments={})
        assert "409" in result[0].text or "cours" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_get_status_idle(self, mocker):
        """get_bulk_cv_reanalyse_status doit appeler GET /bulk-reanalyse/status."""
        mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
        ci = AsyncMock()
        mock_httpx.return_value.__aenter__.return_value = ci
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"status": "idle", "total_cvs": 0}
        resp.raise_for_status = MagicMock()
        ci.get.return_value = resp
        mcp_auth_header_var.set("Bearer token")
        result = await call_tool(name="get_bulk_cv_reanalyse_status", arguments={})
        assert "idle" in result[0].text
        assert "/bulk-reanalyse/status" in str(ci.get.call_args)

    @pytest.mark.asyncio
    async def test_get_status_api_error(self, mocker):
        """get_bulk_cv_reanalyse_status : erreur API → {"success": false}."""
        mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
        ci = AsyncMock()
        mock_httpx.return_value.__aenter__.return_value = ci
        err_resp = MagicMock(status_code=500, text="Internal error")
        ci.get.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=err_resp)
        mcp_auth_header_var.set("Bearer token")
        result = await call_tool(name="get_bulk_cv_reanalyse_status", arguments={})
        payload = json.loads(result[0].text)
        assert payload["success"] is False

    @pytest.mark.asyncio
    async def test_cancel_bulk_success(self, mocker):
        """cancel_bulk_cv_reanalyse doit appeler POST /bulk-reanalyse/cancel."""
        mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
        ci = AsyncMock()
        mock_httpx.return_value.__aenter__.return_value = ci
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"message": "Annulé"}
        resp.raise_for_status = MagicMock()
        ci.post.return_value = resp
        mcp_auth_header_var.set("Bearer token")
        result = await call_tool(name="cancel_bulk_cv_reanalyse", arguments={})
        assert "/bulk-reanalyse/cancel" in str(ci.post.call_args)

    @pytest.mark.asyncio
    async def test_cancel_bulk_network_error(self, mocker):
        """cancel_bulk_cv_reanalyse : erreur réseau → {"success": false}."""
        mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
        ci = AsyncMock()
        mock_httpx.return_value.__aenter__.return_value = ci
        ci.post.side_effect = Exception("Connection refused")
        mcp_auth_header_var.set("Bearer token")
        result = await call_tool(name="cancel_bulk_cv_reanalyse", arguments={})
        payload = json.loads(result[0].text)
        assert payload["success"] is False
        assert "Connection refused" in payload["error"]
