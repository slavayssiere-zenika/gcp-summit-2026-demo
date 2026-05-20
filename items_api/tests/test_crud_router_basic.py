from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from main import app
from shared.auth.jwt import verify_jwt
from shared.database import get_db
from src.items.schemas import ItemResponse

client = TestClient(app, raise_server_exceptions=False)

from conftest import override_get_db, override_verify_jwt as orig_verify_jwt  # noqa: E402


def local_override_verify_jwt():
    return {"sub": "admin", "role": "admin", "allowed_category_ids": [1, 2, 3]}


@pytest.fixture(autouse=True)
def setup_and_clear_overrides():
    app.dependency_overrides[verify_jwt] = local_override_verify_jwt
    yield
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_jwt] = orig_verify_jwt


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_item_success(mock_enrich):
    mock_db = AsyncMock()
    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_cat1 = MagicMock()
    mock_cat1.user = None
    mock_cat1.id = 1
    mock_cat1.name = "Cat1"
    mock_cat1.description = "Cat1 desc"
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    mock_result_existing = MagicMock()
    mock_result_existing.user = None
    mock_result_existing.scalars.return_value.first.return_value = None

    mock_result_final = MagicMock()
    mock_result_final.user = None
    mock_final_item = MagicMock()
    mock_final_item.user = None
    mock_final_item.id = 100
    mock_final_item.name = "Item1"
    mock_final_item.description = "desc"
    mock_final_item.metadata_json = {}
    mock_final_item.user_id = 1
    mock_final_item.categories = []
    mock_final_item.created_at = datetime.now(timezone.utc)
    mock_result_final.scalars.return_value.first.return_value = mock_final_item

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing, mock_result_final]

    async def mock_refresh(obj):
        obj.id = 100
        obj.created_at = datetime.now(timezone.utc)
    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    app.dependency_overrides[get_db] = lambda: mock_db

    mock_enrich.return_value = ItemResponse(
        id=100, name="Item1", description="desc", metadata_json={},
        user_id=1, created_at=datetime.now(timezone.utc), categories=[]
    )

    resp = client.post("/", json={
        "name": "Item1",
        "description": "desc",
        "metadata_json": {},
        "user_id": 1,
        "category_ids": [1]
    })

    assert resp.status_code == 201
    assert resp.json()["id"] == 100


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_item_invalid_category(mock_enrich):
    mock_db = AsyncMock()
    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_result_cats.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_result_cats]
    app.dependency_overrides[get_db] = lambda: mock_db

    resp = client.post("/", json={
        "name": "Item1",
        "description": "desc",
        "metadata_json": {},
        "user_id": 1,
        "category_ids": [999]
    })

    assert resp.status_code == 400
    assert "One or more category IDs are invalid" in resp.json()["detail"]


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_update_item_success(mock_enrich):
    mock_db = AsyncMock()
    mock_result_existing = MagicMock()
    mock_result_existing.user = None
    mock_item = MagicMock()
    mock_item.user = None
    mock_item.id = 100
    mock_item.name = "UpdatedItem"
    mock_item.description = "desc"
    mock_item.metadata_json = {}
    mock_item.user_id = 1
    mock_item.user = None
    mock_item.created_at = datetime.now(timezone.utc)

    mock_cat = MagicMock()
    mock_cat.user = None
    mock_cat.id = 1
    mock_cat.name = "Cat1"
    mock_cat.description = "desc"
    mock_item.categories = [mock_cat]
    mock_result_existing.scalars.return_value.first.return_value = mock_item

    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_cat = MagicMock()
    mock_cat.user = None
    mock_cat.id = 1
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat]

    mock_result_final = MagicMock()
    mock_result_final.user = None
    mock_result_final.scalars.return_value.first.return_value = mock_item

    mock_db.execute.side_effect = [mock_result_existing, mock_result_cats, mock_result_final]
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_enrich.return_value = ItemResponse(
        id=100, name="UpdatedItem", description="desc", metadata_json={},
        user_id=1, created_at=datetime.now(timezone.utc), categories=[]
    )

    resp = client.put("/100", json={"name": "UpdatedItem", "category_ids": [1]})
    assert resp.status_code == 200
    assert resp.json()["name"] == "UpdatedItem"


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_update_item_not_found(mock_enrich):
    mock_db = AsyncMock()
    mock_result_existing = MagicMock()
    mock_result_existing.user = None
    mock_result_existing.scalars.return_value.first.return_value = None

    mock_db.execute.side_effect = [mock_result_existing]
    app.dependency_overrides[get_db] = lambda: mock_db

    resp = client.put("/999", json={"name": "UpdatedItem", "category_ids": [1]})
    assert resp.status_code == 404


def test_delete_item_success():
    mock_db = AsyncMock()
    mock_result_existing = MagicMock()
    mock_result_existing.user = None
    mock_item = MagicMock()
    mock_item.user = None
    mock_item.id = 100
    mock_item.name = "DeletedItem"
    mock_item.description = "desc"
    mock_item.metadata_json = {}
    mock_item.user_id = 1
    mock_item.user = None
    mock_item.created_at = datetime.now(timezone.utc)
    mock_item.categories = []
    mock_result_existing.scalars.return_value.first.return_value = mock_item

    mock_db.execute.side_effect = [mock_result_existing, MagicMock()]
    app.dependency_overrides[get_db] = lambda: mock_db

    resp = client.delete("/100")
    assert resp.status_code == 204


def test_delete_item_not_found():
    mock_db = AsyncMock()
    mock_result_existing = MagicMock()
    mock_result_existing.user = None
    mock_result_existing.scalars.return_value.first.return_value = None

    mock_db.execute.side_effect = [mock_result_existing]
    app.dependency_overrides[get_db] = lambda: mock_db

    resp = client.delete("/999")
    assert resp.status_code == 404


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_get_item_success(mock_enrich):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.user = None
    mock_item = MagicMock()
    mock_item.user = None
    mock_item.id = 100
    mock_item.name = "Item1"
    mock_item.description = "desc"
    mock_item.metadata_json = {}
    mock_item.user_id = 1
    mock_item.user = None
    mock_item.categories = []
    mock_item.created_at = datetime.now(timezone.utc)
    mock_result.scalars.return_value.first.return_value = mock_item

    mock_db.execute.side_effect = [mock_result]
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_enrich.return_value = ItemResponse(
        id=100, name="Item1", description="desc", metadata_json={},
        user_id=1, created_at=datetime.now(timezone.utc), categories=[]
    )

    resp = client.get("/100")
    assert resp.status_code == 200
    assert resp.json()["id"] == 100


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_get_item_not_found(mock_enrich):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.user = None
    mock_result.scalars.return_value.first.return_value = None

    mock_db.execute.side_effect = [mock_result]
    app.dependency_overrides[get_db] = lambda: mock_db

    resp = client.get("/999")
    assert resp.status_code == 404


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_list_items_success(mock_enrich):
    mock_db = AsyncMock()
    mock_count_result = MagicMock()
    mock_count_result.user = None
    mock_count_result.scalar.return_value = 1

    mock_items_result = MagicMock()
    mock_items_result.user = None
    mock_item = MagicMock()
    mock_item.user = None
    mock_item.id = 100
    mock_item.name = "Item1"
    mock_item.description = "desc"
    mock_item.metadata_json = {}
    mock_item.user_id = 1
    mock_item.user = None
    mock_item.categories = []
    mock_item.created_at = datetime.now(timezone.utc)
    mock_items_result.scalars.return_value.all.return_value = [mock_item]

    mock_db.execute.side_effect = [mock_count_result, mock_items_result]
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_enrich.return_value = ItemResponse(
        id=100, name="Item1", description="desc", metadata_json={},
        user_id=1, created_at=datetime.now(timezone.utc), categories=[]
    )

    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert len(resp.json()["items"]) == 1
    assert resp.json()["items"][0]["id"] == 100


@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
def test_get_user_from_api_404(mock_get):
    mock_db = AsyncMock()

    async def mock_refresh(obj, *args, **kwargs):
        obj.id = 100
        obj.name = "Item1"
        obj.description = "desc"
        obj.metadata_json = {}
        obj.categories = []
        obj.created_at = datetime.now(timezone.utc)
    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_cat1 = MagicMock()
    mock_cat1.user = None
    mock_cat1.id = 1
    mock_cat1.name = "Cat1"
    mock_cat1.description = "Cat1 desc"
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    mock_result_existing = MagicMock()
    mock_result_existing.user = None
    mock_result_existing.scalars.return_value.all.return_value = []
    mock_result_existing.scalars.return_value.first.return_value = None

    mock_result_final = MagicMock()
    mock_result_final.user = None
    mock_final_item = MagicMock()
    mock_final_item.user = None
    mock_final_item.id = 100
    mock_final_item.name = "Item1"
    mock_final_item.description = "desc"
    mock_final_item.metadata_json = {}
    mock_final_item.user_id = 1
    mock_final_item.categories = [mock_cat1]
    mock_final_item.created_at = datetime.now(timezone.utc)
    mock_result_final.scalars.return_value.all.return_value = [mock_final_item]
    mock_result_final.scalars.return_value.first.return_value = mock_final_item

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing, mock_result_final]

    app.dependency_overrides[get_db] = lambda: mock_db

    mock_response = MagicMock()
    mock_response.user = None
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    resp = client.post("/", json={
        "name": "Item1",
        "description": "desc",
        "metadata_json": {},
        "user_id": 1,
        "category_ids": [1]
    })
    assert resp.status_code == 201
    assert resp.json()["user"] is None


@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
def test_get_user_from_api_httperror(mock_get):
    import httpx
    mock_db = AsyncMock()

    async def mock_refresh(obj, *args, **kwargs):
        obj.id = 100
        obj.name = "Item1"
        obj.description = "desc"
        obj.metadata_json = {}
        obj.categories = []
        obj.created_at = datetime.now(timezone.utc)
    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_cat1 = MagicMock()
    mock_cat1.user = None
    mock_cat1.id = 1
    mock_cat1.name = "Cat1"
    mock_cat1.description = "Cat1 desc"
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    mock_result_existing = MagicMock()
    mock_result_existing.user = None
    mock_result_existing.scalars.return_value.all.return_value = []
    mock_result_existing.scalars.return_value.first.return_value = None

    mock_result_final = MagicMock()
    mock_result_final.user = None
    mock_final_item = MagicMock()
    mock_final_item.user = None
    mock_final_item.id = 100
    mock_final_item.name = "Item1"
    mock_final_item.description = "desc"
    mock_final_item.metadata_json = {}
    mock_final_item.user_id = 1
    mock_final_item.categories = [mock_cat1]
    mock_final_item.created_at = datetime.now(timezone.utc)
    mock_result_final.scalars.return_value.all.return_value = [mock_final_item]
    mock_result_final.scalars.return_value.first.return_value = mock_final_item

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing, mock_result_final]

    app.dependency_overrides[get_db] = lambda: mock_db

    mock_get.side_effect = httpx.HTTPError("Network error")

    resp = client.post("/", json={
        "name": "Item1",
        "description": "desc",
        "metadata_json": {},
        "user_id": 1,
        "category_ids": [1]
    })
    assert resp.status_code == 201
    assert resp.json()["user"] is None
