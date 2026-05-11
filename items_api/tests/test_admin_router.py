from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from src.auth import verify_jwt
from database import get_db

client = TestClient(app, raise_server_exceptions=False)

from conftest import override_get_db, override_verify_jwt as orig_verify_jwt

def local_override_verify_jwt():
    return {"sub": "admin", "role": "admin"}

@pytest.fixture(autouse=True)
def setup_and_clear_overrides():
    app.dependency_overrides[verify_jwt] = local_override_verify_jwt
    yield
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_jwt] = orig_verify_jwt

def test_delete_user_items_success():
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.delete("/user/1/items")
    assert resp.status_code == 204
    assert mock_db.execute.called
    assert mock_db.commit.called

def test_delete_user_items_forbidden():
    def override_verify_jwt_forbidden():
        return {"sub": "user", "role": "user"}
    app.dependency_overrides[verify_jwt] = override_verify_jwt_forbidden
    
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.delete("/user/1/items")
    assert resp.status_code == 403

def test_pubsub_user_events_success():
    import base64
    import json
    
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    data = json.dumps({"event": "user.merged", "data": {"source_id": 1, "target_id": 2}})
    b64_data = base64.b64encode(data.encode("utf-8")).decode("utf-8")
    
    resp = client.post("/pubsub/user-events", json={
        "message": {
            "data": b64_data
        }
    })
    
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    assert mock_db.execute.called
    assert mock_db.commit.called

def test_pubsub_user_events_invalid_json():
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.post("/pubsub/user-events", content="not_json")
    assert resp.status_code == 400

def test_pubsub_user_events_ignored():
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.post("/pubsub/user-events", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

def test_pubsub_user_events_error():
    import base64
    import json
    
    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("DB crash")
    app.dependency_overrides[get_db] = lambda: mock_db
    
    data = json.dumps({"event": "user.merged", "data": {"source_id": 1, "target_id": 2}})
    b64_data = base64.b64encode(data.encode("utf-8")).decode("utf-8")
    
    resp = client.post("/pubsub/user-events", json={
        "message": {
            "data": b64_data
        }
    })
    
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"

def test_merge_users_success():
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.post("/internal/users/merge", json={"source_id": 1, "target_id": 2})
    assert resp.status_code == 200
    assert mock_db.execute.called
    assert mock_db.commit.called
