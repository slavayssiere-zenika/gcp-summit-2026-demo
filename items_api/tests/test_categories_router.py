from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from shared.auth.jwt import verify_jwt
from shared.database import get_db

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

def test_list_categories():
    mock_db = AsyncMock()
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 2
    
    mock_cats_result = MagicMock()
    mock_cat1 = MagicMock()
    mock_cat1.id = 1
    mock_cat1.name = "Cat1"
    mock_cat1.description = "Desc1"
    
    mock_cat2 = MagicMock()
    mock_cat2.id = 2
    mock_cat2.name = "Cat2"
    mock_cat2.description = "Desc2"
    
    mock_cats_result.scalars.return_value.all.return_value = [mock_cat1, mock_cat2]
    
    mock_db.execute.side_effect = [mock_count_result, mock_cats_result]
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.get("/categories?skip=0&limit=10")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
    assert len(resp.json()["items"]) == 2

def test_create_category_success():
    from datetime import datetime, timezone
    
    mock_db = AsyncMock()
    async def mock_refresh(obj):
        obj.id = 1
        obj.created_at = datetime.now(timezone.utc)
    mock_db.refresh = AsyncMock(side_effect=mock_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.post("/categories", json={"name": "NewCat", "description": "NewDesc"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "NewCat"
    assert resp.json()["id"] == 1

def test_create_category_duplicate():
    mock_db = AsyncMock()
    mock_db.commit.side_effect = Exception("Duplicate entry")
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.post("/categories", json={"name": "NewCat", "description": "NewDesc"})
    assert resp.status_code == 400
    assert "Category name already exists" in resp.json()["detail"]

@patch("src.items.routers.categories_router.get_cache")
@patch("src.items.routers.categories_router.set_cache")
def test_get_item_stats(mock_set_cache, mock_get_cache):
    mock_get_cache.return_value = None
    
    mock_db = AsyncMock()
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 10
    
    mock_group_result = MagicMock()
    mock_group_result.all.return_value = [(1, 5), (2, 5)]
    
    mock_db.execute.side_effect = [mock_count_result, mock_group_result]
    app.dependency_overrides[get_db] = lambda: mock_db
    
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert resp.json()["total"] == 10
    assert resp.json()["by_user"]["1"] == 5
    assert resp.json()["by_user"]["2"] == 5
    
    mock_set_cache.assert_called_once()
