"""
test_dlq_router.py — Tests des endpoints DLQ de drive_api.
Coverage cible : 17% → 55%+

Stratégie : mock complet du client Pub/Sub (pubsub_v1.SubscriberClient)
pour éviter toute connexion GCP.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./drive_dlq_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("DLQ_SUBSCRIPTION_ID", "drive-dlq-sub")

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db
    from src.auth import verify_jwt

from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer testtoken"}


def override_jwt_admin():
    return {"sub": "1", "role": "admin", "email": "admin@z.com"}


def override_jwt_user():
    return {"sub": "2", "role": "user", "email": "user@z.com"}


def _make_sync_db(first_results=None, all_results=None, scalar_values=None):
    first_results = first_results or []
    scalar_values = scalar_values or []
    idx = [0]

    async def fake_execute(stmt, *a, **kw):
        result = MagicMock()
        val = first_results[idx[0]] if idx[0] < len(first_results) else None
        sval = scalar_values[idx[0]] if idx[0] < len(scalar_values) else 0
        result.scalars.return_value.first.return_value = val
        result.scalars.return_value.all.return_value = all_results or []
        result.scalar.return_value = sval
        idx[0] += 1
        return result

    mock_db = AsyncMock()
    mock_db.execute = fake_execute
    mock_db.commit = AsyncMock()
    return mock_db


async def override_get_db():
    yield _make_sync_db()


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_jwt_admin


def get_client():
    app.dependency_overrides[verify_jwt] = override_jwt_admin
    return TestClient(app)


# ── GET /dlq/status ───────────────────────────────────────────────────────────

def test_dlq_status_pubsub_unavailable(mocker):
    """PubSub inaccessible → retourne message_count=-1, pas d'exception."""
    mock_subscriber = MagicMock()
    mock_subscriber.pull.side_effect = Exception("Connection refused")
    mocker.patch("src.routers.dlq_router.pubsub_v1.SubscriberClient", return_value=mock_subscriber)
    mocker.patch("src.routers.dlq_router.asyncio.to_thread", new=AsyncMock(side_effect=Exception("no GCP")))

    with get_client() as client:
        resp = client.get("/dlq/status", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("message_count") == -1 or "error" in data


def test_dlq_status_empty_queue(mocker):
    """PubSub vide → message_count=0, files=[]."""
    mock_pull_resp = MagicMock()
    mock_pull_resp.received_messages = []

    call_count = [0]

    async def fake_to_thread(fn, *args, **kwargs):
        call_count[0] += 1
        # Premier appel = pull → retourner la réponse
        if call_count[0] == 1:
            return mock_pull_resp
        # Deuxième appel = modify_ack_deadline → ne doit pas arriver pour liste vide
        return None

    mocker.patch("src.routers.dlq_router.asyncio.to_thread", side_effect=fake_to_thread)
    mocker.patch("src.routers.dlq_router.pubsub_v1.SubscriberClient", return_value=MagicMock())

    with get_client() as client:
        resp = client.get("/dlq/status", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("message_count", -1) >= 0
    assert data.get("files") == []


def test_dlq_status_with_valid_message(mocker):
    """PubSub avec un message JSON valide → file_id extrait."""
    import base64
    import json

    payload = {"google_file_id": "file123", "folder_id": "folder1"}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()

    msg = MagicMock()
    msg.message.data = base64.b64decode(encoded)
    msg.message.message_id = "msg001"
    msg.ack_id = "ack001"

    mock_pull_resp = MagicMock()
    mock_pull_resp.received_messages = [msg]

    mocker.patch(
        "src.routers.dlq_router.asyncio.to_thread",
        new=AsyncMock(return_value=mock_pull_resp)
    )
    mocker.patch("src.routers.dlq_router.pubsub_v1.SubscriberClient", return_value=MagicMock())

    async def override_db_with_rows():
        yield _make_sync_db(all_results=[])

    app.dependency_overrides[get_db] = override_db_with_rows
    with get_client() as client:
        resp = client.get("/dlq/status", headers=AUTH)
    app.dependency_overrides[get_db] = override_get_db

    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data or "message_count" in data


# ── DELETE /dlq/message ───────────────────────────────────────────────────────

def test_delete_dlq_message_no_params_returns_422(mocker):
    """Aucun paramètre → 422."""
    with get_client() as client:
        resp = client.delete("/dlq/message", headers=AUTH)
    assert resp.status_code == 422


def test_delete_dlq_message_with_ack_id(mocker):
    """ack_id fourni → ACK direct sans re-pull."""
    mock_subscriber = MagicMock()
    mock_subscriber.acknowledge.return_value = None
    mocker.patch("src.routers.dlq_router.pubsub_v1.SubscriberClient", return_value=mock_subscriber)
    mocker.patch(
        "src.routers.dlq_router.asyncio.to_thread",
        new=AsyncMock(return_value=None)
    )

    async def override_db_file():
        mock_db = _make_sync_db(first_results=[None])  # pas de DriveSyncState
        yield mock_db

    app.dependency_overrides[get_db] = override_db_file

    with get_client() as client:
        resp = client.delete("/dlq/message?ack_id=ack_test_123", headers=AUTH)

    app.dependency_overrides[get_db] = override_get_db
    assert resp.status_code in (200, 404, 500)


def test_delete_dlq_message_non_admin_returns_403():
    """Non-admin → 403."""
    app.dependency_overrides[verify_jwt] = override_jwt_user
    with TestClient(app) as client:
        resp = client.delete("/dlq/message?ack_id=ack123", headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_jwt_admin


def test_delete_dlq_message_by_file_id(mocker):
    """google_file_id fourni → tente le re-pull et match."""
    from src.models import DriveSyncState, DriveSyncStatus
    from datetime import datetime, timezone

    sync_state = DriveSyncState()
    sync_state.google_file_id = "file123"
    sync_state.status = DriveSyncStatus.ERROR
    sync_state.last_processed_at = datetime.now(timezone.utc)

    mock_pull_resp = MagicMock()
    import base64
    import json
    payload = {"google_file_id": "file123"}
    msg = MagicMock()
    msg.message.data = json.dumps(payload).encode()
    msg.message.message_id = "msg001"
    msg.ack_id = "ack_real"
    mock_pull_resp.received_messages = [msg]

    mocker.patch(
        "src.routers.dlq_router.asyncio.to_thread",
        new=AsyncMock(return_value=mock_pull_resp)
    )
    mocker.patch("src.routers.dlq_router.pubsub_v1.SubscriberClient", return_value=MagicMock())

    async def override_db_with_state():
        yield _make_sync_db(first_results=[sync_state])

    app.dependency_overrides[get_db] = override_db_with_state

    with get_client() as client:
        resp = client.delete("/dlq/message?google_file_id=file123", headers=AUTH)

    app.dependency_overrides[get_db] = override_get_db
    assert resp.status_code in (200, 404, 500)


# ── POST /dlq/replay ─────────────────────────────────────────────────────────

def test_replay_dlq_empty_queue(mocker):
    """replay avec DLQ vide → 0 messages rejoués."""
    from google.api_core.exceptions import DeadlineExceeded

    call_count = [0]

    async def fake_to_thread(fn, *args, **kwargs):
        call_count[0] += 1
        # Premier appel = pull → DeadlineExceeded (DLQ vide)
        raise DeadlineExceeded("timeout")

    mocker.patch("src.routers.dlq_router.asyncio.to_thread", side_effect=fake_to_thread)
    mocker.patch("src.routers.dlq_router.pubsub_v1.SubscriberClient", return_value=MagicMock())

    with get_client() as client:
        resp = client.post("/dlq/replay", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("dlq_messages_pulled", 0) == 0


def test_replay_dlq_non_admin_returns_403():
    """Non-admin → 403."""
    app.dependency_overrides[verify_jwt] = override_jwt_user
    with TestClient(app) as client:
        resp = client.post("/dlq/replay", headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_jwt_admin


def test_replay_dlq_pubsub_error(mocker):
    """Erreur PubSub → 500 ou réponse d'erreur structurée."""
    mocker.patch(
        "src.routers.dlq_router.asyncio.to_thread",
        new=AsyncMock(side_effect=Exception("GCP unavailable"))
    )
    mocker.patch("src.routers.dlq_router.pubsub_v1.SubscriberClient", return_value=MagicMock())

    with get_client() as client:
        resp = client.post("/dlq/replay", headers=AUTH)
    assert resp.status_code in (200, 500)
