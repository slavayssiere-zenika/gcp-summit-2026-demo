import os
import logging
import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

def get_drive_service():
    """
    Returns an authenticated googleapiclient for the Drive v3 API.
    Uses ADC (Application Default Credentials).
    """
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
    service = build("drive", "v3", credentials=credentials)
    return service

def get_google_access_token() -> str:
    """Gets the raw OAuth2 access token for the service account"""
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        print(f"Failed to get google access token: {e}")
        return ""

def get_m2m_jwt_token() -> str:
    """
    Retrieves the OIDC ID Token from Google Metadata Server (when running on Cloud Run)
    and exchanges it with the Users API to receive a Zenith JWT for inter-service communication.
    """
    is_local = os.getenv("USE_IAM_AUTH", "false").lower() == "false"
    
    if is_local:
        return os.getenv("MOCK_M2M_JWT", "mock_local_jwt")
        
    try:
        import google.auth.transport.requests
        from google.oauth2 import id_token as sa_id_token
        
        req = google.auth.transport.requests.Request()
        audience = USERS_API_URL
        
        try:
            google_id_token = sa_id_token.fetch_id_token(req, audience)
        except Exception as e:
            print(f"fetch_id_token failed: {e}. Trying fallback credentials refresh.")
            credentials, _ = google.auth.default()
            credentials.refresh(req)
            google_id_token = getattr(credentials, 'id_token', None)
            
        if not google_id_token:
            raise Exception("Impossible de générer un ID Token OIDC via ADC.")

        import httpx
        res = httpx.post(f"{USERS_API_URL.rstrip('/')}/service-account/login", json={"id_token": google_id_token}, timeout=5.0)
        res.raise_for_status()
        return res.json()["access_token"]
    except Exception as e:
        print(f"Failed to acquire M2M JWT: {e}")
        return ""


def get_google_oidc_id_token() -> str:
    """
    Génère un OIDC ID Token signé par Google (RS256, validité 1h) pour le SA courant.

    Ce token est embarqué dans les messages Pub/Sub à la place du JWT applicatif HS256
    à courte durée de vie, éliminant les JWTError 'Signature has expired' lors des
    relivraisons Pub/Sub avec backoff (30s → 600s).

    Le worker destinataire (cv_api /pubsub/import-cv) l'échange contre un JWT applicatif
    frais via POST users_api/service-account/login au moment du traitement réel.

    En dev local (USE_IAM_AUTH != 'true') : retourne "" → fallback sur MOCK_M2M_JWT.
    Sur Cloud Run (USE_IAM_AUTH=true) : appelle le Metadata Server pour un ID Token.
    """
    is_local = os.getenv("USE_IAM_AUTH", "false").lower() != "true"
    if is_local:
        logger.debug("[OIDC] Env local détecté (USE_IAM_AUTH != true) — ID Token non généré.")
        return ""

    audience = os.getenv("USERS_API_URL", "http://users_api:8000")
    try:
        import google.auth.transport.requests as google_requests
        from google.oauth2 import id_token as sa_id_token
        req = google_requests.Request()
        token = sa_id_token.fetch_id_token(req, audience)
        logger.info(f"[OIDC] ID Token généré pour audience={audience}")
        return token
    except Exception as e:
        logger.warning(f"[OIDC] Impossible de générer un ID Token (audience={audience}): {e}")
        return ""
