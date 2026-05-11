import pytest
from httpx import AsyncClient
import uuid
import json
from conftest import app, override_verify_jwt
from src.auth import verify_jwt

@pytest.fixture
def unique_id():
    return str(uuid.uuid4())[:8]

@pytest.fixture(autouse=True)
def restore_overrides():
    # Setup
    app.dependency_overrides[verify_jwt] = override_verify_jwt
    yield
    # Teardown
    app.dependency_overrides[verify_jwt] = override_verify_jwt

def test_login_invalid_password(client, unique_id):
    client.post("/", json={"username": f"user_{unique_id}", "email": f"user_{unique_id}@example.com", "password": "password123"})
    response = client.post("/login", json={"email": f"user_{unique_id}@example.com", "password": "wrongpassword"})
    assert response.status_code == 401

def test_login_inactive_user(client, unique_id):
    create_resp = client.post("/", json={"username": f"inactive_{unique_id}", "email": f"inactive_{unique_id}@example.com", "password": "password123"})
    assert create_resp.status_code == 201

    # Suspend user
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "admin", "role": "admin"}
    client.post(f"/suspend/inactive_{unique_id}")
    app.dependency_overrides[verify_jwt] = override_verify_jwt

    response = client.post("/login", json={"email": f"inactive_{unique_id}@example.com", "password": "password123"})
    assert response.status_code == 400

def test_refresh_token(client, unique_id):
    client.post("/", json={"username": f"refresh_{unique_id}", "email": f"refresh_{unique_id}@example.com", "password": "password123"})
    login_resp = client.post("/login", json={"email": f"refresh_{unique_id}@example.com", "password": "password123"})
    
    refresh_token = login_resp.cookies.get("refresh_token")
    client.cookies.set("refresh_token", refresh_token)
    response = client.post("/refresh")
    assert response.status_code == 200

def test_refresh_token_missing(client):
    client.cookies.clear()
    response = client.post("/refresh")
    assert response.status_code == 401

def test_logout(client):
    response = client.post("/logout")
    assert response.status_code == 200

def test_google_config_and_login(client):
    resp = client.get("/google/config")
    assert resp.status_code in [200, 500]
    resp = client.get("/google/login", follow_redirects=False)
    assert resp.status_code in [302, 307]

def test_internal_service_token_admin(client, unique_id):
    create_resp = client.post("/", json={"username": f"admin_{unique_id}", "email": f"admin_{unique_id}@example.com", "password": "password123", "role": "admin"})
    assert create_resp.status_code == 201

    app.dependency_overrides[verify_jwt] = lambda: {"sub": f"admin_{unique_id}", "role": "admin"}
    response = client.post("/internal/service-token")
    assert response.status_code == 200
    app.dependency_overrides[verify_jwt] = override_verify_jwt

def test_suspend_user_admin(client, unique_id):
    username = f"suspend_{unique_id}"
    email = f"suspend_{unique_id}@example.com"
    create_resp = client.post("/", json={"username": username, "email": email, "password": "password123"})
    assert create_resp.status_code == 201
    
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "admin_system", "role": "admin"}
    resp = client.post(f"/suspend/{username}")
    assert resp.status_code == 200
    app.dependency_overrides[verify_jwt] = override_verify_jwt

def test_get_duplicates_admin(client, unique_id):
    r1 = client.post("/", json={"username": f"dup1_{unique_id}", "email": f"dup1_{unique_id}@e.com", "password": "password123", "first_name": "Jean", "last_name": "Dupont"})
    r2 = client.post("/", json={"username": f"dup2_{unique_id}", "email": f"dup2_{unique_id}@e.com", "password": "password123", "first_name": "Jean", "last_name": "Dupont"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    
    app.dependency_overrides[verify_jwt] = lambda: {"sub": "admin_system", "role": "admin"}
    resp = client.get("/duplicates")
    assert resp.status_code == 200
    app.dependency_overrides[verify_jwt] = override_verify_jwt

def test_merge_users_admin(client, unique_id):
    r1 = client.post("/", json={"username": f"m1_{unique_id}", "email": f"m1_{unique_id}@e.com", "password": "password123"})
    r2 = client.post("/", json={"username": f"m2_{unique_id}", "email": f"m2_{unique_id}@e.com", "password": "password123"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    
    id1 = r1.json()["id"]
    id2 = r2.json()["id"]

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "admin_system", "role": "admin"}
    resp = client.post("/merge", json={"source_id": id1, "target_id": id2})
    assert resp.status_code == 200
    app.dependency_overrides[verify_jwt] = override_verify_jwt
