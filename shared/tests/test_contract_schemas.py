"""Tests de contrat pour les schémas partagés.

Ces tests garantissent que les APIs respectent le format PaginationResponse.
Un test qui échoue ici signifie une rupture de contrat inter-services.
"""
import pytest
from pydantic import ValidationError

from shared.schemas.pagination import PaginationResponse
from shared.schemas.missions import MissionsResponse
from shared.schemas.users import UsersResponse
from shared.schemas.mcp import McpToolResult


# ── PaginationResponse générique ──────────────────────────────────────────────

class TestPaginationResponse:
    """Tests du contrat de l'enveloppe de pagination générique."""

    def test_accepte_format_valide(self):
        r = PaginationResponse[dict].model_validate({"items": [{"id": 1}], "total": 1})
        assert r.total == 1
        assert len(r.items) == 1

    def test_accepte_liste_vide(self):
        r = PaginationResponse[dict].model_validate({"items": [], "total": 0})
        assert r.items == []

    def test_rejette_items_manquant(self):
        """Régression : ancienne clé 'missions' au lieu de 'items' doit échouer."""
        with pytest.raises(ValidationError):
            PaginationResponse[dict].model_validate({"missions": [], "total": 0})

    def test_rejette_items_non_array(self):
        with pytest.raises(ValidationError):
            PaginationResponse[dict].model_validate({"items": "not-a-list", "total": 0})

    def test_rejette_total_manquant(self):
        with pytest.raises(ValidationError):
            PaginationResponse[dict].model_validate({"items": []})

    def test_valeurs_par_defaut_skip_limit(self):
        r = PaginationResponse[dict].model_validate({"items": [], "total": 0})
        assert r.skip == 0
        assert r.limit == 50


# ── MissionsResponse ──────────────────────────────────────────────────────────

class TestMissionsResponse:
    """Tests du contrat missions — cas historique du bug missions→items."""

    def test_accepte_format_actuel(self):
        payload = {
            "items": [{"id": 1, "title": "Mission DevOps", "user_id": 42}],
            "total": 1,
        }
        r = MissionsResponse.model_validate(payload)
        assert r.items[0].title == "Mission DevOps"
        assert r.items[0].user_id == 42

    def test_rejette_ancienne_cle_missions(self):
        """Régression critique : ce test aurait détecté le bug en production."""
        with pytest.raises(ValidationError):
            MissionsResponse.model_validate({"missions": [], "total": 0})

    def test_champs_optionnels_absents(self):
        """Les champs optionnels peuvent être absents sans erreur."""
        r = MissionsResponse.model_validate(
            {"items": [{"id": 1, "title": "Mission"}], "total": 1}
        )
        assert r.items[0].description is None
        assert r.items[0].start_date is None

    def test_accepte_id_manquant(self):
        r = MissionsResponse.model_validate(
            {"items": [{"title": "Mission sans id"}], "total": 1}
        )
        assert r.items[0].id is None

    def test_rejette_title_manquant(self):
        with pytest.raises(ValidationError):
            MissionsResponse.model_validate(
                {"items": [{"id": 1}], "total": 1}
            )


# ── UsersResponse ─────────────────────────────────────────────────────────────

class TestUsersResponse:
    def test_accepte_format_valide(self):
        payload = {
            "items": [{"id": 1, "email": "alice@zenika.com"}],
            "total": 1,
        }
        r = UsersResponse.model_validate(payload)
        assert r.items[0].email == "alice@zenika.com"

    def test_rejette_items_manquant(self):
        with pytest.raises(ValidationError):
            UsersResponse.model_validate({"users": [], "total": 0})

    def test_champ_is_anonymous_par_defaut(self):
        r = UsersResponse.model_validate(
            {"items": [{"id": 1, "email": "anon@zenika.com"}], "total": 1}
        )
        assert r.items[0].is_anonymous is False


# ── McpToolResult ─────────────────────────────────────────────────────────────

class TestMcpToolResult:
    def test_accepte_result_liste(self):
        r = McpToolResult.model_validate({"result": [{"type": "text", "text": "ok"}]})
        assert len(r.result) == 1

    def test_accepte_result_vide(self):
        r = McpToolResult.model_validate({"result": []})
        assert r.result == []

    def test_result_par_defaut_vide(self):
        r = McpToolResult.model_validate({})
        assert r.result == []
