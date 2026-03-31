import pytest
from fastapi.testclient import TestClient
from conftest import app

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_metrics(client):
    response = client.get("/metrics")
    assert response.status_code == 200

def test_create_user(client):
    response = client.post("/users/", json={
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert data["id"] is not None

def test_get_user(client):
    # Create first
    create_resp = client.post("/users/", json={"username": "getuser", "email": "get@example.com"})
    user_id = create_resp.json()["id"]
    
    response = client.get(f"/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["username"] == "getuser"

def test_get_user_not_found(client):
    response = client.get("/users/999")
    assert response.status_code == 404

def test_list_users(client):
    client.post("/users/", json={"username": "listuser", "email": "list@example.com"})
    response = client.get("/users/")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1

def test_update_user(client):
    create_resp = client.post("/users/", json={"username": "updateuser", "email": "up@e.com"})
    user_id = create_resp.json()["id"]
    
    response = client.put(f"/users/{user_id}", json={"full_name": "Updated Name"})
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"

def test_delete_user(client):
    create_resp = client.post("/users/", json={"username": "deluser", "email": "del@e.com"})
    user_id = create_resp.json()["id"]
    
    response = client.delete(f"/users/{user_id}")
    assert response.status_code == 24 or response.status_code == 204
    
def test_create_user_with_permissions(client):
    response = client.post("/users/", json={
        "username": "permuser",
        "email": "perm@example.com",
        "allowed_category_ids": [1, 2, 3]
    })
    assert response.status_code == 201
    data = response.json()
    assert data["allowed_category_ids"] == [1, 2, 3]

def test_update_user_permissions(client):
    create_resp = client.post("/users/", json={"username": "up_perm", "email": "perm_up@e.com"})
    user_id = create_resp.json()["id"]
    
    response = client.put(f"/users/{user_id}", json={"allowed_category_ids": [5, 10]})
    assert response.status_code == 200
    assert response.json()["allowed_category_ids"] == [5, 10]
