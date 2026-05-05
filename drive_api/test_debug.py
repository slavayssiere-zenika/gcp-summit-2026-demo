import asyncio
import os
os.environ["SECRET_KEY"] = "test"
from fastapi.testclient import TestClient
from main import app
from database import get_db
from unittest.mock import MagicMock, AsyncMock, patch
from src.auth import verify_jwt

async def override_get_db():
    yield AsyncMock()

app.dependency_overrides[get_db] = override_get_db

@patch('src.routers.ingestion_router.IngestionKpiService')
def run(mock_service_class):
    mock_service = MagicMock()
    mock_service.get_folder_kpis = AsyncMock(return_value=[{"folder_id": 1}])
    mock_service_class.return_value = mock_service

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "123"}
    client = TestClient(app, raise_server_exceptions=True)
    response = client.get("/ingestion/folder-kpis")
    print(response.status_code)

run()
