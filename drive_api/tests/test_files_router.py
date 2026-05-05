import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from database import get_db
from src.auth import verify_jwt
from src.models import DriveSyncStatus

client = TestClient(app, raise_server_exceptions=False)

async def override_get_db():
    mock_db = AsyncMock()
    yield mock_db

app.dependency_overrides[get_db] = override_get_db

@pytest.mark.asyncio
@patch('src.routers.files_router.get_db')
async def test_get_status(mock_get_db):
    mock_db = AsyncMock()
    mock_scalar = MagicMock(scalar=MagicMock(side_effect=[100, 10, 20, 30, 40, 50, 60, None]))
    mock_db.execute.return_value = mock_scalar
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    
    response = client.get("/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_files_scanned"] == 100
    assert data["pending"] == 10

@pytest.mark.asyncio
async def test_list_files():
    mock_db = AsyncMock()
    mock_scalar = MagicMock(scalar=MagicMock(return_value=10))
    mock_scalars = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    mock_db.execute.side_effect = [mock_scalar, mock_scalars]
    
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    
    response = client.get("/files?status=PENDING&folder_id=1&search=test")
    
    assert response.status_code == 200
    assert response.json()["total"] == 10
    assert response.json()["files"] == []

@pytest.mark.asyncio
async def test_get_file_state():
    mock_db = AsyncMock()
    mock_file = MagicMock()
    mock_file.google_file_id = "test_id"
    mock_file.status = DriveSyncStatus.PENDING
    mock_file.revision_id = "r1"
    mock_file.modified_time = "2023-01-01T00:00:00Z"
    mock_file.file_name = "test.doc"
    mock_file.parent_folder_name = "parent"
    mock_file.error_message = None
    mock_file.file_type = "google_doc"
    mock_file.user_id = None
    mock_file.folder_id = 1
    mock_file.last_processed_at = None
    mock_file.imported_at = None
    mock_file.processing_duration_ms = None
    
    mock_scalars = MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_file))))
    mock_db.execute.return_value = mock_scalars
    
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    
    response = client.get("/files/test_id")
    
    assert response.status_code == 200
    assert response.json()["google_file_id"] == "test_id"

@pytest.mark.asyncio
async def test_search_consultant_files():
    mock_db = AsyncMock()
    mock_file = MagicMock()
    mock_file.google_file_id = "test_id"
    mock_file.file_name = "CV"
    mock_file.parent_folder_name = "test"
    mock_file.status = "PENDING"
    mock_file.user_id = 1
    mock_file.folder_id = 1
    mock_file.error_message = None
    
    mock_scalars = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_file]))))
    mock_db.execute.return_value = mock_scalars
    
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    
    response = client.get("/consultant/search?name=test")
    
    assert response.status_code == 200
    assert response.json()["count"] == 1

@pytest.mark.asyncio
@patch('src.routers.files_router._reset_errors_to_pending')
async def test_retry_errors(mock_reset):
    mock_reset.return_value = {"status": "success", "total_reset": 5}
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    
    response = client.post("/retry-errors")
    
    assert response.status_code == 200
    assert response.json()["total_reset"] == 5

@pytest.mark.asyncio
async def test_clear_all_errors():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(rowcount=5)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    
    response = client.delete("/errors")
    
    assert response.status_code == 200
    assert response.json()["cleared_count"] == 5

@pytest.mark.asyncio
@patch('src.routers.files_router._reset_errors_to_pending')
async def test_scheduled_retry_errors(mock_reset):
    mock_reset.return_value = {"status": "success", "total_reset": 2}
    # No JWT needed for public router
    response = client.post("/scheduled/retry-errors")
    assert response.status_code == 200
    assert response.json()["total_reset"] == 2

@pytest.mark.asyncio
@patch('src.routers.files_router.get_drive_service')
async def test_trigger_sync(mock_get_drive_service):
    mock_drive = MagicMock()
    mock_get_drive_service.return_value = mock_drive
    
    response = client.post("/sync")
    assert response.status_code == 200
    assert response.json()["status"] == "started"

@pytest.mark.asyncio
@patch('src.routers.files_router.get_google_access_token')
async def test_get_google_token(mock_get_token):
    mock_get_token.return_value = "token123"
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    
    response = client.get("/tokens/google")
    assert response.status_code == 200
    assert response.json()["access_token"] == "token123"

@pytest.mark.asyncio
@patch('src.routers.files_router.get_redis')
async def test_update_file(mock_get_redis):
    mock_db = AsyncMock()
    mock_file = MagicMock()
    mock_file.google_file_id = "test_id"
    mock_file.status = DriveSyncStatus.ERROR
    mock_file.revision_id = "r1"
    mock_file.modified_time = "2023-01-01T00:00:00Z"
    mock_file.file_name = "test.doc"
    mock_file.parent_folder_name = "parent"
    mock_file.error_message = "error"
    mock_file.file_type = "google_doc"
    mock_file.user_id = None
    mock_file.folder_id = 1
    mock_file.last_processed_at = None
    mock_file.imported_at = None
    mock_file.processing_duration_ms = None
    
    mock_scalars = MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_file))))
    mock_db.execute.return_value = mock_scalars
    
    mock_redis = MagicMock()
    mock_get_redis.return_value = mock_redis
    
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    
    response = client.patch("/files/test_id", json={"status": "PENDING", "user_id": 2})
    
    assert response.status_code == 200
    mock_redis.delete.assert_called_with("drive:file:known:test_id")
    assert mock_file.status == DriveSyncStatus.PENDING
    assert mock_file.user_id == 2
