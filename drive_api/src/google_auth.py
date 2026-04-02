import os
import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from googleapiclient.discovery import build

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

def get_drive_service():
    """
    Returns an authenticated googleapiclient for the Drive v3 API.
    Uses ADC (Application Default Credentials).
    """
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
    service = build("drive", "v3", credentials=credentials)
    return service

def get_m2m_jwt_token() -> str:
    """
    Retrieves the OIDC ID Token from Google Metadata Server (when running on Cloud Run)
    and exchanges it with the Users API to receive a Zenith JWT for inter-service communication.
    """
    # 1. Fetch native Google OIDC token targeting the internal microservice.
    # In a local development environment (where ADC is user-based instead of Service Account),
    # this might fail. We provide a mock/bypass for local if needed.
    is_local = os.getenv("USE_IAM_AUTH", "false").lower() == "false"
    
    if is_local:
        # Generate a dummy test token or fetch one for local testing
        # To strictly do this right, we will just use a hardcoded dev token
        # But for M2M, let's just do an empty string or mock
        return os.getenv("MOCK_M2M_JWT", "mock_local_jwt")
        
    try:
        credentials, _ = google.auth.default()
        req = Request()
        credentials.refresh(req)
        google_id_token = getattr(credentials, 'id_token', None)
        
        if not google_id_token:
            # Fallback for Service Accounts (using google-auth directly)
            from google.oauth2 import service_account
            if isinstance(credentials, service_account.Credentials):
                 # ID tokens from raw SA keys require target audience
                 import google.auth.transport.requests
                 from google.oauth2 import id_token as sa_id_token
                 audience = USERS_API_URL
                 google_id_token = sa_id_token.fetch_id_token(Request(), audience)
        
        if not google_id_token:
            raise Exception("Impossible de générer un ID Token")

        import httpx
        res = httpx.post(f"{USERS_API_URL}/users/service-account/login", json={"id_token": google_id_token}, timeout=5.0)
        res.raise_for_status()
        return res.json()["access_token"]
    except Exception as e:
        print(f"Failed to acquire M2M JWT: {e}")
        return ""
