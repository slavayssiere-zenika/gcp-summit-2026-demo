"""
test_maybe_trigger_hitl.py — Tests unitaires de _maybe_trigger_hitl().

Valide le post-processing HITL dans run_agent_query :
  1. Quand requires_human_approval=True → hitl_create_entry() appelé → dict retourné.
  2. Quand requires_human_approval=False → None retourné (pas de HITL).
  3. Quand missions_result absent de session state → None retourné.
  4. Quand hitl_create_entry() lève une exception → None retourné (dégradé gracieux).
  5. Quand ENABLE_OUTPUT_SCHEMA=false → _maybe_trigger_hitl jamais appelé.

Architecture :
  - FakeRedis pour isoler Redis (pas de dépendance réseau).
  - Pas de httpx — hitl_create_entry() est maintenant un appel Python direct.
  - Mock de session_service.get_session() pour simuler les états ADK.
"""
import os
import sys

import pytest
import fakeredis

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "..")
for p in [os.path.join(_HERE, ".."), _ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["SECRET_KEY"] = "test-secret-key-32-chars-minimum!!"
os.environ["REDIS_URL"] = "redis://localhost:6379/12"
os.environ.setdefault("GEMINI_MODEL", "gemini-test")
os.environ.setdefault("ENABLE_OUTPUT_SCHEMA", "true")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_redis_client():
    """FakeRedis async partagé entre hitl_router._get_hitl_redis et les assertions."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def patch_hitl_redis(fake_redis_client, monkeypatch):
    """Remplace _get_hitl_redis() par le FakeRedis dans hitl_router.py."""
    import hitl_router as hitl_module
    monkeypatch.setattr(hitl_module, "_get_hitl_redis", lambda: fake_redis_client)


def _make_mock_session(missions_result: dict | None):
    """Crée un objet session simulant la session ADK avec state."""
    from unittest.mock import MagicMock, AsyncMock
    session = MagicMock()
    session.state = {"missions_result": missions_result} if missions_result else {}

    service = MagicMock()
    service.get_session = AsyncMock(return_value=session)
    return service


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMaybeTriggerHitlApprovalRequired:
    """requires_human_approval=True → HITL créé en Redis."""

    @pytest.mark.asyncio
    async def test_creates_hitl_entry_in_redis(self, fake_redis_client):
        """Quand requires_human_approval=True, une clé hitl:*:pending doit exister."""
        from agent import _maybe_trigger_hitl

        missions_result = {
            "mission_title": "Mission Capgemini Kubernetes",
            "requires_human_approval": True,
            "approval_reason": "Score de confiance < 0.8 — validation managériale.",
            "urgency_level": "high",
            "recommended_consultants": [
                {"consultant_id": 1, "full_name": "Alice Martin", "confidence_score": 0.78}
            ],
        }
        service = _make_mock_session(missions_result)

        result = await _maybe_trigger_hitl(
            session_service=service,
            app_name="test_app",
            user_id="user_1",
            session_id="sess_1",
            caller_session_id="caller_sess_1",
            auth_token=None,
        )

        # Le résultat doit contenir les champs HITL
        assert result is not None
        assert "hitl_id" in result
        assert result["mission_title"] == "Mission Capgemini Kubernetes"
        assert result["reason"] == "Score de confiance < 0.8 — validation managériale."
        assert len(result["candidates"]) == 1

        # La clé Redis doit exister
        hitl_id = result["hitl_id"]
        raw = await fake_redis_client.get(f"hitl:{hitl_id}:pending")
        assert raw is not None, f"Clé Redis hitl:{hitl_id}:pending absente"

        from hitl_router import _decrypt_hitl
        data = _decrypt_hitl(raw)
        assert data["mission_title"] == "Mission Capgemini Kubernetes"
        assert data["urgency_level"] == "high"
        assert data["session_id"] == "caller_sess_1"

    @pytest.mark.asyncio
    async def test_reason_auto_generated_when_absent(self, fake_redis_client):
        """Si approval_reason est absent/None, la raison est générée depuis urgency_level dans Redis."""
        from agent import _maybe_trigger_hitl

        missions_result = {
            "mission_title": "Mission X",
            "requires_human_approval": True,
            "approval_reason": None,  # absent
            "urgency_level": "critical",
            "recommended_consultants": [],
        }
        service = _make_mock_session(missions_result)

        result = await _maybe_trigger_hitl(
            session_service=service,
            app_name="test_app",
            user_id="user_1",
            session_id="sess_auto",
            caller_session_id=None,
            auth_token=None,
        )

        assert result is not None
        # La raison auto-générée doit contenir l'urgency_level dans le Redis
        raw = await fake_redis_client.get(f"hitl:{result['hitl_id']}:pending")
        from hitl_router import _decrypt_hitl
        data = _decrypt_hitl(raw)
        assert "critical" in data["reason"], (
            f"La raison auto-générée doit contenir 'critical', got: {data['reason']}"
        )

    @pytest.mark.asyncio
    async def test_candidates_correctly_mapped(self, fake_redis_client):
        """Les candidats doivent être correctement extraits du MissionAnalysis."""
        from agent import _maybe_trigger_hitl

        missions_result = {
            "mission_title": "Mission Y",
            "requires_human_approval": True,
            "urgency_level": "medium",
            "recommended_consultants": [
                {"consultant_id": 42, "full_name": "Bob Dupont", "confidence_score": 0.85},
                {"consultant_id": 99, "full_name": "Carol Martin", "confidence_score": 0.72},
            ],
        }
        service = _make_mock_session(missions_result)

        result = await _maybe_trigger_hitl(
            session_service=service,
            app_name="test_app",
            user_id="user_1",
            session_id="sess_candidates",
            caller_session_id="sess_caller",
            auth_token=None,
        )

        assert result is not None
        raw = await fake_redis_client.get(f"hitl:{result['hitl_id']}:pending")
        from hitl_router import _decrypt_hitl
        data = _decrypt_hitl(raw)
        assert len(data["candidates"]) == 2
        assert data["candidates"][0]["consultant_id"] == 42
        assert data["candidates"][1]["full_name"] == "Carol Martin"


class TestMaybeTriggerHitlNoApproval:
    """requires_human_approval=False ou absent → None retourné."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_required(self):
        """Cas nominal : requires_human_approval=False → None, pas d'entrée Redis."""
        from agent import _maybe_trigger_hitl

        missions_result = {
            "mission_title": "Mission normale",
            "requires_human_approval": False,
            "urgency_level": "low",
            "recommended_consultants": [],
        }
        service = _make_mock_session(missions_result)

        result = await _maybe_trigger_hitl(
            session_service=service,
            app_name="test_app",
            user_id="user_1",
            session_id="sess_no_hitl",
            caller_session_id=None,
            auth_token=None,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_missions_result_absent(self):
        """Si missions_result absent de session.state → None."""
        from agent import _maybe_trigger_hitl

        service = _make_mock_session(None)  # state vide

        result = await _maybe_trigger_hitl(
            session_service=service,
            app_name="test_app",
            user_id="user_1",
            session_id="sess_empty",
            caller_session_id=None,
            auth_token=None,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_session_not_found(self):
        """Si get_session() retourne None (session expirée) → None."""
        from agent import _maybe_trigger_hitl
        from unittest.mock import AsyncMock, MagicMock

        service = MagicMock()
        service.get_session = AsyncMock(return_value=None)

        result = await _maybe_trigger_hitl(
            session_service=service,
            app_name="test_app",
            user_id="user_1",
            session_id="sess_expired",
            caller_session_id=None,
            auth_token=None,
        )

        assert result is None


class TestMaybeTriggerHitlDegradedBehavior:
    """Dégradé gracieux — exception → None, pas de crash."""

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_failure(self, monkeypatch):
        """Si hitl_create_entry() lève une exception (Redis down) → None, pas de crash."""
        from agent import _maybe_trigger_hitl
        import hitl_router as hitl_module

        async def _failing_hitl_create_entry(**_kwargs):
            raise ConnectionError("Redis indisponible")

        monkeypatch.setattr(hitl_module, "hitl_create_entry", _failing_hitl_create_entry)

        missions_result = {
            "mission_title": "Mission crash",
            "requires_human_approval": True,
            "urgency_level": "high",
            "recommended_consultants": [],
        }
        service = _make_mock_session(missions_result)

        # Ne doit PAS lever d'exception — retourne None silencieusement
        result = await _maybe_trigger_hitl(
            session_service=service,
            app_name="test_app",
            user_id="user_1",
            session_id="sess_crash",
            caller_session_id=None,
            auth_token=None,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_get_session_failure(self):
        """Si get_session() lève une exception → None, pas de crash."""
        from agent import _maybe_trigger_hitl
        from unittest.mock import AsyncMock, MagicMock

        service = MagicMock()
        service.get_session = AsyncMock(side_effect=RuntimeError("ADK session failure"))

        result = await _maybe_trigger_hitl(
            session_service=service,
            app_name="test_app",
            user_id="user_1",
            session_id="sess_adk_fail",
            caller_session_id=None,
            auth_token=None,
        )

        assert result is None
