import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from shared.database import get_db
from shared.auth.jwt import verify_jwt
from src.routers.ingestion_router import _require_admin

client = TestClient(app, raise_server_exceptions=False)

async def override_get_db():
    yield AsyncMock()

app.dependency_overrides[get_db] = override_get_db

def test_require_admin():
    with pytest.raises(HTTPException, match="Privilèges administrateur requis"):
        _require_admin({"role": "user"})
        
    assert _require_admin({"role": "admin"}) == {"role": "admin"}

@pytest.mark.asyncio
@patch('src.routers.ingestion_router.IngestionKpiService')
async def test_get_ingestion_stats(mock_service_class):
    mock_service = MagicMock()
    mock_service.get_ingestion_stats = AsyncMock(return_value={"total_files": 100})
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    response = client.get("/ingestion/stats")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json() == {"total_files": 100}

@pytest.mark.asyncio
@patch('src.routers.ingestion_router.IngestionKpiService')
async def test_get_folder_kpis(mock_service_class):
    mock_service = MagicMock()
    mock_service.get_folder_kpis = AsyncMock(return_value=[{"folder_id": 1}])
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    response = client.get("/ingestion/folder-kpis")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json() == [{"folder_id": 1}]

@pytest.mark.asyncio
@patch('src.routers.ingestion_router.IngestionKpiService')
async def test_get_ingestion_history(mock_service_class):
    mock_service = MagicMock()
    mock_service.get_ingestion_history = AsyncMock(return_value=[{"google_file_id": "1"}])
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    response = client.get("/ingestion/history?limit=10")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json() == [{"google_file_id": "1"}]

@pytest.mark.asyncio
@patch('src.routers.ingestion_router.IngestionKpiService')
async def test_ingestion_batch_retry(mock_service_class):
    mock_service = MagicMock()
    mock_service.batch_retry = AsyncMock(return_value={"total_reset": 5})
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    response = client.post("/ingestion/batch-retry")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json()["sync_triggered"] is True

@pytest.mark.asyncio
@patch('src.routers.ingestion_router.IngestionKpiService')
async def test_quality_gate_batch(mock_service_class):
    mock_service = MagicMock()
    mock_service.quality_gate_batch = AsyncMock(return_value={
        "total_queued": 2,
        "reason_breakdown": {"user_id_manquant": 2}
    })
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123", "role": "admin"}
    response = client.post("/ingestion/quality-gate-batch")
    del app.dependency_overrides[verify_jwt]
    
    assert response.status_code == 200
    assert response.json()["files_queued_for_retry"] == 2
