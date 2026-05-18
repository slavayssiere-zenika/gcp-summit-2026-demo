from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from shared.auth.jwt import verify_jwt
from shared.database import get_db
from src.items.schemas import ItemResponse
from datetime import datetime

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
def test_create_items_bulk_success(mock_enrich):
    mock_db = AsyncMock()
    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_cat1 = MagicMock()
    mock_cat1.user = None
    mock_cat1.id = 1
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
    mock_result_final.scalars.return_value.all.return_value = [mock_final_item]

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing, mock_result_final]
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_enrich.return_value = ItemResponse(
        id=100,
        name="Bulk1",
        description="desc",
        metadata_json={},
        user_id=1,
        created_at=datetime.utcnow(),
        categories=[]
    )

    resp = client.post("/bulk", json={
        "items": [
            {
                "name": "Bulk1",
                "description": "desc",
                "metadata_json": {},
                "user_id": 1,
                "category_ids": [1]
            }
        ]
    })

    assert resp.status_code == 201
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == 100


def test_create_items_bulk_empty():
    resp = client.post("/bulk", json={"items": []})
    assert resp.status_code == 201
    assert resp.json() == []


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_items_bulk_invalid_category(mock_enrich):
    mock_db = AsyncMock()
    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    # Missing categories compared to what was requested
    mock_result_cats.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_result_cats]
    app.dependency_overrides[get_db] = lambda: mock_db

    resp = client.post("/bulk", json={
        "items": [
            {
                "name": "Bulk1",
                "user_id": 1,
                "category_ids": [999]
            }
        ]
    })

    assert resp.status_code == 400
    assert "One or more category IDs are invalid" in resp.json()["detail"]


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_items_bulk_forbidden_category(mock_enrich):
    def override_verify_jwt_forbidden():
        return {"sub": "user", "role": "user", "allowed_category_ids": [1]}

    app.dependency_overrides[verify_jwt] = override_verify_jwt_forbidden

    mock_db = AsyncMock()
    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_cat1 = MagicMock()
    mock_cat1.user = None
    mock_cat1.id = 2
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    mock_db.execute.side_effect = [mock_result_cats]
    app.dependency_overrides[get_db] = lambda: mock_db

    resp = client.post("/bulk", json={
        "items": [
            {
                "name": "Bulk1",
                "user_id": 1,
                "category_ids": [2]
            }
        ]
    })

    assert resp.status_code == 403
    assert "User does not have rights for categories" in resp.json()["detail"]


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_items_bulk_integrity_error_fallback(mock_enrich):
    from sqlalchemy.exc import IntegrityError

    mock_db = AsyncMock()
    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_cat1 = MagicMock()
    mock_cat1.user = None
    mock_cat1.id = 1
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    mock_result_existing1 = MagicMock()
    mock_result_existing1.user = None
    mock_result_existing1.scalars.return_value.all.return_value = []

    mock_result_fallback_existing = MagicMock()
    mock_result_fallback_existing.user = None
    mock_existing = MagicMock()
    mock_existing.user = None
    mock_existing.id = 200
    mock_result_fallback_existing.scalars.return_value.first.return_value = None

    mock_result_final = MagicMock()
    mock_result_final.user = None
    mock_final_item = MagicMock()
    mock_final_item.user = None
    mock_final_item.id = 200
    mock_result_final.scalars.return_value.all.return_value = [mock_final_item]

    mock_db.execute.side_effect = [
        mock_result_cats,
        mock_result_existing1,
        mock_result_fallback_existing,
        mock_result_final
    ]

    # Simulate IntegrityError on first commit
    mock_db.commit.side_effect = [IntegrityError("", "", ""), None]

    app.dependency_overrides[get_db] = lambda: mock_db

    mock_enrich.return_value = ItemResponse(
        id=200,
        name="BulkFallback",
        description="desc",
        metadata_json={},
        user_id=1,
        created_at=datetime.utcnow(),
        categories=[]
    )

    resp = client.post("/bulk", json={
        "items": [
            {
                "name": "Bulk1",
                "description": "desc",
                "metadata_json": {},
                "user_id": 1,
                "category_ids": [1]
            }
        ]
    })

    assert resp.status_code == 201
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == 200
    assert mock_db.rollback.called


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_items_bulk_generic_exception(mock_enrich):
    mock_db = AsyncMock()
    mock_result_cats = MagicMock()
    mock_result_cats.user = None
    mock_cat1 = MagicMock()
    mock_cat1.user = None
    mock_cat1.id = 1
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    mock_result_existing = MagicMock()
    mock_result_existing.user = None
    mock_result_existing.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing]

    # Simulate generic Exception on first commit
    mock_db.commit.side_effect = Exception("DB crash")

    app.dependency_overrides[get_db] = lambda: mock_db

    resp = client.post("/bulk", json={
        "items": [
            {
                "name": "Bulk1",
                "user_id": 1,
                "category_ids": [1]
            }
        ]
    })

    assert resp.status_code == 500
    assert mock_db.rollback.called
