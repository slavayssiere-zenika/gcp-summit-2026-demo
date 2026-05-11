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
def setup_teardown():
    app.dependency_overrides[verify_jwt] = override_verify_jwt
    yield
    app.dependency_overrides[verify_jwt] = override_verify_jwt

def test_crud_create_duplicate(client, unique_id):
    username = f"dup_{unique_id}"
    email = f"dup_{unique_id}@example.com"
    resp1 = client.post("/", json={"username": username, "email": email, "password": "password123"})
    assert resp1.status_code == 201

    # Same username, different email (upsert on email first) -> wait, if same username but different email, email is not found, username is found
    resp2 = client.post("/", json={"username": username, "email": f"other_{unique_id}@example.com", "password": "password123"})
    assert resp2.status_code == 201
    assert resp2.json()["id"] == resp1.json()["id"]

    # Try duplicate email but different username
    resp3 = client.post("/", json={"username": f"other2_{unique_id}", "email": email, "password": "password123"})
    assert resp3.status_code == 201
    assert resp3.json()["id"] == resp1.json()["id"]

def test_crud_bulk(client, unique_id):
    r1 = client.post("/", json={"username": f"bulk1_{unique_id}", "password": "password123"})
    id1 = r1.json()["id"]
    r2 = client.post("/", json={"username": f"bulk2_{unique_id}", "password": "password123"})
    id2 = r2.json()["id"]

    resp = client.post("/bulk", json={"user_ids": [id1, id2, 999999]})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

def test_crud_update_user(client, unique_id):
    r1 = client.post("/", json={"username": f"upd_{unique_id}", "password": "password123"})
    user_id = r1.json()["id"]

    # Admin update
    resp = client.put(f"/{user_id}", json={"full_name": "New Name", "is_active": False, "allowed_category_ids": [1, 2]})
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "New Name"
    assert resp.json()["allowed_category_ids"] == [1, 2]

def test_crud_delete_user(client, unique_id):
    r1 = client.post("/", json={"username": f"del_{unique_id}", "password": "password123"})
    user_id = r1.json()["id"]

    # Admin delete
    resp = client.delete(f"/{user_id}")
    assert resp.status_code in [200, 204]

    # Verify deleted
    resp2 = client.get(f"/{user_id}")
    assert resp2.status_code == 404

def test_list_and_search_anonymous(client, unique_id):
    client.post("/", json={"username": f"anon_{unique_id}", "password": "password123", "is_anonymous": True})
    
    # List anonymous
    r_list = client.get("/?is_anonymous=true")
    assert r_list.status_code == 200
    assert r_list.json()["total"] >= 1

    # Search anonymous
    r_search = client.get(f"/search?query=anon_{unique_id}&is_anonymous=true")
    assert r_search.status_code == 200
    assert r_search.json()["total"] >= 1
