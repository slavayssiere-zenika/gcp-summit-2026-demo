import pytest
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from database import get_db
from src.auth import verify_jwt
from src.routers.folders_router import _require_admin

client = TestClient(app, raise_server_exceptions=False)

async def override_get_db():
    yield AsyncMock()

app.dependency_overrides[get_db] = override_get_db

def test_require_admin():
    with pytest.raises(HTTPException, match="Privilèges administrateur requis"):
        _require_admin({"role": "user"})
        
    assert _require_admin({"role": "admin"}) == {"role": "admin"}

@pytest.mark.asyncio
@patch('src.routers.folders_router.FolderService')
async def test_add_folder(mock_service_class):
    mock_service = MagicMock()
    
    class MockFolder:
        id = 1
        google_folder_id = "123"
        tag = "tag1"
        folder_name = "Test"
        excluded_folders = []
        is_initial_sync_done = False
        created_at = datetime.datetime.now(datetime.timezone.utc)
        
    mock_service.add_folder = AsyncMock(return_value=MockFolder())
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    response = client.post("/folders", json={"google_folder_id": "123", "tag": "tag1", "folder_name": "Test"})
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json()["google_folder_id"] == "123"

@pytest.mark.asyncio
@patch('src.routers.folders_router.FolderService')
async def test_update_folder(mock_service_class):
    mock_service = MagicMock()
    
    class MockFolder:
        id = 1
        google_folder_id = "123"
        tag = "new_tag"
        folder_name = "Test"
        excluded_folders = []
        is_initial_sync_done = False
        created_at = datetime.datetime.now(datetime.timezone.utc)
        
    mock_service.update_folder = AsyncMock(return_value=MockFolder())
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    response = client.patch("/folders/1", json={"tag": "new_tag"})
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json()["tag"] == "new_tag"

@pytest.mark.asyncio
@patch('src.routers.folders_router.FolderService')
async def test_list_folders(mock_service_class):
    mock_service = MagicMock()
    
    class MockFolder:
        id = 1
        google_folder_id = "123"
        tag = "tag1"
        folder_name = "Test"
        excluded_folders = []
        is_initial_sync_done = False
        created_at = datetime.datetime.now(datetime.timezone.utc)
        
    mock_service.list_folders_with_stats = AsyncMock(return_value=([MockFolder()], {1: {"PENDING": 5}}, 1))
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    response = client.get("/folders")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["stats"]["pending"] == 5

@pytest.mark.asyncio
@patch('src.routers.folders_router.FolderService')
async def test_reset_folder_sync(mock_service_class):
    mock_service = MagicMock()
    mock_service.reset_folder_sync = AsyncMock(return_value=5)
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    response = client.post("/folders/reset-sync?tag=t1")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json()["rows_updated"] == 5

@pytest.mark.asyncio
async def test_rebuild_folder_tree():
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    response = client.post("/folders/rebuild-tree")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200

@pytest.mark.asyncio
@patch('src.routers.folders_router.FolderService')
async def test_invalidate_drive_cache(mock_service_class):
    mock_service_class.invalidate_drive_cache.return_value = 10
    
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    response = client.post("/folders/invalidate-cache")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json()["keys_deleted"] == 10

@pytest.mark.asyncio
@patch('src.routers.folders_router.FolderService')
async def test_delete_folder(mock_service_class):
    mock_service = MagicMock()
    mock_service.delete_folder = AsyncMock(return_value=5)
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    response = client.delete("/folders/1")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json()["files_removed"] == 5
