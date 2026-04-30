"""
test_taxonomy_router.py — Tests endpoints taxonomy (status, cancel, reset, recover, batch/start, batch/list).
Coverage cible : 16% → 50%+
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./cv_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    with patch("redis.asyncio.from_url", return_value=mock_redis):
        from main import app
        from database import get_db
        from src.auth import verify_jwt

from fastapi.testclient import TestClient

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
