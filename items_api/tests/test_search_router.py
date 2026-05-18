from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from shared.auth.jwt import verify_jwt
from shared.database import get_db

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


@patch("src.items.routers.search_router.get_user_from_api", new_callable=AsyncMock)
def test_search_items_success(mock_get_user):
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
    mock_item.categories = []
    mock_items_result.scalars.return_value.all.return_value = [mock_item]

    mock_db.execute.side_effect = [mock_count_result, mock_items_result]
    app.dependency_overrides[get_db] = lambda: mock_db

    from src.items.schemas import UserInfo
    mock_user = UserInfo(id=1, username="u", email="e@e", is_active=True)
    mock_get_user.return_value = mock_user

    resp = client.get("/search/query?query=Item1")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert len(resp.json()["items"]) == 1


@patch("src.items.routers.search_router.get_user_from_api", new_callable=AsyncMock)
def test_list_user_items_success(mock_get_user):
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
    mock_item.categories = []
    mock_items_result.scalars.return_value.all.return_value = [mock_item]

    mock_db.execute.side_effect = [mock_count_result, mock_items_result]
    app.dependency_overrides[get_db] = lambda: mock_db

    from src.items.schemas import UserInfo
    mock_user = UserInfo(id=1, username="u", email="e@e", is_active=True)
    mock_get_user.return_value = mock_user

    resp = client.get("/user/1")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert len(resp.json()["items"]) == 1
