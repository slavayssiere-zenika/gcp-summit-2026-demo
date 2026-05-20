"""
test_hitl_endpoints.py — Tests des endpoints HITL (Human-in-the-Loop) Phase 3.

Valide sans Redis réel (mock fakeredis) :
  - POST /hitl/create → crée un pending en Redis
  - POST /hitl/respond (approved) → enregistre la décision, supprime le pending
  - POST /hitl/respond (rejected) → idem
  - POST /hitl/respond → 404 si hitl_id inconnu
  - POST /hitl/respond → 400 si decision invalide
  - GET  /hitl/pending → liste les pending

Architecture HITL :
    Agent (requires_human_approval=True)
        → POST /hitl/create  (hitl_id → Redis TTL 30 min)
        → A2AResponse.data = {hitl_request: {hitl_id, …}}
        → Frontend: HitlApproval.vue
        → POST /hitl/respond (decision: approved/rejected)
        → Redis hitl:{id}:response
"""
import json
import os
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

# ── Env avant import ────────────────────────────────────────────────────────────
os.environ.setdefault("SECRET_KEY", "testsecret_must_be_32_characters_long_for_sha256")
os.environ.setdefault("GEMINI_MODEL", "gemini-test")
os.environ.setdefault("REDIS_URL", "redis://localhost/12")
os.environ.setdefault("APP_VERSION", "test")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "false")

SECRET_KEY = "testsecret_must_be_32_characters_long_for_sha256"
ALGORITHM = "HS256"


def _make_jwt(sub: str = "manager@zenika.com", role: str = "manager") -> str:
    return jwt.encode(
        {"sub": sub, "role": role, "exp": int(time.time()) + 3600},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# ── Fake Redis ─────────────────────────────────────────────────────────────────
class FakeRedis:
    """Redis in-memory ultra-simplifié pour les tests HITL."""

    def __init__(self):
        self._store: dict[str, str] = {}
        self._ttls: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value
        self._ttls[key] = ttl

    def get(self, key: str):
        return self._store.get(key)

    def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0

    def keys(self, pattern: str) -> list[str]:
        """Support du pattern hitl:*:pending simplifié."""
        if "*" in pattern:
            prefix, suffix = pattern.split("*", 1)
            return [k for k in self._store if k.startswith(prefix) and k.endswith(suffix)]
        return [k for k in self._store if k == pattern]

    @classmethod
    def from_url(cls, url: str, **kwargs) -> "FakeRedis":
        return cls()


# ── Fixture ────────────────────────────────────────────────────────────────────
@pytest.fixture()
def fake_redis():
    return FakeRedis()


@pytest.fixture()
def client(fake_redis):
    with (
        patch("agent_commons.session.RedisSessionService.__init__", return_value=None),
        patch("agent_commons.session.RedisSessionService.create_session", new=AsyncMock(return_value=None)),
        patch("agent_commons.session.RedisSessionService.get_session", new=AsyncMock(return_value=None)),
        patch("agent_commons.mcp_proxy.get_cached_tools", new=AsyncMock(return_value=[])),
        patch("agent_commons.runner.run_agent_and_collect", new=AsyncMock(
            return_value=("ok", [], "", 5, 2, None, "text_only")
        )),
        patch("agent_commons.finops.log_tokens_to_bq"),
        # HITL Redis mock — patcher sur hitl_router (le module qui définit _get_hitl_redis)
        patch("hitl_router._get_hitl_redis", return_value=fake_redis),
    ):
        from main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ── Helpers ────────────────────────────────────────────────────────────────────
def _auth_headers(sub: str = "manager@zenika.com", role: str = "manager") -> dict:
    return {"Authorization": f"Bearer {_make_jwt(sub, role)}"}


def _user_headers(sub: str = "user@zenika.com") -> dict:
    """Headers sans rôle manager — pour tester les refus 403."""
    return {"Authorization": f"Bearer {_make_jwt(sub, role='consultant')}"}


# ── Tests POST /hitl/create ────────────────────────────────────────────────────
class TestHitlCreate:
    """Valide la création d'une demande HITL en Redis."""

    def test_create_returns_hitl_id(self, client):
        """POST /hitl/create doit retourner un hitl_id UUID et expires_at."""
        resp = client.post(
            "/hitl/create",
            json={
                "mission_title": "Mission BNP Paribas",
                "reason": "Score trop faible — validation managériale requise.",
                "candidates": [{"consultant_id": 1, "full_name": "Alice Martin", "confidence_score": 0.45}],
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "hitl_id" in data
        assert "expires_at" in data
        assert data["success"] is True
        # Vérifier que le hitl_id est un UUID valide
        uuid.UUID(data["hitl_id"])

    def test_create_stores_in_redis(self, client, fake_redis):
        """POST /hitl/create doit stocker le payload chiffré en Redis."""
        resp = client.post(
            "/hitl/create",
            json={"mission_title": "Mission LVMH", "reason": "Urgence critique."},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        hitl_id = resp.json()["hitl_id"]

        # Vérifier le stockage Redis — le blob est chiffré (AES-256-GCM)
        raw = fake_redis.get(f"hitl:{hitl_id}:pending")
        assert raw is not None, "La clé Redis doit exister"

        # Déchiffrer pour vérifier le contenu
        from hitl_router import _decrypt_hitl
        stored = _decrypt_hitl(raw)
        assert stored["mission_title"] == "Mission LVMH"
        assert stored["reason"] == "Urgence critique."
        assert stored["hitl_id"] == hitl_id

    def test_create_payload_is_encrypted(self, client, fake_redis):
        """Le payload Redis ne doit PAS être du JSON en clair (IMP-3 chiffrement actif)."""
        import json as _json
        resp = client.post(
            "/hitl/create",
            json={"mission_title": "Secret Mission", "reason": "Confidentiel."},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        hitl_id = resp.json()["hitl_id"]

        raw = fake_redis.get(f"hitl:{hitl_id}:pending")
        assert raw is not None

        # Le blob ne doit pas être parseable comme JSON clair
        try:
            _json.loads(raw)
            assert False, "Le payload Redis ne devrait PAS être du JSON en clair — chiffrement inactif !"
        except (_json.JSONDecodeError, ValueError):
            pass  # ✅ Preuve que le chiffrement AES-GCM est actif

    def test_create_requires_auth(self, client):
        """POST /hitl/create sans JWT doit retourner 401."""
        resp = client.post("/hitl/create", json={"mission_title": "X", "reason": "Y"})
        assert resp.status_code == 401


# ── Tests POST /hitl/respond ───────────────────────────────────────────────────
class TestHitlRespond:
    """Valide l'enregistrement de la décision HITL."""

    def _create_pending(self, fake_redis, hitl_id: str, mission_title: str = "Test Mission") -> None:
        """Helper : injecte un pending chiffré (AES-256-GCM) directement en Redis."""
        from hitl_router import _encrypt_hitl
        payload = {
            "hitl_id": hitl_id,
            "mission_title": mission_title,
            "reason": "Test reason",
            "candidates": [],
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        fake_redis.setex(f"hitl:{hitl_id}:pending", 1800, _encrypt_hitl(payload))

    def test_respond_approved(self, client, fake_redis):
        """POST /hitl/respond avec decision=approved doit retourner success=True."""
        hitl_id = str(uuid.uuid4())
        self._create_pending(fake_redis, hitl_id)

        resp = client.post(
            "/hitl/respond",
            json={"hitl_id": hitl_id, "decision": "approved", "comment": "Profil validé."},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["hitl_id"] == hitl_id

    def test_respond_rejected(self, client, fake_redis):
        """POST /hitl/respond avec decision=rejected doit retourner success=True."""
        hitl_id = str(uuid.uuid4())
        self._create_pending(fake_redis, hitl_id)

        resp = client.post(
            "/hitl/respond",
            json={"hitl_id": hitl_id, "decision": "rejected", "comment": "Score insuffisant."},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_respond_stores_decision_in_redis(self, client, fake_redis):
        """La décision doit être stockée chiffrée sous hitl:{id}:response en Redis."""
        hitl_id = str(uuid.uuid4())
        self._create_pending(fake_redis, hitl_id)

        client.post(
            "/hitl/respond",
            json={"hitl_id": hitl_id, "decision": "approved", "comment": "OK"},
            headers=_auth_headers(),
        )

        response_raw = fake_redis.get(f"hitl:{hitl_id}:response")
        assert response_raw is not None
        # Déchiffrer pour vérifier (IMP-3 — le blob est chiffré)
        from hitl_router import _decrypt_hitl
        stored = _decrypt_hitl(response_raw)
        assert stored["decision"] == "approved"
        assert stored["comment"] == "OK"
        assert "decided_at" in stored

    def test_respond_removes_pending(self, client, fake_redis):
        """Après la réponse, le pending Redis doit être supprimé."""
        hitl_id = str(uuid.uuid4())
        self._create_pending(fake_redis, hitl_id)

        client.post(
            "/hitl/respond",
            json={"hitl_id": hitl_id, "decision": "approved"},
            headers=_auth_headers(),
        )

        assert fake_redis.get(f"hitl:{hitl_id}:pending") is None

    def test_respond_404_on_unknown_hitl_id(self, client, fake_redis):
        """POST /hitl/respond avec hitl_id inconnu doit retourner 404."""
        resp = client.post(
            "/hitl/respond",
            json={"hitl_id": str(uuid.uuid4()), "decision": "approved"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_respond_400_on_invalid_decision(self, client, fake_redis):
        """POST /hitl/respond avec decision invalide doit retourner 400."""
        hitl_id = str(uuid.uuid4())
        self._create_pending(fake_redis, hitl_id)

        resp = client.post(
            "/hitl/respond",
            json={"hitl_id": hitl_id, "decision": "maybe"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

    def test_respond_requires_auth(self, client):
        """POST /hitl/respond sans JWT doit retourner 401."""
        resp = client.post("/hitl/respond", json={"hitl_id": "x", "decision": "approved"})
        assert resp.status_code == 401

    def test_respond_403_non_manager(self, client, fake_redis):
        """POST /hitl/respond avec un rôle 'consultant' doit retourner 403 (RBAC S-CRIT-2)."""
        hitl_id = str(uuid.uuid4())
        self._create_pending(fake_redis, hitl_id)

        resp = client.post(
            "/hitl/respond",
            json={"hitl_id": hitl_id, "decision": "approved"},
            headers=_user_headers(),  # rôle consultant — acces refusé
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ── Tests GET /hitl/pending ────────────────────────────────────────────────────
class TestHitlPending:
    """Valide la liste des demandes en attente."""

    def test_pending_empty(self, client, fake_redis):
        """GET /hitl/pending sans pending retourne une liste vide."""
        resp = client.get("/hitl/pending", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data
        assert isinstance(data["pending"], list)

    def test_pending_returns_created_items(self, client, fake_redis):
        """GET /hitl/pending doit retourner les demandes créées."""
        # Créer 2 demandes
        for mission in ("Mission Alpha", "Mission Beta"):
            client.post(
                "/hitl/create",
                json={"mission_title": mission, "reason": "Test"},
                headers=_auth_headers(),
            )

        resp = client.get("/hitl/pending", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2

    def test_pending_requires_auth(self, client):
        """GET /hitl/pending sans JWT doit retourner 401."""
        resp = client.get("/hitl/pending")
        assert resp.status_code == 401
