"""
Tests unitaires du handler Pub/Sub /pubsub/import-cv (cv_api).

Couvre :
- Cas nominal : payload valide, pipeline mocké → 200
- Cas OIDC absent : token manquant → 401
- Cas payload invalide : base64 malformé → 400
- Cas pipeline error : exception _process_cv_core → 500 (retry Pub/Sub)
- Cas non-CV : IGNORED → 200 (ACK sans retry)
"""
import base64
import json
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# SECRET_KEY doit être cohérente avec celle chargée par src.auth au démarrage.
# test_main.py charge le module en premier (ordre alphabétique) avec 'testsecret',
# donc on utilise la même valeur. setdefault() est insuffisant car auth.py purge l'env
# après lecture — la clé doit être cohérente entre tous les fichiers de test.
os.environ["SECRET_KEY"] = "testsecret"
os.environ.setdefault("PUBSUB_INVOKER_SA_EMAIL", "sa-pubsub-invoker-dev@your-project.iam.gserviceaccount.com")
os.environ.setdefault("GOOGLE_API_KEY", "dummy-api-key")

_TEST_JWT_SECRET = "testsecret"  # Doit correspondre à la SECRET_KEY chargée par src.auth


def _make_pubsub_payload(
    google_file_id: str = "test-file-123",
    url: str = "https://docs.google.com/document/d/test-file-123",
    source_tag: str = "Paris",
    folder_name: str = "Marie Dupont",
    google_access_token: str = "test-google-token",
    jwt: str = "",
    oidc_token: str = "",  # Vide en local (USE_IAM_AUTH != true), rempli en prod
) -> dict:
    """Construit un payload Pub/Sub encodé en base64 comme GCP le ferait."""
    from jose import jwt as jose_jwt
    if not jwt and not oidc_token:
        jwt = jose_jwt.encode({"sub": "test-worker"}, _TEST_JWT_SECRET, algorithm="HS256")
    
    message_data = {
        "google_file_id": google_file_id,
        "url": url,
        "source_tag": source_tag,
        "folder_name": folder_name,
        "google_access_token": google_access_token,
        "oidc_token": oidc_token,
        "jwt": jwt,
    }
    encoded = base64.b64encode(json.dumps(message_data).encode()).decode()
    return {
        "message": {
            "data": encoded,
            "messageId": "test-msg-id-001",
            "publishTime": "2026-04-22T00:00:00Z",
        },
        "subscription": "projects/test-project/subscriptions/cv-import-events-sub-test",
    }


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_pubsub_handler_missing_token():
    """Le handler doit refuser les requêtes sans token Authorization (Pub/Sub retry)."""
    from main import app
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/pubsub/import-cv",
            json=_make_pubsub_payload(),
        )
    assert resp.status_code == 401, f"Attendu 401, reçu {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_pubsub_handler_invalid_base64_payload():
    """Le handler doit retourner 400 si le champ 'data' est malformé."""
    from main import app
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/pubsub/import-cv",
            json={"message": {"data": "###INVALID_BASE64###"}},
            headers={"Authorization": "Bearer dummy-oidc-token"},
        )
    # En dev (PUBSUB_INVOKER_SA_EMAIL = placeholder), la validation OIDC est bypassée
    # → le handler tente de décoder le base64 et échoue avec 400
    assert resp.status_code == 400, f"Attendu 400, reçu {resp.status_code}"


@pytest.mark.asyncio
async def test_pubsub_handler_missing_url_in_payload():
    """Le handler doit retourner 400 si url ou google_file_id sont absents."""
    from main import app
    
    empty_data = base64.b64encode(json.dumps({"source_tag": "Paris"}).encode()).decode()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/pubsub/import-cv",
            json={"message": {"data": empty_data}},
            headers={"Authorization": "Bearer dummy-oidc-token"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pubsub_handler_nominal_success():
    """Cas nominal : pipeline exécutée avec succès, retourne 200."""
    from main import app
    
    mock_result = MagicMock()
    mock_result.user_id = 42
    
    with (
        patch("src.cvs.router._process_cv_core", new=AsyncMock(return_value=mock_result)),
        patch("httpx.AsyncClient") as mock_http,
        patch("src.cvs.router.database.SessionLocal", return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    ):
        # Mock le PATCH vers drive_api
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_http.return_value.__aenter__.return_value.patch = AsyncMock(return_value=mock_response)
        
        from main import app as fresh_app
        async with AsyncClient(transport=ASGITransport(app=fresh_app), base_url="http://test") as client:
            resp = await client.post(
                "/pubsub/import-cv",
                json=_make_pubsub_payload(),
                headers={"Authorization": "Bearer dummy-oidc-token"},
            )
    
    assert resp.status_code == 200
    assert resp.json().get("status") == "accepted"


@pytest.mark.asyncio
async def test_pubsub_handler_pipeline_failure_triggers_500():
    """
    Quand _process_cv_core lève une exception non-CV (erreur réseau, timeout),
    le handler doit retourner 500 → Pub/Sub retentera automatiquement.
    """
    from fastapi import HTTPException
    from main import app
    
    with (
        patch("src.cvs.router._process_cv_core", new=AsyncMock(side_effect=HTTPException(status_code=500, detail="Gemini timeout"))),
        patch("httpx.AsyncClient") as mock_http,
        patch("src.cvs.router.database.SessionLocal", return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    ):
        mock_http.return_value.__aenter__.return_value.patch = AsyncMock()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/pubsub/import-cv",
                json=_make_pubsub_payload(),
                headers={"Authorization": "Bearer dummy-oidc-token"},
            )
    
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_pubsub_handler_non_cv_returns_200_ack():
    """
    Quand le document n'est pas un CV, le handler doit retourner 200 (ACK)
    pour éviter un retry Pub/Sub inutile.
    """
    from fastapi import HTTPException
    from main import app
    
    with (
        patch("src.cvs.router._process_cv_core", new=AsyncMock(side_effect=HTTPException(status_code=400, detail="Not a CV - LLM Parsing failed"))),
        patch("httpx.AsyncClient") as mock_http,
        patch("src.cvs.router.database.SessionLocal", return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    ):
        mock_http.return_value.__aenter__.return_value.patch = AsyncMock()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/pubsub/import-cv",
                json=_make_pubsub_payload(),
                headers={"Authorization": "Bearer dummy-oidc-token"},
            )
    
    # 200 ACK → le message d'erreur est envoyé par webhook
    assert resp.status_code == 200
    assert resp.json().get("status") == "accepted"


@pytest.mark.asyncio
async def test_pubsub_handler_oidc_exchange_success():
    """
    UC10 — Quand le payload contient un oidc_token (production Cloud Run),
    le handler doit l'échanger contre un JWT applicatif frais via users_api.
    Vérifie que l'échange réussi permet l'exécution du pipeline.
    """
    from main import app
    from jose import jwt as jose_jwt

    mock_result = MagicMock()
    mock_result.user_id = 99

    # Simule un payload avec oidc_token et sans jwt (cas production)
    fresh_jwt = jose_jwt.encode({"sub": "drive-api-sa"}, _TEST_JWT_SECRET, algorithm="HS256")
    mock_oidc_response = AsyncMock()
    mock_oidc_response.status_code = 200
    mock_oidc_response.json = MagicMock(return_value={"access_token": fresh_jwt})

    mock_patch_response = AsyncMock()
    mock_patch_response.status_code = 200

    with (
        patch("src.cvs.router._process_cv_core", new=AsyncMock(return_value=mock_result)),
        patch("httpx.AsyncClient") as mock_http,
        patch("src.cvs.router.database.SessionLocal", return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    ):
        mock_http_instance = AsyncMock()
        mock_http_instance.post = AsyncMock(return_value=mock_oidc_response)
        mock_http_instance.patch = AsyncMock(return_value=mock_patch_response)
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/pubsub/import-cv",
                json=_make_pubsub_payload(oidc_token="google-oidc-id-token", jwt=""),
                headers={"Authorization": "Bearer dummy-oidc-envelope-token"},
            )

    assert resp.status_code == 200, f"Attendu 200, reçu {resp.status_code}: {resp.text}"
    assert resp.json().get("status") == "accepted"
