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


# ---------------------------------------------------------------------------
# Nouveau flow : une seule SELECT catégories + une SELECT existant par item
# + 1 commit + gather(enrich) — pas de fetch final distinct.
# ---------------------------------------------------------------------------

@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_items_bulk_success(mock_enrich):
    mock_db = AsyncMock()

    # execute #1 : fetch catégories
    mock_result_cats = MagicMock()
    mock_cat1 = MagicMock()
    mock_cat1.id = 1
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    # execute #2 : check existant pour item "Bulk1"
    mock_result_existing = MagicMock()
    mock_result_existing.scalars.return_value.first.return_value = None  # pas en DB

    # execute #3 : selectinload reload après commit (nouveau comportement post-fix MissingGreenlet)
    mock_db_item_reloaded = MagicMock()
    mock_db_item_reloaded.id = 100
    mock_db_item_reloaded.categories = [mock_cat1]
    mock_db_item_reloaded.created_at = datetime.utcnow()
    mock_result_reloaded = MagicMock()
    mock_result_reloaded.scalars.return_value.first.return_value = mock_db_item_reloaded

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing, mock_result_reloaded]
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
    # Catégories absentes → mismatch count
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
    mock_cat2 = MagicMock()
    mock_cat2.id = 2
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat2]
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
    """
    Nouveau flow : IntegrityError sur commit d'un item → rollback → SELECT existant.
    Le code ne charge plus de "fresh_cats" globalement, mais réutilise cat_map.
    """
    from sqlalchemy.exc import IntegrityError

    mock_db = AsyncMock()

    # execute #1 : fetch catégories
    mock_result_cats = MagicMock()
    mock_cat1 = MagicMock()
    mock_cat1.id = 1
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    # execute #2 : check existant → None (pas encore en DB)
    mock_result_no_existing = MagicMock()
    mock_result_no_existing.scalars.return_value.first.return_value = None

    # execute #3 : SELECT existant après rollback IntegrityError → retrouve l'item
    mock_existing_item = MagicMock()
    mock_existing_item.id = 200
    mock_existing_item.categories = [mock_cat1]
    mock_result_existing_after_rollback = MagicMock()
    mock_result_existing_after_rollback.scalars.return_value.first.return_value = mock_existing_item

    mock_db.execute.side_effect = [
        mock_result_cats,                       # 1. category fetch
        mock_result_no_existing,                # 2. existing check (None)
        mock_result_existing_after_rollback,    # 3. recovery after IntegrityError
    ]

    # Premier commit → IntegrityError simulé
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
                "name": "BulkFallback",
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
    """
    Erreur non-IntegrityError : le commit échoue (DB crash).
    Le code logue l'erreur, continue sans l'item, et retourne une liste partielle.
    """
    mock_db = AsyncMock()

    mock_result_cats = MagicMock()
    mock_cat1 = MagicMock()
    mock_cat1.id = 1
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    mock_result_existing = MagicMock()
    mock_result_existing.scalars.return_value.first.return_value = None

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing]
    mock_db.commit.side_effect = Exception("DB crash")

    app.dependency_overrides[get_db] = lambda: mock_db

    # La réponse est 201 avec une liste vide (item skippé silencieusement)
    # NOTE : comportement intentionnel post-refactor SRE — l'item est loggé en erreur
    # mais ne bloque pas le reste du payload.
    resp = client.post("/bulk", json={
        "items": [
            {
                "name": "Bulk1",
                "user_id": 1,
                "category_ids": [1]
            }
        ]
    })

    # La liste est vide — l'item a échoué mais pas de 500 levée
    assert resp.status_code == 201
    assert mock_db.rollback.called


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_items_bulk_deduplication(mock_enrich):
    """
    Un payload avec deux items identiques (user_id, name) ne doit créer qu'un seul
    item en DB — le doublon est éliminé en amont.
    """
    mock_db = AsyncMock()

    mock_result_cats = MagicMock()
    mock_cat1 = MagicMock()
    mock_cat1.id = 1
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    # Un seul check existant (doublon éliminé avant la boucle)
    mock_result_existing = MagicMock()
    mock_result_existing.scalars.return_value.first.return_value = None

    # execute #3 : selectinload reload après commit
    mock_db_item_reloaded = MagicMock()
    mock_db_item_reloaded.id = 42
    mock_db_item_reloaded.categories = [mock_cat1]
    mock_db_item_reloaded.created_at = datetime.utcnow()
    mock_result_reloaded = MagicMock()
    mock_result_reloaded.scalars.return_value.first.return_value = mock_db_item_reloaded

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing, mock_result_reloaded]
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_enrich.return_value = ItemResponse(
        id=42,
        name="DupItem",
        description="",
        metadata_json={},
        user_id=1,
        created_at=datetime.utcnow(),
        categories=[]
    )

    resp = client.post("/bulk", json={
        "items": [
            {"name": "DupItem", "user_id": 1, "category_ids": [1]},
            {"name": "DupItem", "user_id": 1, "category_ids": [1]},  # doublon
        ]
    })

    assert resp.status_code == 201
    # Un seul item retourné malgré 2 dans le payload
    assert len(resp.json()) == 1
    # Un seul commit effectué (pas deux)
    assert mock_db.commit.call_count == 1


@patch("src.items.crud_router.enrich_item", new_callable=AsyncMock)
def test_create_items_bulk_idempotent_existing(mock_enrich):
    """
    Si tous les items existent déjà, aucun commit ne doit avoir lieu.
    """
    mock_db = AsyncMock()

    mock_result_cats = MagicMock()
    mock_cat1 = MagicMock()
    mock_cat1.id = 1
    mock_result_cats.scalars.return_value.all.return_value = [mock_cat1]

    # Item déjà existant
    mock_existing = MagicMock()
    mock_existing.id = 77
    mock_existing.categories = [mock_cat1]
    mock_result_existing = MagicMock()
    mock_result_existing.scalars.return_value.first.return_value = mock_existing

    mock_db.execute.side_effect = [mock_result_cats, mock_result_existing]
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_enrich.return_value = ItemResponse(
        id=77, name="ExistingItem", description="", metadata_json={},
        user_id=1, created_at=datetime.utcnow(), categories=[]
    )

    resp = client.post("/bulk", json={
        "items": [{"name": "ExistingItem", "user_id": 1, "category_ids": [1]}]
    })

    assert resp.status_code == 201
    assert resp.json()[0]["id"] == 77
    # Aucun commit — rien à insérer
    assert not mock_db.commit.called
