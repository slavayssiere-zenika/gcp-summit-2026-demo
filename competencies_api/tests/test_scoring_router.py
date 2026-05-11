from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from src.competencies.scoring_router import verify_scheduler_oidc

client = TestClient(app, raise_server_exceptions=False)

def override_verify_jwt():
    return {"sub": "admin", "role": "admin"}

def override_verify_scheduler_oidc():
    return None

from src.auth import verify_jwt

app.dependency_overrides[verify_jwt] = override_verify_jwt
app.dependency_overrides[verify_scheduler_oidc] = override_verify_scheduler_oidc

from database import get_db

# --- /evaluations/bulk-scoring-all ---

@patch("src.competencies.scoring_router.bulk_scoring_manager.is_running", new_callable=AsyncMock)
@patch("src.competencies.scoring_router.bulk_scoring_manager.initialize", new_callable=AsyncMock)
def test_trigger_bulk_scoring_all_success(mock_init, mock_is_running):
    mock_is_running.return_value = False
    
    # We mock db so it returns some user ids
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [1, 2]
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    app.dependency_overrides[get_db] = lambda: mock_db
    
    with patch("src.competencies.scoring_router.os.getenv") as mock_getenv:
        def getenv_side_effect(key, default=""):
            if key == "GCP_PROJECT_ID": return "p1"
            if key == "BATCH_GCS_BUCKET": return "b1"
            return default
        mock_getenv.side_effect = getenv_side_effect
        
        with patch("src.competencies.scoring_router.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post_resp = MagicMock()
            mock_post_resp.status_code = 200
            mock_post_resp.json.return_value = {"access_token": "fake_token", "token_type": "Bearer"}
            mock_post.return_value = mock_post_resp
            
            resp = client.post("/evaluations/bulk-scoring-all?force=true")
            assert resp.status_code == 202
            assert resp.json()["triggered"] == 2
            
            mock_init.assert_called_once()

@patch("src.competencies.scoring_router.bulk_scoring_manager.is_running", new_callable=AsyncMock)
@patch("src.competencies.scoring_router.bulk_scoring_manager.initialize", new_callable=AsyncMock)
def test_trigger_bulk_scoring_all_no_force(mock_init, mock_is_running):
    mock_is_running.return_value = False
    
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [3, 4, 5]
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    app.dependency_overrides[get_db] = lambda: mock_db
    
    with patch("src.competencies.scoring_router.os.getenv") as mock_getenv:
        mock_getenv.return_value = "" # no Vertex AI configured -> fallback
        
        with patch("src.competencies.scoring_router.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock() # Will trigger fallback exception handling
            mock_post.return_value.status_code = 500
            
            with patch("src.competencies.scoring_router.BackgroundTasks.add_task") as mock_add_task:
                resp = client.post("/evaluations/bulk-scoring-all?force=false")
                assert resp.status_code == 202
                assert resp.json()["triggered"] == 3
                mock_init.assert_called_once()
                mock_add_task.assert_called_once()

# --- /bulk-scoring-all/status ---

@patch("src.competencies.scoring_router.bulk_scoring_manager.get_status", new_callable=AsyncMock)
def test_get_bulk_scoring_status(mock_status):
    mock_status.return_value = {"status": "running"}
    resp = client.get("/bulk-scoring-all/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

# --- /bulk-scoring-all/cancel ---

@patch("src.competencies.scoring_router.bulk_scoring_manager.reset", new_callable=AsyncMock)
@patch("src.competencies.scoring_router.set_scoring_scheduler_enabled", new_callable=AsyncMock)
def test_cancel_bulk_scoring(mock_set_sched, mock_reset):
    resp = client.post("/bulk-scoring-all/cancel")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_reset.assert_called_once()
    mock_set_sched.assert_called_once_with(False)

# --- /bulk-scoring-all/resume/manual ---

@patch("src.competencies.scoring_router.bulk_scoring_manager.get_status", new_callable=AsyncMock)
def test_resume_bulk_scoring_noop(mock_get_status):
    mock_get_status.return_value = {"status": "idle"}
    resp = client.post("/bulk-scoring-all/resume/manual")
    assert resp.status_code == 200
    assert resp.json()["action"] == "noop"

@patch("src.competencies.scoring_router.bulk_scoring_manager.get_status", new_callable=AsyncMock)
@patch("src.competencies.scoring_router.GCP_PROJECT_ID", "p1")
@patch("src.competencies.scoring_router.BATCH_GCS_BUCKET", "b1")
@patch("src.competencies.scoring_router.bulk_scoring_manager.update_progress", new_callable=AsyncMock)
def test_resume_bulk_scoring_succeeded(mock_update, mock_get_status):
    mock_get_status.return_value = {"status": "batch_running", "batch_job_id": "j1", "dest_uri": "gs://b/out"}
    
    with patch("google.genai.Client") as mock_genai:
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_genai.return_value.batches.get.return_value = mock_job
        
        with patch("src.competencies.scoring_router.BackgroundTasks.add_task") as mock_add_task:
            resp = client.post("/bulk-scoring-all/resume/manual")
            assert resp.status_code == 200
            assert resp.json()["action"] == "apply_triggered"
            mock_add_task.assert_called_once()

@patch("src.competencies.scoring_router.bulk_scoring_manager.get_status", new_callable=AsyncMock)
@patch("src.competencies.scoring_router.GCP_PROJECT_ID", "p1")
@patch("src.competencies.scoring_router.BATCH_GCS_BUCKET", "b1")
@patch("src.competencies.scoring_router.bulk_scoring_manager.update_progress", new_callable=AsyncMock)
def test_resume_bulk_scoring_failed(mock_update, mock_get_status):
    mock_get_status.return_value = {"status": "batch_running", "batch_job_id": "j1", "dest_uri": "gs://b/out"}
    
    with patch("google.genai.Client") as mock_genai:
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_FAILED"
        mock_genai.return_value.batches.get.return_value = mock_job
        
        resp = client.post("/bulk-scoring-all/resume/manual")
        assert resp.status_code == 200
        assert resp.json()["action"] == "error"
        mock_update.assert_called_with(status="error", error="[resume] Vertex job JOB_STATE_FAILED.")

# --- verify_scheduler_oidc ---

@pytest.mark.asyncio
async def test_verify_scheduler_oidc_no_audience():
    from fastapi import Request, HTTPException
    from src.competencies.scoring_router import verify_scheduler_oidc
    
    with patch("src.competencies.scoring_router.SCHEDULER_AUDIENCE", ""):
        with pytest.raises(HTTPException) as exc:
            await verify_scheduler_oidc(Request(scope={"type": "http", "headers": []}))
        assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_verify_scheduler_oidc_no_header():
    from fastapi import Request, HTTPException
    from src.competencies.scoring_router import verify_scheduler_oidc
    
    with patch("src.competencies.scoring_router.SCHEDULER_AUDIENCE", "aud"):
        with pytest.raises(HTTPException) as exc:
            await verify_scheduler_oidc(Request(scope={"type": "http", "headers": []}))
        assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_verify_scheduler_oidc_success():
    from fastapi import Request
    from src.competencies.scoring_router import verify_scheduler_oidc
    
    with patch("src.competencies.scoring_router.SCHEDULER_AUDIENCE", "aud"):
        with patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
            mock_verify.return_value = {"email": "test@test.com"}
            await verify_scheduler_oidc(Request(scope={"type": "http", "headers": [(b"authorization", b"Bearer token")]}))
            mock_verify.assert_called_once()


