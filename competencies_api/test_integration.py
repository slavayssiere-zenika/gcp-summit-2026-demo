import pytest
from unittest.mock import MagicMock, patch

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200

def test_create_competency(client):
    response = client.post("/competencies/", json={
        "name": "Python",
        "description": "Backend language"
    })
    assert response.status_code == 201
    assert response.json()["name"] == "Python"
    
def test_create_sub_competency(client):
    # Create parent
    parent_resp = client.post("/competencies/", json={"name": "Backend", "description": "Backend Dev"})
    assert parent_resp.status_code == 201
    parent_id = parent_resp.json()["id"]
    
    # Create sub-competency
    child_resp = client.post("/competencies/", json={
        "name": "FastAPI",
        "description": "Python Framework",
        "parent_id": parent_id
    })
    assert child_resp.status_code == 201
    assert child_resp.json()["parent_id"] == parent_id
    
def test_list_competencies_tree(client):
    # Verify the GET / route returns the nested tree structure
    parent_resp = client.post("/competencies/", json={"name": "DevOps", "description": "Operations"})
    parent_id = parent_resp.json()["id"]
    client.post("/competencies/", json={"name": "Docker", "description": "Container", "parent_id": parent_id})
    client.post("/competencies/", json={"name": "K8s", "description": "Orchestrator", "parent_id": parent_id})
    
    list_resp = client.get("/competencies/")
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
    create_resp = client.post("/competencies/", json={"name": "Docker", "description": "DevOps"})
    assert create_resp.status_code == 201
    comp_id = create_resp.json()["id"]

    # 2. Mock external get_user_from_api inter-service call 
    mock_user = MagicMock()
    mock_user.status_code = 200
    mock_user.json.return_value = {"id": 1, "username": "testuser", "is_active": True}
    mock_user.raise_for_status = MagicMock()

    # 3. Patch directly the AsyncClient.get
    with patch("httpx.AsyncClient.get", return_value=mock_user) as mock_get:
        # Hit the assign route WITH the Authorization header to test propagation
        response = client.post(
            f"/competencies/user/1/assign/{comp_id}",
            headers={"Authorization": "Bearer specific_jwt_to_propagate"}
        )
        assert response.status_code == 201
        
        # Verify the dependency was called and the header propagated perfectly
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs.get("headers", {}).get("Authorization") == "Bearer specific_jwt_to_propagate"

def test_assign_competency_fails_silently_on_unauthorized_fetch(client):
    # 1. Create competency
    create_resp = client.post("/competencies/", json={"name": "K8s", "description": "DevOps"})
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
        response = client.post(f"/competencies/user/1/assign/{comp_id}")
        assert response.status_code == 503
        assert "Users API unavailable" in response.json()["detail"]
