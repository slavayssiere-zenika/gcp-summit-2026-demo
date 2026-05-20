"""
test_assignments_functional.py — Tests fonctionnels pour assignments_router.py.

Couverture visée (de 39% → ~75%) :
  - POST /user/{id}/assign/bulk     (L59-121)
  - DELETE /user/{id}/evaluations   (L160-174)
  - DELETE /user/{id}/remove/{comp} (L177-198)
  - GET /user/{id}                  (L201-248) — cache path + pagination
  - POST /internal/users/merge      (L251-298)
  - DELETE /user/{id}/clear         (L301-315)
  - POST /pubsub/user-events        (L318-351)
  - _get_assign_sem                  (L45-51)
"""
import asyncio
import base64
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_MONOREPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./competencies_assign_test.db"
os.environ["USERS_API_URL"] = "http://users_api:8000"
os.environ["SECRET_KEY"] = "testsecret"

import fakeredis
from fakeredis import aioredis

_fake_redis_server = fakeredis.FakeServer()
_fake_redis_client = aioredis.FakeRedis(
    server=_fake_redis_server, db=8, decode_responses=True
)

with patch(
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
    return_value=MagicMock(),
):
    import shared.cache as _cache_module
    from shared.database import engine, get_db
    from main import app
    from shared.auth.jwt import verify_jwt
    from src.competencies.models import Base
    # NE PAS remplacer _redis_pool ici (phase de collecte) — cela pollurait
    # les tests d'intégration qui tournent dans la même session.

if engine:
    engine.dispose()

sync_engine = create_engine(
    "sqlite:///./competencies_assign_test.db",
    connect_args={"check_same_thread": False},
)
async_engine = create_async_engine(
    "sqlite+aiosqlite:///./competencies_assign_test.db",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=async_engine,
)


async def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        await db.close()


def override_verify_jwt_admin():
    return {"sub": "1", "role": "admin", "allowed_category_ids": [1]}


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def setup_fake_redis_pool():
    """
    Remplace _redis_pool par un FakeRedis UNIQUEMENT pendant les tests de ce module.
    Sauvegarde + restaure la valeur originale pour ne pas polluer les tests d'intégration
    qui tournent dans la même session pytest.
    """
    _original_pool = _cache_module._redis_pool
    _cache_module._redis_pool = _fake_redis_client
    yield
    _cache_module._redis_pool = _original_pool


@pytest.fixture(autouse=True)
def wipe_db():
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)
    asyncio.run(_fake_redis_client.flushdb())
    yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_competency(client, name: str) -> dict:
    resp = client.post("/", json={"name": name, "description": f"Desc {name}"})
    # POST /competencies returns 201 Created
    assert resp.status_code in (200, 201), f"Failed to create: {resp.text}"
    return resp.json()


def _mock_get_user(user_id: int):
    """Patch get_user_from_api pour éviter les appels HTTP réels."""
    return patch(
        "src.competencies.assignments_router.get_user_from_api",
        new_callable=AsyncMock,
        return_value={"id": user_id, "username": f"user_{user_id}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. POST /user/{user_id}/assign/bulk
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssignBulk:
    """Couvre assignments_router.py L59-121."""

    @_mock_get_user(1)
    def test_assign_bulk_empty_list(self, mock_get_user, client):
        """Body vide → assigned=0, skipped=0."""
        resp = client.post(
            "/user/1/assign/bulk",
            json={"competency_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["assigned"] == 0

    @_mock_get_user(1)
    def test_assign_bulk_valid_competencies(self, mock_get_user, client):
        """Assigne plusieurs compétences valides → assigned == nombre de comp."""
        comp1 = _create_competency(client, "BulkPython")
        comp2 = _create_competency(client, "BulkGo")

        resp = client.post(
            "/user/1/assign/bulk",
            json={"competency_ids": [comp1["id"], comp2["id"]]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned"] == 2
        assert data["skipped"] == 0

    @_mock_get_user(1)
    def test_assign_bulk_invalid_ids_reported(self, mock_get_user, client):
        """IDs inexistants → reportés dans invalid_ids, skipped > 0."""
        resp = client.post(
            "/user/1/assign/bulk",
            json={"competency_ids": [9991, 9992]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] == 2
        assert set(data["invalid_ids"]) == {9991, 9992}

    @_mock_get_user(1)
    def test_assign_bulk_idempotent(self, mock_get_user, client):
        """Appel deux fois → pas d'erreur (ON CONFLICT DO NOTHING)."""
        comp = _create_competency(client, "IdempotentComp")
        for _ in range(2):
            resp = client.post(
                "/user/1/assign/bulk",
                json={"competency_ids": [comp["id"]]},
            )
            assert resp.status_code == 200

    def test_assign_bulk_rbac_forbidden(self, client):
        """Un consultant ne peut pas assigner des compétences à un autre."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.post(
                "/user/99/assign/bulk",
                json={"competency_ids": [1]},
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DELETE /user/{user_id}/evaluations — clear evaluations admin-only
# ═══════════════════════════════════════════════════════════════════════════════

class TestClearUserEvaluations:
    """Couvre assignments_router.py L160-174."""

    @_mock_get_user(1)
    def test_clear_evaluations_success(self, mock_get_user, client):
        """Admin peut supprimer toutes les évaluations d'un utilisateur."""
        # Créer une évaluation via user-score
        comp = _create_competency(client, "EvalToDelete")
        client.post(f"/user/1/assign/{comp['id']}")
        client.post(
            f"/evaluations/user/1/competency/{comp['id']}/user-score",
            json={"score": 3, "comment": "To be deleted"},
        )

        resp = client.delete("/user/1/evaluations")
        assert resp.status_code == 204

    def test_clear_evaluations_non_admin_forbidden(self, client):
        """Un consultant ne peut pas vider les évaluations → 403."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.delete("/user/10/evaluations")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DELETE /user/{user_id}/remove/{competency_id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestRemoveCompetencyFromUser:
    """Couvre assignments_router.py L177-198."""

    @_mock_get_user(1)
    def test_remove_competency_success(self, mock_get_user, client):
        """Supprime l'assignation d'une compétence pour un utilisateur."""
        comp = _create_competency(client, "ToRemove")
        # Assigner d'abord
        client.post(f"/user/1/assign/{comp['id']}")

        resp = client.delete(f"/user/1/remove/{comp['id']}")
        assert resp.status_code == 204

    @_mock_get_user(1)
    def test_remove_competency_idempotent(self, mock_get_user, client):
        """Supprimer une compétence non assignée → 204 sans erreur."""
        resp = client.delete("/user/1/remove/99999")
        assert resp.status_code == 204

    def test_remove_competency_rbac_forbidden(self, client):
        """Un consultant ne peut pas retirer des compétences d'un autre utilisateur."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.delete("/user/99/remove/1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GET /user/{user_id} — avec cache et pagination
# ═══════════════════════════════════════════════════════════════════════════════

class TestListUserCompetencies:
    """Couvre assignments_router.py L201-248."""

    @_mock_get_user(1)
    def test_list_user_competencies_empty(self, mock_get_user, client):
        """Utilisateur sans compétences → total=0."""
        resp = client.get("/user/999")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @_mock_get_user(1)
    def test_list_user_competencies_with_data(self, mock_get_user, client):
        """Retourne les compétences assignées avec pagination."""
        comp1 = _create_competency(client, "ListComp1")
        comp2 = _create_competency(client, "ListComp2")
        client.post(f"/user/1/assign/{comp1['id']}")
        client.post(f"/user/1/assign/{comp2['id']}")

        resp = client.get("/user/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @_mock_get_user(1)
    def test_list_user_competencies_pagination(self, mock_get_user, client):
        """skip/limit fonctionne correctement."""
        for i in range(3):
            comp = _create_competency(client, f"PaginComp{i}")
            client.post(f"/user/1/assign/{comp['id']}")

        resp = client.get("/user/1?skip=1&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2

    def test_list_user_competencies_rbac_forbidden(self, client):
        """Un consultant ne peut pas lister les compétences d'un autre."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.get("/user/99")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ═══════════════════════════════════════════════════════════════════════════════
# 5. POST /internal/users/merge
# ═══════════════════════════════════════════════════════════════════════════════

class TestMergeUsers:
    """Couvre assignments_router.py L251-298."""

    @_mock_get_user(1)
    def test_merge_users_success(self, mock_get_user, client):
        """Fusionne les compétences du source vers target."""
        comp = _create_competency(client, "MergeComp")
        # Assigner au source (user 100)
        client.post(f"/user/100/assign/{comp['id']}")

        resp = client.post(
            "/internal/users/merge",
            json={"source_id": 100, "target_id": 200},
            headers={"Authorization": "Bearer admintoken"},
        )
        assert resp.status_code == 200
        assert "migrated" in resp.json().get("message", "").lower()

    def test_merge_users_missing_auth(self, client):
        """Pas de header Authorization → 401."""
        resp = client.post(
            "/internal/users/merge",
            json={"source_id": 100, "target_id": 200},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 6. DELETE /user/{user_id}/clear — clear toutes les assignations admin-only
# ═══════════════════════════════════════════════════════════════════════════════

class TestClearUserCompetencies:
    """Couvre assignments_router.py L301-315."""

    @_mock_get_user(1)
    def test_clear_competencies_success(self, mock_get_user, client):
        """Admin peut supprimer toutes les assignations d'un utilisateur."""
        comp = _create_competency(client, "ToClear")
        client.post(f"/user/1/assign/{comp['id']}")

        resp = client.delete("/user/1/clear")
        assert resp.status_code == 204

        # Vérifier que la liste est vide après
        list_resp = client.get("/user/1")
        assert list_resp.json()["total"] == 0

    def test_clear_competencies_non_admin_forbidden(self, client):
        """Un consultant ne peut pas vider les compétences → 403."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.delete("/user/10/clear")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ═══════════════════════════════════════════════════════════════════════════════
# 7. POST /pubsub/user-events — Pub/Sub handler
# ═══════════════════════════════════════════════════════════════════════════════

class TestPubSubUserEvents:
    """Couvre assignments_router.py L318-351."""

    def _encode_payload(self, event_data: dict) -> str:
        return base64.b64encode(json.dumps(event_data).encode()).decode()

    def test_pubsub_missing_message_ignored(self, client):
        """Message Pub/Sub invalide → status 'ignored'."""
        resp = client.post("/pubsub/user-events", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_pubsub_missing_data_field_ignored(self, client):
        """Message sans 'data' → status 'ignored'."""
        resp = client.post(
            "/pubsub/user-events",
            json={"message": {"messageId": "123"}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_pubsub_user_merged_event(self, client):
        """Événement user.merged → migre les compétences et retourne 'processed'."""
        event = {
            "event": "user.merged",
            "data": {"source_id": 500, "target_id": 501},
        }
        payload = {
            "message": {
                "data": self._encode_payload(event),
                "messageId": "test-msg-1",
            }
        }
        resp = client.post("/pubsub/user-events", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "processed"

    def test_pubsub_unknown_event_type(self, client):
        """Événement inconnu → 'processed' sans erreur (silencieux)."""
        event = {"event": "user.created", "data": {"user_id": 999}}
        payload = {
            "message": {
                "data": self._encode_payload(event),
                "messageId": "test-msg-2",
            }
        }
        resp = client.post("/pubsub/user-events", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "processed"

    def test_pubsub_invalid_base64_returns_error(self, client):
        """Données base64 invalides → 'error' sans crash."""
        payload = {
            "message": {
                "data": "!!! NOT VALID BASE64 !!!",
                "messageId": "test-msg-3",
            }
        }
        resp = client.post("/pubsub/user-events", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. _get_assign_sem — Semaphore initialization (L45-51)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetAssignSem:
    """Couvre assignments_router.py L45-51."""

    def test_get_assign_sem_creates_semaphore(self):
        """_get_assign_sem initialise le semaphore avec la valeur par défaut."""
        from src.competencies import assignments_router
        # Reset du singleton pour tester l'initialisation
        assignments_router._ASSIGN_BULK_SEM = None
        sem = assignments_router._get_assign_sem()
        assert sem is not None
        assert isinstance(sem, asyncio.Semaphore)

    def test_get_assign_sem_singleton(self):
        """Deux appels consécutifs retournent le même objet."""
        from src.competencies import assignments_router
        sem1 = assignments_router._get_assign_sem()
        sem2 = assignments_router._get_assign_sem()
        assert sem1 is sem2

    def test_get_assign_sem_custom_env(self):
        """ASSIGN_BULK_SEMAPHORE env var configure la limite."""
        from src.competencies import assignments_router
        assignments_router._ASSIGN_BULK_SEM = None
        os.environ["ASSIGN_BULK_SEMAPHORE"] = "3"
        try:
            sem = assignments_router._get_assign_sem()
            assert sem._value == 3
        finally:
            del os.environ["ASSIGN_BULK_SEMAPHORE"]
            assignments_router._ASSIGN_BULK_SEM = None
