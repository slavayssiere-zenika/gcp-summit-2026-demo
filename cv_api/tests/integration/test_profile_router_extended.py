import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from src.cvs.models import CVProfile
import base64
import json
from sqlalchemy.ext.asyncio import AsyncSession

def test_force_invalidate_taxonomy_cache(client, wipe_cv_db):
    resp = client.post("/cache/invalidate-taxonomy")
    assert resp.status_code == 200

def test_get_all_user_tags(client, wipe_cv_db):
    # Appeler d'abord pour vérifier vide
    resp = client.get("/users/tags/map")
    assert resp.status_code == 200
    assert resp.json() == {}

@pytest.mark.asyncio
async def test_get_users_by_tag(client, wipe_cv_db):
    with patch("src.services.profile_service.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "is_anonymous": False}
        mock_get.return_value = mock_resp
        
        resp = client.get("/users/tag/test_tag")
        assert resp.status_code == 200
        assert "items" in resp.json()

@pytest.mark.asyncio
async def test_get_user_cv(client, wipe_cv_db):
    with patch("src.services.profile_service.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "is_anonymous": False}
        mock_get.return_value = mock_resp
        
        resp = client.get("/user/1")
        assert resp.status_code == 404

@pytest.mark.asyncio
async def test_get_user_cv_details(client, wipe_cv_db):
    with patch("src.services.profile_service.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "is_anonymous": False}
        mock_get.return_value = mock_resp
        
        resp = client.get("/user/1/details")
        assert resp.status_code == 404

def test_merge_users(client, wipe_cv_db):
    resp = client.post("/internal/users/merge", json={"source_id": 2, "target_id": 1}, headers={"Authorization": "Bearer token"})
    assert resp.status_code == 200

def test_handle_user_pubsub_events(client, wipe_cv_db):
    data = {"event": "user.merged", "data": {"source_id": 2, "target_id": 1}}
    encoded = base64.b64encode(json.dumps(data).encode()).decode()
    resp = client.post("/pubsub/user-events", json={"message": {"data": encoded}})
    assert resp.status_code == 200

def test_remediate_anonymous_profiles_dry_run(client, wipe_cv_db):
    with patch("src.services.profile_service.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"items": [{"id": 1, "email": "test@zenika.com", "is_anonymous": True}], "total": 1, "skip": 0, "limit": 100}
        mock_get.return_value = mock_resp
        
        resp = client.post("/internal/remediate-anonymous-profiles?dry_run=true", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 200
        assert resp.json()["candidates_to_fix"] == 1

def test_remediate_anonymous_profiles_execute(client, wipe_cv_db):
    resp = client.post("/internal/remediate-anonymous-profiles?dry_run=false", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
