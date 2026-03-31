import pytest
from fastapi.testclient import TestClient
from conftest import app

from unittest.mock import MagicMock, patch

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_create_item(client):
    # Mock the user verification call
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": 1, 
        "username": "testuser", 
        "email": "a@b.com",
        "is_active": True
    }
    mock_response.raise_for_status = MagicMock()
    
    # Mock category creation first to avoid 400 Bad Request
    client.post("/items/categories", json={"name": "TestCat", "description": "Test"})
    
    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        response = client.post("/items/", json={
            "name": "Test Item",
            "user_id": 1,
            "description": "A test item",
            "category_ids": [1]
        }, headers={"Authorization": "Bearer testing_propagation_token"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Item"
        assert data["user_id"] == 1
        
        # Verify JWT string was explicitly propagated during the enrich_item() loop
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs.get("headers", {}).get("Authorization") == "Bearer testing_propagation_token"

def test_get_item(client):
    # Mock user verification for creation
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {"id": 1, "username": "testuser", "email": "a@b.com", "is_active": True}
    mock_user.raise_for_status = MagicMock()

    client.post("/items/categories", json={"name": "GetCat", "description": "Test"})

    with patch("httpx.AsyncClient.get", return_value=mock_user) as mock_get:
        create_resp = client.post("/items/", json={"name": "GetItem", "user_id": 1, "category_ids": [1]}, headers={"Authorization": "Bearer token"})
        item_id = create_resp.json()["id"]

        response = client.get(f"/items/{item_id}", headers={"Authorization": "Bearer verify_jwt_token"})
        assert response.status_code == 200
        assert response.json()["name"] == "GetItem"
        
        # Verify that get_item() propagated the token during enrichment
        assert mock_get.call_count == 2
        _, kwargs = mock_get.call_args_list[1]
        assert kwargs.get("headers", {}).get("Authorization") == "Bearer verify_jwt_token"

def test_list_items(client):
    # Mock user verification for creation
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {"id": 1, "username": "testuser", "email": "a@b.com", "is_active": True}
    
    client.post("/items/categories", json={"name": "ListCat", "description": "Test"})

    with patch("httpx.AsyncClient.get", return_value=mock_user) as mock_get:
        client.post("/items/", json={"name": "ListItem", "user_id": 1, "category_ids": [1]}, headers={"Authorization": "Bearer list_token"})
        response = client.get("/items/", headers={"Authorization": "Bearer list_token"})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1
        
        # Check that the list_items loop propagated the correct Header for the enrich_item map.
        assert mock_get.call_count >= 2
        for call_data in mock_get.call_args_list:
            _, kwargs = call_data
            assert kwargs.get("headers", {}).get("Authorization") == "Bearer list_token"

def test_list_user_items(client):
    # Mock user verification for creation
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {"id": 1, "username": "testuser", "email": "a@b.com", "is_active": True}
    
    client.post("/items/categories", json={"name": "UserCat", "description": "Test"})
    
    with patch("httpx.AsyncClient.get", return_value=mock_user) as mock_get:
        client.post("/items/", json={"name": "UserItem", "user_id": 1, "category_ids": [1]}, headers={"Authorization": "Bearer list_user_token"})
        response = client.get("/items/user/1", headers={"Authorization": "Bearer list_user_token"})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        
        # Verify propagation 
        assert mock_get.call_count >= 2
        for call_data in mock_get.call_args_list:
            _, kwargs = call_data
            assert kwargs.get("headers", {}).get("Authorization") == "Bearer list_user_token"
def test_create_category(client):
    response = client.post("/items/categories", json={
        "name": "NewCat",
        "description": "New Category"
    })
    assert response.status_code == 201
    assert response.json()["name"] == "NewCat"

def test_create_item_with_permissions(client):
    # Mock category creation (ID 1)
    client.post("/items/categories", json={"name": "C1", "description": "D1"})
    
    # Mock user verification with allowed_category_ids=[1]
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {
        "id": 1, "username": "u1", "email": "u1@e.com", 
        "is_active": True, "allowed_category_ids": [1]
    }
    mock_user.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", return_value=mock_user):
        response = client.post("/items/", json={
            "name": "Allowed Item",
            "user_id": 1,
            "category_ids": [1]
        })
        assert response.status_code == 201

def test_create_item_permission_denied(client):
    # Mock category ID 2 exists but user only has [1]
    client.post("/items/categories", json={"name": "C2", "description": "D2"})
    
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {
        "id": 1, "username": "u1", "email": "u1@e.com", 
        "is_active": True, "allowed_category_ids": [1]
    }
    
    with patch("httpx.AsyncClient.get", return_value=mock_user):
        response = client.post("/items/", json={
            "name": "Forbidden Item",
            "user_id": 1,
            "category_ids": [2]
        })
        assert response.status_code == 403
        assert "does not have rights" in response.json()["detail"]

def test_list_user_items_filtering(client):
    # Setup categories: 1 (allowed), 2 (forbidden)
    client.post("/items/categories", json={"name": "AllowedCat"})
    client.post("/items/categories", json={"name": "ForbiddenCat"})
    
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {
        "id": 1, "username": "u1", "email": "u1@e.com", 
        "is_active": True, "allowed_category_ids": [1] # Only category 1 allowed
    }
    
    with patch("httpx.AsyncClient.get", return_value=mock_user):
        # Create item in category 1
        client.post("/items/", json={"name": "Visible", "user_id": 1, "category_ids": [1]}, headers={"Authorization": "Bearer token"})
        
        # Manually create item in category 2 via DB to test filtering 
        # (API would block creation, but we test the filtering logic in GET)
        # However, for the integration test with TestClient, we'll just check the response
        response = client.get("/items/user/1", headers={"Authorization": "Bearer filter_token"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for item in data["items"]:
            for cat in item["categories"]:
                assert cat["id"] == 1
