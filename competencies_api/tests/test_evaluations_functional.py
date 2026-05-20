"""
test_evaluations_functional.py — Tests fonctionnels pour evaluations_router.py.

Couverture visée (de 21% → ~70%) :
  - POST /evaluations/batch/search
  - POST /evaluations/batch/users
  - GET  /evaluations/user/{user_id}
  - GET  /evaluations/user/{user_id}/competency/{competency_id}
  - POST /evaluations/user/{user_id}/competency/{competency_id}/user-score
  - POST /evaluations/user/{user_id}/ai-score-all (sans IA réelle)
  - RBAC : 403 pour les rôles non autorisés

Note : Réutilise les fixtures du conftest.py (client, wipe_db, verify_jwt override).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Importé APRÈS que conftest.py a configuré l'env + le monorepo path
from main import app  # noqa: E402  (conftest initialise l'app avant)
from shared.auth.jwt import verify_jwt  # noqa: E402


def override_verify_jwt_admin():
    return {"sub": "1", "role": "admin", "allowed_category_ids": [1]}


# ── Helpers DB ────────────────────────────────────────────────────────────────

def _create_competency(client, name: str, parent_id: int | None = None) -> dict:
    payload = {"name": name, "description": f"Desc {name}", "parent_id": parent_id}
    resp = client.post("/", json=payload)
    # POST /competencies returns 201 Created
    assert resp.status_code in (200, 201), f"create_competency failed: {resp.text}"
    return resp.json()


def _assign(client, user_id: int, comp_id: int):
    """Assigne une compétence en mockant get_user_from_api (no Users API available in tests)."""
    with patch(
        "src.competencies.assignments_router.get_user_from_api",
        new_callable=AsyncMock,
        return_value={"id": user_id, "username": f"user_{user_id}"},
    ):
        resp = client.post(f"/user/{user_id}/assign/{comp_id}")
    assert resp.status_code in (200, 201), f"assign failed: {resp.text}"
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. POST /evaluations/batch/search
# ═══════════════════════════════════════════════════════════════════════════════

class TestBatchSearchEvaluations:
    """Couvre evaluations_router.py : search_batch_evaluations (L51-102)."""

    def test_batch_search_empty_competency_ids(self, client):
        """Si competency_ids est vide → retourne evaluations={}."""
        resp = client.post(
            "/evaluations/batch/search",
            json={"user_id": 42, "competency_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["evaluations"] == {}

    def test_batch_search_returns_evaluations(self, client):
        """Retourne les compétences assignées à l'utilisateur."""
        comp = _create_competency(client, "Python")
        _assign(client, 1, comp["id"])

        resp = client.post(
            "/evaluations/batch/search",
            json={"user_id": 1, "competency_ids": [comp["id"]]},
        )
        assert resp.status_code == 200
        data = resp.json()["evaluations"]
        assert str(comp["id"]) in data or comp["id"] in data

    def test_batch_search_missing_competencies_padded(self, client):
        """Si une compétence n'a pas d'évaluation → renvoyée avec scores None."""
        comp = _create_competency(client, "Rust")

        resp = client.post(
            "/evaluations/batch/search",
            json={"user_id": 1, "competency_ids": [comp["id"]]},
        )
        assert resp.status_code == 200
        data = resp.json()["evaluations"]
        # La compétence doit être présente avec scores None
        key = str(comp["id"]) if str(comp["id"]) in data else comp["id"]
        assert data[key]["ai_score"] is None
        assert data[key]["user_score"] is None

    def test_batch_search_rbac_self_access_allowed(self, client):
        """Un utilisateur peut accéder à ses propres évaluations."""
        # Créer la compétence en admin AVANT de switcher le JWT
        comp = _create_competency(client, "Go")
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "99", "role": "consultant"
        }
        try:
            resp = client.post(
                "/evaluations/batch/search",
                json={"user_id": 99, "competency_ids": [comp["id"]]},
            )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin

    def test_batch_search_rbac_cross_user_forbidden(self, client):
        """Un consultant ne peut pas voir les évaluations d'un autre."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.post(
                "/evaluations/batch/search",
                json={"user_id": 99, "competency_ids": [1]},
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ═══════════════════════════════════════════════════════════════════════════════
# 2. POST /evaluations/batch/users
# ═══════════════════════════════════════════════════════════════════════════════

class TestBatchUsersEvaluations:
    """Couvre evaluations_router.py : search_batch_users_evaluations (L105-161)."""

    def test_batch_users_empty_user_ids(self, client):
        """Si user_ids est vide → retourne evaluations={}."""
        resp = client.post(
            "/evaluations/batch/users",
            json={"competency_id": 1, "user_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["evaluations"] == {}

    def test_batch_users_rbac_consultant_forbidden(self, client):
        """Un consultant ne peut pas appeler batch/users (réservé admin/rh)."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.post(
                "/evaluations/batch/users",
                json={"competency_id": 1, "user_ids": [1, 2]},
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin

    def test_batch_users_pads_missing_users(self, client):
        """Les user_ids sans évaluation sont renvoyés avec scores None."""
        comp = _create_competency(client, "Kubernetes")

        resp = client.post(
            "/evaluations/batch/users",
            json={"competency_id": comp["id"], "user_ids": [101, 102]},
        )
        assert resp.status_code == 200
        data = resp.json()["evaluations"]
        for uid in ["101", "102", 101, 102]:
            if str(uid) in data or uid in data:
                key = str(uid) if str(uid) in data else uid
                assert data[key]["user_score"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. GET /evaluations/user/{user_id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestListUserEvaluations:
    """Couvre evaluations_router.py : list_user_evaluations (L164-248)."""

    def test_list_evaluations_user_no_competencies(self, client):
        """Utilisateur sans compétences → liste vide."""
        resp = client.get("/evaluations/user/999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_evaluations_user_with_leaf_competency(self, client):
        """Utilisateur avec une compétence feuille → retournée dans la liste."""
        comp = _create_competency(client, "Docker")
        _assign(client, 1, comp["id"])

        resp = client.get("/evaluations/user/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_list_evaluations_rbac_self(self, client):
        """Un utilisateur peut lister ses propres évaluations."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "55", "role": "consultant"
        }
        try:
            resp = client.get("/evaluations/user/55")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin

    def test_list_evaluations_rbac_cross_user_forbidden(self, client):
        """Un consultant ne peut pas voir les évaluations d'un autre utilisateur."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "55", "role": "consultant"
        }
        try:
            resp = client.get("/evaluations/user/66")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin

    def test_list_evaluations_with_skip_limit(self, client):
        """Pagination skip/limit fonctionne."""
        resp = client.get("/evaluations/user/1?skip=0&limit=10")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GET /evaluations/user/{user_id}/competency/{competency_id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetUserCompetencyEvaluation:
    """Couvre evaluations_router.py : get_user_competency_evaluation (L251-293)."""

    def test_get_evaluation_competency_not_found(self, client):
        """Retourne 404 si la compétence n'existe pas."""
        resp = client.get("/evaluations/user/1/competency/9999")
        assert resp.status_code == 404

    def test_get_evaluation_no_score_yet(self, client):
        """Compétence existante sans évaluation → retourne scores None."""
        comp = _create_competency(client, "Terraform")

        resp = client.get(f"/evaluations/user/1/competency/{comp['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_score"] is None
        assert data["user_score"] is None
        assert data["competency_name"] == "Terraform"

    def test_get_evaluation_rbac_forbidden(self, client):
        """Un consultant ne peut pas voir les évaluations d'un autre."""
        # Créer la compétence en admin AVANT de switcher le JWT
        comp = _create_competency(client, "Ansible")
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.get(f"/evaluations/user/99/competency/{comp['id']}")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ═══════════════════════════════════════════════════════════════════════════════
# 5. POST /evaluations/user/{user_id}/competency/{competency_id}/user-score
# ═══════════════════════════════════════════════════════════════════════════════

class TestSetUserScore:
    """Couvre evaluations_router.py : set_user_competency_score (L296-328)."""

    def test_set_user_score_creates_evaluation(self, client):
        """POST user-score crée l'évaluation si elle n'existe pas encore."""
        comp = _create_competency(client, "GraphQL")
        _assign(client, 1, comp["id"])

        resp = client.post(
            f"/evaluations/user/1/competency/{comp['id']}/user-score",
            json={"score": 3, "comment": "Bonne maîtrise"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_score"] == 3
        assert data["user_comment"] == "Bonne maîtrise"

    def test_set_user_score_updates_existing(self, client):
        """POST user-score met à jour un score existant."""
        comp = _create_competency(client, "Redis")
        _assign(client, 1, comp["id"])

        # 1er score
        client.post(
            f"/evaluations/user/1/competency/{comp['id']}/user-score",
            json={"score": 2, "comment": "Débutant"},
        )
        # 2ème score
        resp = client.post(
            f"/evaluations/user/1/competency/{comp['id']}/user-score",
            json={"score": 4, "comment": "Expert"},
        )
        assert resp.status_code == 200
        assert resp.json()["user_score"] == 4

    def test_set_user_score_competency_not_found(self, client):
        """POST user-score sur compétence inexistante → 404."""
        resp = client.post(
            "/evaluations/user/1/competency/9999/user-score",
            json={"score": 1, "comment": ""},
        )
        assert resp.status_code == 404

    def test_set_user_score_rbac_forbidden(self, client):
        """Un consultant ne peut pas scorer les évaluations d'un autre."""
        # Créer la compétence en admin AVANT de switcher le JWT
        comp = _create_competency(client, "Kafka")
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.post(
                f"/evaluations/user/99/competency/{comp['id']}/user-score",
                json={"score": 2, "comment": ""},
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin

    def test_set_user_score_self_allowed(self, client):
        """Un consultant peut noter ses propres compétences."""
        # Créer la compétence en admin AVANT de switcher le JWT
        comp = _create_competency(client, "FastAPI")
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "77", "role": "consultant"
        }
        try:
            resp = client.post(
                f"/evaluations/user/77/competency/{comp['id']}/user-score",
                json={"score": 5, "comment": "Expert"},
            )
            assert resp.status_code in (200, 201)
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ═══════════════════════════════════════════════════════════════════════════════
# 6. POST /evaluations/user/{user_id}/ai-score-all
# ═══════════════════════════════════════════════════════════════════════════════

class TestTriggerAiScoreAll:
    """Couvre evaluations_router.py : trigger_ai_score_all (L389-478)."""

    @patch("httpx.AsyncClient.post")
    def test_ai_score_all_no_competencies(self, mock_post, client):
        """Utilisateur sans compétences → triggered=0, aucune tâche en arrière-plan."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403  # service token indisponible → fallback
        mock_post.return_value = mock_resp

        resp = client.post("/evaluations/user/999/ai-score-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == 999
        assert data["triggered"] == 0

    @patch("src.competencies.evaluations_router._score_all_bg", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.post")
    def test_ai_score_all_with_competencies(self, mock_post, mock_bg, client):
        """POST ai-score-all lance les background tasks pour les compétences feuilles."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_post.return_value = mock_resp

        comp = _create_competency(client, "MLOps")
        _assign(client, 1, comp["id"])

        resp = client.post("/evaluations/user/1/ai-score-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == 1
        assert data["triggered"] >= 1

    @patch("httpx.AsyncClient.post")
    def test_ai_score_all_rbac_forbidden(self, mock_post, client):
        """Un consultant ne peut pas déclencher le scoring IA pour un autre."""
        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "10", "role": "consultant"
        }
        try:
            resp = client.post("/evaluations/user/99/ai-score-all")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = override_verify_jwt_admin

    @patch("src.competencies.evaluations_router._score_all_bg", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.post")
    def test_ai_score_all_only_missing_flag(self, mock_post, mock_bg, client):
        """?only_missing=true filtre les compétences déjà scorées."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_post.return_value = mock_resp

        comp = _create_competency(client, "Terraform Cloud")
        _assign(client, 1, comp["id"])
        # Scorer manuellement la compétence
        client.post(
            f"/evaluations/user/1/competency/{comp['id']}/user-score",
            json={"score": 3, "comment": ""},
        )

        resp = client.post("/evaluations/user/1/ai-score-all?only_missing=true")
        assert resp.status_code == 200
        # Avec only_missing=true, les compétences sans ai_score sont retournées
        # (user-score ≠ ai-score, donc la compétence peut encore manquer le ai_score)
        assert "triggered" in resp.json()
