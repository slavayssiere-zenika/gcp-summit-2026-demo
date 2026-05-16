from unittest.mock import patch
from fastapi.testclient import TestClient
import jwt as jose_jwt

from main import app

client = TestClient(app)


@patch("src.users.auth_router.id_token.verify_oauth2_token")
def test_service_account_login_success(mock_verify_oauth2_token):
    mock_verify_oauth2_token.return_value = {
        "email": "sa-cv-prd-123456@zenika-prd.iam.gserviceaccount.com",
        "iss": "https://accounts.google.com"
    }

    id_token_str = jose_jwt.encode({"aud": "http://api.internal.zenika/api/users/"}, "secret", algorithm="HS256")

    response = client.post("/service-account/login", json={"id_token": id_token_str})

    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "service_account"
    assert data["username"] == "sa-cv-prd-123456@zenika-prd.iam.gserviceaccount.com"

    args, kwargs = mock_verify_oauth2_token.call_args
    assert kwargs.get("audience") == "http://api.internal.zenika/api/users/"


@patch("src.users.auth_router.id_token.verify_oauth2_token")
def test_service_account_login_invalid_email(mock_verify_oauth2_token):
    id_token_str = jose_jwt.encode({"aud": "http://api.internal.zenika/api/users/"}, "secret", algorithm="HS256")

    # Missing email
    mock_verify_oauth2_token.return_value = {
        "iss": "https://accounts.google.com"
    }

    response = client.post("/service-account/login", json={"id_token": id_token_str})
    assert response.status_code == 403
    assert "email est requis" in response.json()["detail"]

    # Invalid email domain
    mock_verify_oauth2_token.return_value = {
        "email": "user@zenika.com",
        "iss": "https://accounts.google.com"
    }

    response = client.post("/service-account/login", json={"id_token": id_token_str})
    assert response.status_code == 403
    assert "Service Account autorisé" in response.json()["detail"]


@patch("src.users.auth_router.id_token.verify_oauth2_token")
def test_service_account_login_invalid_token(mock_verify_oauth2_token):
    mock_verify_oauth2_token.side_effect = ValueError("Token expired")

    id_token_str = jose_jwt.encode({"aud": "http://api.internal.zenika/api/users/"}, "secret", algorithm="HS256")

    response = client.post("/service-account/login", json={"id_token": id_token_str})
    assert response.status_code == 401
    assert "Token invalide" in response.json()["detail"]
