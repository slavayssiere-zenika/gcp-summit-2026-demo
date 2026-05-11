def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_metrics(client):
    response = client.get("/metrics")
    assert response.status_code == 200


def test_create_user(client):
    import uuid
    uid = str(uuid.uuid4())[:8]
    response = client.post("/", json={
        "username": f"testuser_{uid}",
        "email": f"test_{uid}@example.com",
        "password": "securepassword",
        "full_name": "Test User"
    })
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["username"] == f"testuser_{uid}"
    assert data["id"] is not None


def test_get_user(client):
    # Create first
    import uuid
    uid = str(uuid.uuid4())[:8]
    create_resp = client.post("/", json={"username": f"getuser_{uid}", "email": f"get_{uid}@example.com", "password": "securepassword"})
    assert create_resp.status_code == 201, create_resp.text
    user_id = create_resp.json()["id"]

    response = client.get(f"/{user_id}")
    assert response.status_code == 200
    assert response.json()["username"] == f"getuser_{uid}"


def test_get_user_not_found(client):
    response = client.get("/999")
    assert response.status_code == 404


def test_list_users(client):
    import uuid
    uid = str(uuid.uuid4())[:8]
    client.post("/", json={"username": f"listuser_{uid}", "email": f"list_{uid}@example.com", "password": "securepassword"})
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1


def test_update_user(client):
    import uuid
    uid = str(uuid.uuid4())[:8]
    create_resp = client.post("/", json={"username": f"updateuser_{uid}", "email": f"up_{uid}@e.com", "password": "securepassword"})
    assert create_resp.status_code == 201, create_resp.text
    user_id = create_resp.json()["id"]

    response = client.put(f"/{user_id}", json={"full_name": "Updated Name"})
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"


def test_delete_user(client):
    import uuid
    uid = str(uuid.uuid4())[:8]
    create_resp = client.post("/", json={"username": f"deluser_{uid}", "email": f"del_{uid}@e.com", "password": "securepassword"})
    assert create_resp.status_code == 201, create_resp.text
    user_id = create_resp.json()["id"]

    response = client.delete(f"/{user_id}")
    assert response.status_code == 24 or response.status_code == 204


def test_create_user_with_permissions(client):
    import uuid
    uid = str(uuid.uuid4())[:8]
    response = client.post("/", json={
        "username": f"permuser_{uid}",
        "email": f"perm_{uid}@example.com",
        "password": "securepassword",
        "allowed_category_ids": [1, 2, 3]
    })
    assert response.status_code == 201
    data = response.json()
    assert data["allowed_category_ids"] == [1, 2, 3]


def test_update_user_permissions(client):
    import uuid
    uid = str(uuid.uuid4())[:8]
    create_resp = client.post("/", json={"username": f"up_perm_{uid}", "email": f"perm_up_{uid}@e.com", "password": "securepassword"})
    assert create_resp.status_code == 201, create_resp.text
    user_id = create_resp.json()["id"]

    response = client.put(f"/{user_id}", json={"allowed_category_ids": [5, 10]})
    assert response.status_code == 200
    assert response.json()["allowed_category_ids"] == [5, 10]


def test_login_logout(client):
    # Create user for auth
    import uuid
    uid = str(uuid.uuid4())[:8]
    client.post("/", json={"username": f"authuser_{uid}", "email": f"auth_{uid}@example.com", "password": "securepassword"})

    # Login success
    login_resp = client.post("/login", json={"email": f"auth_{uid}@example.com", "password": "securepassword"})
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()

    # Login fail
    bad_login = client.post("/login", json={"email": f"auth_{uid}@example.com", "password": "wrongpassword"})
    assert bad_login.status_code == 401

    # Logout
    logout_resp = client.post("/logout")
    assert logout_resp.status_code == 200


def test_get_me(client):
    # Valid via mock token in dependency override for integration tests? No, get_me extracts token from cookies manually!
    import uuid
    uid = str(uuid.uuid4())[:8]
    client.post("/", json={"username": f"me_user_{uid}", "email": f"me_{uid}@example.com", "password": "securepassword"})

    from conftest import app, override_verify_jwt
    from src.auth import verify_jwt
    app.dependency_overrides.pop(verify_jwt, None)

    try:
        # Login to get cookie
        login_resp = client.post("/login", json={"email": f"me_{uid}@example.com", "password": "securepassword"})
        # We need to explicitly extract the token becausehttpx test client does not perfectly persist across requests in some cases
        access_token = login_resp.cookies.get("access_token")

        # We must set the cookie on the client as requested by deprecation warning
        client.cookies.set("access_token", access_token)

        me_resp = client.get("/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == f"me_user_{uid}"

        # Missing cookie
        client.cookies.clear()
        no_cookie_resp = client.get("/me")
        assert no_cookie_resp.status_code == 401
    finally:
        app.dependency_overrides[verify_jwt] = override_verify_jwt


def test_get_user_stats(client):
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert "total" in resp.json()


def test_search_users(client):
    resp = client.get("/search?query=auth")
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_update_delete_not_found(client):
    put_resp = client.put("/9999", json={"first_name": "x"})
    assert put_resp.status_code == 404

    del_resp = client.delete("/9999")
    assert del_resp.status_code == 404


def test_router_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
