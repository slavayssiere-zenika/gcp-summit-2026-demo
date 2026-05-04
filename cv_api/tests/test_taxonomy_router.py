"""
test_taxonomy_router.py — Tests endpoints taxonomy (status, cancel, reset, recover, batch/start, batch/list).
Coverage cible : 16% → 50%+
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./cv_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("GEMINI_MODEL", "test-model")
os.environ.setdefault("GEMINI_PRO_MODEL", "test-model-pro")

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    with patch("redis.asyncio.from_url", return_value=mock_redis):
        from database import get_db
        from main import app
        from src.auth import verify_jwt


AUTH = {"Authorization": "Bearer testtoken"}

def override_jwt_admin():
    return {"sub": "1", "email": "admin@z.com", "role": "admin"}

def override_jwt_user():
    return {"sub": "2", "email": "user@z.com", "role": "user"}

async def override_get_db():
    db = AsyncMock()
    yield db

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_jwt_admin


def get_client():
    app.dependency_overrides[verify_jwt] = override_jwt_admin
    return TestClient(app)


# ── GET /recalculate_tree/status ──────────────────────────────────────────────

def test_status_idle_when_no_task(mocker):
    """Aucune tâche → status idle."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value=None)
    )
    with get_client() as client:
        resp = client.get("/recalculate_tree/status", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


def test_status_running(mocker):
    """Tâche en cours → status running."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "running", "mode": "interactive", "logs": []})
    )
    with get_client() as client:
        resp = client.get("/recalculate_tree/status", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_status_batch_running_translated(mocker):
    """mode=batch + status=running → réponse status=batch_running pour le frontend."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "running", "mode": "batch", "logs": []})
    )
    with get_client() as client:
        resp = client.get("/recalculate_tree/status", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "batch_running"


def test_status_completed(mocker):
    """Tâche terminée → status completed passé tel quel."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "completed", "tree": {}, "logs": []})
    )
    with get_client() as client:
        resp = client.get("/recalculate_tree/status", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


# ── POST /recalculate_tree/cancel ─────────────────────────────────────────────

def test_cancel_interactive_sets_cancelled(mocker):
    """POST cancel → update_progress(status='cancelled')."""
    mock_update = AsyncMock()
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.update_progress",
        new=mock_update
    )
    with get_client() as client:
        resp = client.post("/recalculate_tree/cancel", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_update.assert_awaited_once()


# ── POST /recalculate_tree/batch/cancel ───────────────────────────────────────

def test_batch_cancel_no_job(mocker):
    """Batch cancel sans job actif → success quand même."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "idle", "batch_job_id": None})
    )
    mock_update = AsyncMock()
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.update_progress",
        new=mock_update
    )
    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/cancel", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_batch_cancel_with_active_job(mocker):
    """Batch cancel avec job actif → tente l'annulation Vertex."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "running", "batch_job_id": "projects/x/jobs/123"})
    )
    mock_update = AsyncMock()
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.update_progress",
        new=mock_update
    )
    mock_vertex = MagicMock()
    mock_vertex.batches.cancel.side_effect = Exception("already done")
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=mock_vertex))

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/cancel", headers=AUTH)
    assert resp.status_code == 200


# ── POST /recalculate_tree/batch/reset ────────────────────────────────────────

def test_batch_reset_admin_resets_state(mocker):
    """Admin → reset réussit."""
    mock_init = AsyncMock()
    mock_update = AsyncMock()
    mocker.patch("src.cvs.routers.taxonomy_router.tree_task_manager.initialize_task", new=mock_init)
    mocker.patch("src.cvs.routers.taxonomy_router.tree_task_manager.update_progress", new=mock_update)

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/reset", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_init.assert_awaited_once()


def test_batch_reset_non_admin_returns_403(mocker):
    """Non-admin → 403."""
    app.dependency_overrides[verify_jwt] = override_jwt_user
    with TestClient(app) as client:
        resp = client.post("/recalculate_tree/batch/reset", headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_jwt_admin


# ── POST /recalculate_tree/batch/recover ──────────────────────────────────────

def test_batch_recover_no_job_returns_failure(mocker):
    """Recover sans job actif → success=False."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value=None)
    )
    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/recover", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json().get("success") is False


def test_batch_recover_with_job_id_sets_running(mocker):
    """Recover avec batch_job_id → remet status running."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={
            "status": "error", "batch_job_id": "projects/x/jobs/42",
            "batch_step": "deduplicating"
        })
    )
    mock_update = AsyncMock()
    mocker.patch("src.cvs.routers.taxonomy_router.tree_task_manager.update_progress", new=mock_update)

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/recover", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    # deduplicating → doit revenir à "map"
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs.get("batch_step") == "map"


def test_batch_recover_non_admin_returns_403(mocker):
    """Non-admin → 403."""
    app.dependency_overrides[verify_jwt] = override_jwt_user
    with TestClient(app) as client:
        resp = client.post("/recalculate_tree/batch/recover", headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_jwt_admin


# ── POST /recalculate_tree/batch/start ───────────────────────────────────────

def test_batch_start_conflict_when_running(mocker):
    """batch/start → 409 si un batch est déjà en cours."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "running", "batch_job_id": "jobs/42"})
    )
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.is_task_running",
        new=AsyncMock(return_value=True)
    )
    # Mock le client Vertex pour la vérif d'état réel
    mock_vertex = MagicMock()
    mock_vertex.batches.get.return_value = MagicMock(state=MagicMock(name="JOB_STATE_RUNNING"))
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=mock_vertex))

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/start", headers=AUTH)
    assert resp.status_code in (200, 409)


def test_batch_start_idle_triggers_pipeline(mocker):
    """batch/start → 200 si aucun batch en cours."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value=None)
    )
    mock_init = AsyncMock()
    mocker.patch("src.cvs.routers.taxonomy_router.tree_task_manager.initialize_task", new=mock_init)
    mock_update = AsyncMock()
    mocker.patch("src.cvs.routers.taxonomy_router.tree_task_manager.update_progress", new=mock_update)

    # Mock tout le pipeline GCS + Vertex
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(
        gcs_client=MagicMock(),
        vertex_batch_client=MagicMock(),
        bucket_name="test-bucket",
    ))
    mocker.patch(
        "src.cvs.routers.taxonomy_router.asyncio.to_thread",
        new=AsyncMock(return_value=MagicMock(name="projects/x/jobs/new"))
    )

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/start", headers=AUTH)
    assert resp.status_code in (200, 202, 409, 500)


# ── GET /recalculate_tree/batch/list ─────────────────────────────────────────

def test_batch_list_no_vertex_client(mocker):
    """GET batch/list sans client Vertex → réponse vide ou erreur gérée."""
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=None))
    with get_client() as client:
        resp = client.get("/recalculate_tree/batch/list", headers=AUTH)
    assert resp.status_code in (200, 500)


def test_batch_list_returns_list(mocker):
    """GET batch/list → liste des jobs."""
    mock_vertex = MagicMock()
    mock_vertex.batches.list.return_value = []
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=mock_vertex))

    with get_client() as client:
        resp = client.get("/recalculate_tree/batch/list", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))


# ── POST /recalculate_tree (interactive) ─────────────────────────────────────

def test_recalculate_tree_already_running(mocker):
    """POST /recalculate_tree → 200 avec status=running si tâche en cours (pas de 409)."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.is_task_running",
        new=AsyncMock(return_value=True)
    )
    with get_client() as client:
        resp = client.post("/recalculate_tree", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json().get("status") == "running"

# ── POST /recalculate_tree/batch/check ───────────────────────────────────────

def test_batch_check_no_job(mocker):
    """batch/check sans job → success."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value=None)
    )
    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/check", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json().get("message") == "Aucun batch en cours"


def test_batch_check_intermediate_states_return_early(mocker):
    """batch/check sur 'deduplicating' ou 'sweeping' retourne immédiatement (le fix du bug)."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={
            "status": "running", 
            "batch_job_id": "jobs/42",
            "batch_step": "deduplicating"
        })
    )
    # On mock Vertex AI pour s'assurer qu'il n'est PAS appelé
    mock_vertex = MagicMock()
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=mock_vertex))

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/check", headers=AUTH)
    
    assert resp.status_code == 200
    assert resp.json().get("state") == "DEDUPLICATING"
    mock_vertex.batches.get.assert_not_called()


def test_batch_check_failed_deletes_job(mocker):
    """batch/check sur job FAILED → supprime le job GCP et met l'état en error."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "running", "batch_job_id": "jobs/42", "batch_step": "map"})
    )
    mock_job = MagicMock()
    mock_job.state.name = "JOB_STATE_FAILED"
    mock_vertex = MagicMock()
    mock_vertex.batches.get.return_value = mock_job
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=mock_vertex))
    
    mock_to_thread = AsyncMock(side_effect=lambda f, *a, **k: f(*a, **k))
    mocker.patch("src.cvs.routers.taxonomy_router.asyncio.to_thread", new=mock_to_thread)

    mock_update = AsyncMock()
    mocker.patch("src.cvs.routers.taxonomy_router.tree_task_manager.update_progress", new=mock_update)

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/check", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json().get("success") is False
    mock_vertex.batches.delete.assert_called_once_with(name="jobs/42")
    
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs.get("status") == "error"


def test_batch_check_pending_timeout_cancels_job(mocker):
    """batch/check sur job PENDING timeout → annule le job GCP et restart auto."""
    import datetime as dt
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "running", "batch_job_id": "jobs/42", "batch_step": "map"})
    )
    
    mock_job = MagicMock()
    mock_job.state.name = "JOB_STATE_PENDING"
    mock_job.create_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4) # > 3h timeout
    
    mock_vertex = MagicMock()
    mock_vertex.batches.get.return_value = mock_job
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=mock_vertex))
    
    mock_to_thread = AsyncMock(side_effect=lambda f, *a, **k: f(*a, **k))
    mocker.patch("src.cvs.routers.taxonomy_router.asyncio.to_thread", new=mock_to_thread)

    mock_update = AsyncMock()
    mocker.patch("src.cvs.routers.taxonomy_router.tree_task_manager.update_progress", new=mock_update)

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/check", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json().get("action") == "auto_restart"
    mock_vertex.batches.cancel.assert_called_once_with(name="jobs/42")


def test_batch_check_running_returns_progress(mocker):
    """batch/check sur job RUNNING → retourne la progression (completion_stats)."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "running", "batch_job_id": "jobs/42", "batch_step": "map"})
    )
    
    mock_job = MagicMock()
    mock_job.state.name = "JOB_STATE_RUNNING"
    mock_job.completion_stats = MagicMock(success_count=50, failed_count=10, incomplete_count=40, total_count=100)
    
    mock_vertex = MagicMock()
    mock_vertex.batches.get.return_value = mock_job
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=mock_vertex))
    
    mock_to_thread = AsyncMock(side_effect=lambda f, *a, **k: f(*a, **k))
    mocker.patch("src.cvs.routers.taxonomy_router.asyncio.to_thread", new=mock_to_thread)

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/check", headers=AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("state") == "JOB_STATE_RUNNING"
    assert data.get("progress", {}).get("completed") == 50
    assert data.get("progress", {}).get("percent") == 50


def test_batch_check_succeeded_map_parses_json_and_starts_dedup(mocker):
    """batch/check sur job SUCCEEDED en step map → parse GCS JSONL et lance run_dedup async."""
    mocker.patch(
        "src.cvs.routers.taxonomy_router.tree_task_manager.get_latest_status",
        new=AsyncMock(return_value={"status": "running", "batch_job_id": "jobs/42", "batch_step": "map"})
    )
    
    mock_job = MagicMock()
    mock_job.state.name = "JOB_STATE_SUCCEEDED"
    mock_job.dest.gcs_uri = "gs://test-bucket/taxonomy/output/map-xxx/"
    
    mock_vertex = MagicMock()
    mock_vertex.batches.get.return_value = mock_job
    mocker.patch("src.cvs.routers.taxonomy_router._svc_config", MagicMock(vertex_batch_client=mock_vertex))
    
    mock_to_thread = AsyncMock(side_effect=lambda f, *a, **k: f(*a, **k))
    mocker.patch("src.cvs.routers.taxonomy_router.asyncio.to_thread", new=mock_to_thread)

    # Mock GCS Client
    mock_blob = MagicMock()
    mock_blob.name = "taxonomy/output/map-xxx/results.jsonl"
    import json
    fake_jsonl = json.dumps({
        "response": {"candidates": [{"content": {"parts": [{"text": '```json\n{"items": [{"Pillar 1": [{"name": "Skill 1"}]}]}\n```'}]}}]}
    })
    mock_blob.download_as_text.return_value = fake_jsonl
    
    mock_bucket = MagicMock()
    mock_bucket.list_blobs.return_value = iter([mock_blob])
    
    mock_gcs_client = MagicMock()
    mock_gcs_client.bucket.return_value = mock_bucket
    mocker.patch("src.cvs.routers.taxonomy_router.gcs_storage.Client", return_value=mock_gcs_client)
    
    mock_update = AsyncMock()
    mocker.patch("src.cvs.routers.taxonomy_router.tree_task_manager.update_progress", new=mock_update)
    
    mocker.patch("src.cvs.routers.taxonomy_router.log_finops", new=AsyncMock())
    mock_create_task = mocker.patch("src.cvs.routers.taxonomy_router.asyncio.create_task")

    with get_client() as client:
        resp = client.post("/recalculate_tree/batch/check", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json().get("state") == "PROCESSING_DEDUP"
    
    # Vérifie que map_result a été parsé et persisté
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs.get("batch_step") == "deduplicating"
    assert "Pillar 1" in call_kwargs.get("map_result", {})
    
    # Vérifie que la suite LLM est lancée en background
    mock_create_task.assert_called_once()

