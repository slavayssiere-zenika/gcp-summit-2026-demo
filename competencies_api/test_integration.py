import pytest
from unittest.mock import MagicMock, patch

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200

def test_create_competency(client):
    response = client.post("/", json={
        "name": "Python",
        "description": "Backend language"
    })
    assert response.status_code == 201
    assert response.json()["name"] == "Python"
    
def test_create_sub_competency(client):
    # Create parent
    parent_resp = client.post("/", json={"name": "Backend", "description": "Backend Dev"})
    assert parent_resp.status_code == 201
    parent_id = parent_resp.json()["id"]
    
    # Create sub-competency
    child_resp = client.post("/", json={
        "name": "FastAPI",
        "description": "Python Framework",
        "parent_id": parent_id
    })
    assert child_resp.status_code == 201
    assert child_resp.json()["parent_id"] == parent_id
    
def test_list_competencies_tree(client):
    # Verify the GET / route returns the nested tree structure
    parent_resp = client.post("/", json={"name": "DevOps", "description": "Operations"})
    parent_id = parent_resp.json()["id"]
    client.post("/", json={"name": "Docker", "description": "Container", "parent_id": parent_id})
    client.post("/", json={"name": "K8s", "description": "Orchestrator", "parent_id": parent_id})
    
    list_resp = client.get("/")
    assert list_resp.status_code == 200
    
    items = list_resp.json()["items"]
    # Find our DevOps root node
    devops_node = next((i for i in items if i["id"] == parent_id), None)
    assert devops_node is not None
    assert devops_node["parent_id"] is None
    
    # Verify sub_competencies were correctly eager-loaded by Pydantic
    assert "sub_competencies" in devops_node
    assert len(devops_node["sub_competencies"]) == 2
    sub_names = [s["name"] for s in devops_node["sub_competencies"]]
    assert "Docker" in sub_names
    assert "K8s" in sub_names

def test_assign_competency_propagates_jwt(client):
    # 1. Create a competency first
    create_resp = client.post("/", json={"name": "Docker", "description": "DevOps"})
    assert create_resp.status_code == 201
    comp_id = create_resp.json()["id"]

    # 2. Mock external get_user_from_api inter-service call 
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {"id": 1, "username": "testuser", "is_active": True, "email": "test@example.com"}
    mock_user.raise_for_status = MagicMock()

    # 3. Patch directly the AsyncClient.get
    with patch("httpx.AsyncClient.get", return_value=mock_user) as mock_get:
        # Hit the assign route WITH the Authorization header to test propagation
        response = client.post(
            f"/user/1/assign/{comp_id}",
            headers={"Authorization": "Bearer specific_jwt_to_propagate"}
        )
        assert response.status_code == 201
        
        # Verify the dependency was called and the header propagated perfectly
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs.get("headers", {}).get("Authorization") == "Bearer specific_jwt_to_propagate"

def test_assign_competency_fails_silently_on_unauthorized_fetch(client):
    # 1. Create competency
    create_resp = client.post("/", json={"name": "K8s", "description": "DevOps"})
    comp_id = create_resp.json()["id"]

    # 2. Mock external users_api refusing 
    mock_user = MagicMock()
    mock_user.status_code = 401
    mock_user.json.return_value = {"detail": "Unauthorized"}
    import httpx
    
    # We simulate raise_for_status failing with HTTPError
    def raise_err():
        raise httpx.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=mock_user)
    mock_user.raise_for_status.side_effect = raise_err

    # 3. Expect 503 Service Unavailable directly matching get_user_from_api's httpx.HTTPError exception handler
    with patch("httpx.AsyncClient.get", return_value=mock_user):
        response = client.post(f"/user/1/assign/{comp_id}")
        assert response.status_code == 503
        assert "Users API unavailable" in response.json()["detail"]

def test_get_competency(client):
    create_resp = client.post("/", json={"name": "GetTest", "description": "To be fetched"})
    comp_id = create_resp.json()["id"]
    
    resp = client.get(f"/{comp_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "GetTest"
    
    # Not found
    resp404 = client.get("/9999")
    assert resp404.status_code == 404

def test_update_competency(client):
    create_resp = client.post("/", json={"name": "UpdTest", "description": "Desc"})
    comp_id = create_resp.json()["id"]
    
    put_resp = client.put(f"/{comp_id}", json={"description": "Updated Desc"})
    assert put_resp.status_code == 200
    assert put_resp.json()["description"] == "Updated Desc"
    
    # 404
    put_404 = client.put("/9999", json={"description": "Updated Desc"})
    assert put_404.status_code == 404
    
    # Circular ref checking
    put_circ = client.put(f"/{comp_id}", json={"parent_id": comp_id})
    assert put_circ.status_code == 400

def test_delete_competency(client):
    create_resp = client.post("/", json={"name": "DelTest", "description": "Del"})
    comp_id = create_resp.json()["id"]
    
    del_resp = client.delete(f"/{comp_id}")
    assert del_resp.status_code == 204
    
    del_404 = client.delete("/9999")
    assert del_404.status_code == 404

def test_create_competency_parent_not_found(client):
    response = client.post("/", json={"name": "Child", "parent_id": 9999})
    assert response.status_code == 400

def test_assign_and_list_user_competencies(client):
    # 1. Create competency first
    create_resp = client.post("/", json={"name": "UserComp", "description": "DevOps"})
    comp_id = create_resp.json()["id"]

    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {"id": 1, "username": "testuser", "is_active": True, "email": "test@e.com"}
    mock_user.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_user):
        # First assignment
        assign_resp = client.post(f"/user/1/assign/{comp_id}")
        assert assign_resp.status_code == 201
        
        # Second assignment is idempotent (ON CONFLICT DO NOTHING) — same 201, no error
        assign_resp2 = client.post(f"/user/1/assign/{comp_id}")
        assert assign_resp2.status_code == 201
        # The status now always reflects the assignment action (idempotent upsert)
        assert "assigned" in assign_resp2.json()["status"]

    # List user competencies
    list_resp = client.get("/user/1")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1
    names = [c["name"] for c in list_resp.json()]
    assert "UserComp" in names

    # Remove competency
    rem_resp = client.delete(f"/user/1/remove/{comp_id}")
    assert rem_resp.status_code == 204

def test_get_user_from_api_not_found(client):
    # 1. Create competency
    create_resp = client.post("/", json={"name": "NotFoundUser", "description": "DevOps"})
    comp_id = create_resp.json()["id"]

    mock_user = MagicMock()
    mock_user.status_code = 404
    mock_user.json.return_value = {"detail": "Not found"}

    with patch("httpx.AsyncClient.get", return_value=mock_user):
        response = client.post(f"/user/999/assign/{comp_id}")
        assert response.status_code == 404

def test_bulk_import_tree_unauthorized(client):
    from main import app
    from src.auth import verify_jwt
    with patch.dict(app.dependency_overrides, {verify_jwt: lambda: {"sub": "1", "allowed_category_ids": [1]}}):
        response = client.post("/bulk_tree", json={"tree": {"Root": {}}})
        assert response.status_code == 403

def test_bulk_import_tree_authorized(client):
    from main import app
    from src.auth import verify_jwt
    with patch.dict(app.dependency_overrides, {verify_jwt: lambda: {"sub": "1", "role": "admin", "allowed_category_ids": []}}):
        payload = {
            "tree": {
                "Language": {
                    "sub": {
                        "Python": {
                            "sub": ["FastAPI", ["Django", "Web Framework"]]
                        }
                    }
                }
            }
        }
        response = client.post("/bulk_tree", json=payload)
        assert response.status_code == 200

def test_bulk_import_tree_list_format(client):
    from main import app
    from src.auth import verify_jwt
    with patch.dict(app.dependency_overrides, {verify_jwt: lambda: {"sub": "1", "role": "admin", "allowed_category_ids": []}}):
        payload = {
            "tree": [
                {
                    "Language": {
                        "sub": {
                            "Go": {
                                "sub": ["Gin"]
                            }
                        }
                    }
                },
                {
                    "Database": {
                        "sub": ["PostgreSQL"]
                    }
                }
            ]
        }
        response = client.post("/bulk_tree", json=payload)
        assert response.status_code == 200
        
        # Optional: verify that it was stored correctly
        list_resp = client.get("/")
        assert list_resp.status_code == 200
        names = [i["name"] for i in list_resp.json()["items"]]
        assert "Language" in names or "Database" in names


def test_get_competency_stats(client):
    # 1. Create competencies
    comp1 = client.post("/", json={"name": "RareSkill", "description": "Rare"}).json()["id"]
    comp2 = client.post("/", json={"name": "CommonSkill", "description": "Common"}).json()["id"]
    
    # 2. Mock user fetch (Assignment requires validating user in users_api)
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {"id": 1, "username": "u1", "is_active": True, "email": "u1@e.com"}
    mock_user.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", return_value=mock_user):
        # Assign comp2 to user 1, comp1 to user 1
        client.post(f"/user/1/assign/{comp2}")
        client.post(f"/user/1/assign/{comp1}")
        
    mock_user2 = MagicMock()
    mock_user2.status_code = 200
    mock_user2.json.return_value = {"id": 2, "username": "u2", "is_active": True, "email": "u2@e.com"}
    mock_user2.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", return_value=mock_user2):
        # Assign comp2 to user 2 (so comp2 has 2 users, comp1 has 1)
        client.post(f"/user/2/assign/{comp2}")

    # 3. Test stats - Most common (sort_order=desc)
    resp = client.post("/stats/counts", json={"sort_order": "desc", "limit": 10})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["name"] == "CommonSkill"
    assert items[0]["count"] == 2
    assert items[1]["name"] == "RareSkill"
    assert items[1]["count"] == 1
    
    # 4. Test stats - Rarest (sort_order=asc)
    resp_rare = client.post("/stats/counts", json={"sort_order": "asc", "limit": 10})
    assert resp_rare.status_code == 200
    items_rare = resp_rare.json()["items"]
    assert items_rare[0]["name"] == "RareSkill"
    assert items_rare[0]["count"] == 1
    
    # 5. Test filter by user_id
    resp_filter = client.post("/stats/counts", json={"user_ids": [2]})
    assert resp_filter.status_code == 200
    items_filter = resp_filter.json()["items"]
    assert len(items_filter) == 1
    assert items_filter[0]["name"] == "CommonSkill"
    assert items_filter[0]["count"] == 1



# ── Tests P2 : Intégrité des données ────────────────────────────────────────────

def test_delete_parent_competency_with_children(client):
    """
    Supprimer une compétence parent avec des enfants doit :
    - soit retourner 409 Conflict (protection cascade)
    - soit cascader la suppression des enfants (204 + enfants absents)
    """
    parent_resp = client.post("/", json={"name": "ParentToDelete", "description": "Parent"})
    assert parent_resp.status_code == 201
    parent_id = parent_resp.json()["id"]

    child_resp = client.post("/", json={"name": "ChildOfParent", "description": "Child", "parent_id": parent_id})
    assert child_resp.status_code == 201

    del_resp = client.delete(f"/{parent_id}")
    assert del_resp.status_code in [204, 409], \
        f"Suppression d\'un parent avec enfant doit retourner 204 (cascade) ou 409 (protection), got {del_resp.status_code}"

    if del_resp.status_code == 204:
        list_resp = client.get("/")
        all_names = [i["name"] for i in list_resp.json()["items"]]
        assert "ChildOfParent" not in all_names, \
            "Si suppression cascade, l\'enfant doit également être supprimé"


def test_competency_name_uniqueness(client):
    """
    Deux compétences avec le même nom déclenche un Upsert Idempotent.
    Attendu : 201 Created sur le doublon avec l'objet pré-existant retourné silencieusement.
    """
    client.post("/", json={"name": "UniqueCompetency", "description": "First"})
    resp2 = client.post("/", json={"name": "UniqueCompetency", "description": "Second"})
    assert resp2.status_code == 201
    assert resp2.json()["name"] == "UniqueCompetency"


def test_version_accessible(client):
    """GET /version doit retourner un champ version valide."""
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_competency_update_does_not_allow_self_parent(client):
    """
    Assigner une compétence comme parent d\'elle-même (référence circulaire)
    doit retourner 400 Bad Request.
    """
    resp = client.post("/", json={"name": "SelfRefComp", "description": "Circular"})
    comp_id = resp.json()["id"]
    put_resp = client.put(f"/{comp_id}", json={"parent_id": comp_id})
    assert put_resp.status_code == 400
    assert "circular" in put_resp.json()["detail"].lower() or "parent" in put_resp.json()["detail"].lower()
