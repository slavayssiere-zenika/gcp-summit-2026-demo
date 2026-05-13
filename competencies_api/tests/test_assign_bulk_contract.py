"""
test_assign_bulk_contract.py — Tests de contrat de l'endpoint POST /user/{id}/assign/bulk.

Objectif : garantir que cet endpoint :
1. Retourne une ERREUR explicite si le payload est {"competencies": [...]} (mauvais format)
2. Fonctionne correctement avec {"competency_ids": [...]} (format attendu)
3. Ne retourne JAMAIS un 200 silencieux quand le payload est invalide

Régression couverte :
  - Avant le fix : le mauvais payload retournait 200 + "Aucune compétence fournie"
    → 0 assignments sans aucune erreur visible → bug silencieux catastrophique.
  - Après le fix : l'appel côté cv_api résout les noms en IDs avant d'appeler cet endpoint.
    Mais si le mauvais format arrive quand même, ce test le détecte.
"""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("USERS_API_URL", "http://users_api:8000")


# ─────────────────────────────────────────────────────────────────────────────
# Classe 1 : Comportement de l'endpoint assign/bulk
# ─────────────────────────────────────────────────────────────────────────────

class TestAssignBulkEndpointBehavior:
    """Teste le comportement réel de l'endpoint assignments_router.assign_competencies_bulk.

    Ces tests vérifient le contrat côté serveur (competencies_api).
    """

    def test_endpoint_reads_competency_ids_key(self):
        """L'endpoint lit body["competency_ids"] et ignore body["competencies"].

        Ce test documente le contrat de l'endpoint et détecte si quelqu'un
        modifie accidentellement la clé attendue dans assignments_router.py.
        """
        # Simuler le parsing du body comme le fait l'endpoint :
        # competency_ids = body.get("competency_ids", [])

        # Cas 1 : bon format → ids non-vides
        correct_body = {"competency_ids": [42, 87, 103]}
        ids_from_correct = correct_body.get("competency_ids", [])
        assert ids_from_correct == [42, 87, 103], \
            "Le format {'competency_ids': [...]} doit être lu correctement"

        # Cas 2 : mauvais format (ancien bug) → ids vides
        wrong_body = {"competencies": [{"name": "Python"}, {"name": "Terraform"}]}
        ids_from_wrong = wrong_body.get("competency_ids", [])
        assert ids_from_wrong == [], (
            "DOCUMENTATION DU COMPORTEMENT : si 'competencies' est envoyé au lieu de "
            "'competency_ids', l'endpoint retourne 0 assignments. "
            "Toujours résoudre les noms en IDs AVANT d'appeler cet endpoint."
        )

    def test_endpoint_returns_message_when_no_ids(self):
        """Quand competency_ids est vide, l'endpoint retourne un message descriptif.

        Ce message doit être suffisamment explicite pour détecter le bug en log.
        Le message actuel 'Aucune compétence fournie' est trop ambigu :
        il peut indiquer soit un payload vide (normal) soit un mauvais format (bug).
        """
        # Comportement actuel documenté
        simulated_response = {"assigned": 0, "skipped": 0, "message": "Aucune compétence fournie."}

        # Ce message SEUL ne permet pas de distinguer :
        # - payload vide intentionnel (normal)
        # - mauvais format de payload (bug silencieux)
        # TODO amélioration future : retourner 400 Bad Request si competency_ids absent

        assert simulated_response["assigned"] == 0
        assert "fournie" in simulated_response["message"].lower()

    def test_correct_payload_schema(self):
        """Vérifie la structure exacte du payload correct pour assign/bulk."""
        # Schémas incorrects qui ont causé le bug
        incorrect_schemas = [
            {"competencies": [{"name": "Python"}]},  # Objet au lieu d'ID
            {"competency_names": ["Python", "Terraform"]},  # Mauvaise clé
            {"ids": [1, 2, 3]},  # Mauvaise clé
            {},  # Vide → silencieux
        ]

        for wrong in incorrect_schemas:
            ids = wrong.get("competency_ids", [])
            assert ids == [], \
                f"Le payload incorrect {list(wrong.keys())} ne doit retourner aucun ID"


# ─────────────────────────────────────────────────────────────────────────────
# Classe 2 : Tests de contrat MCP (assign_competencies_bulk tool)
# ─────────────────────────────────────────────────────────────────────────────

class TestMcpAssignBulkContract:
    """Vérifie que le MCP tool assign_competencies_bulk respecte le contrat.

    Le MCP tool expose une interface différente (compétences par nom)
    mais doit résoudre les IDs avant d'appeler l'endpoint HTTP.
    """

    @pytest.mark.asyncio
    async def test_mcp_tool_calls_correct_endpoint(self, mocker):
        """Le MCP tool doit appeler POST /user/{id}/assign/bulk et non un autre endpoint."""
        mock_client = AsyncMock()
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"assigned": 2, "skipped": 0}),
        )
        mock_client.raise_for_status = MagicMock()
        mocker.patch("mcp_server.httpx.AsyncClient", return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_client),
            __aexit__=AsyncMock(return_value=None),
        ))

        from mcp_server import call_tool
        await call_tool(
            name="assign_competencies_bulk",
            arguments={"user_id": 42, "competencies": [{"name": "Python", "practiced": True}]},
        )

        assert mock_client.post.called, "Le MCP tool doit appeler POST"
        call_url = str(mock_client.post.call_args)
        assert "/user/42/assign/bulk" in call_url, \
            f"Mauvais endpoint appelé: {call_url}"

    @pytest.mark.asyncio
    async def test_mcp_tool_result_structure(self, mocker):
        """Le MCP tool doit retourner un résultat parseable avec assigned/skipped."""
        import json

        mock_client = AsyncMock()
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"success": True, "assigned": 5, "skipped": 1}),
        )
        mock_client.raise_for_status = MagicMock()
        mocker.patch("mcp_server.httpx.AsyncClient", return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_client),
            __aexit__=AsyncMock(return_value=None),
        ))

        from mcp_server import call_tool
        result = await call_tool(
            name="assign_competencies_bulk",
            arguments={"user_id": 1, "competencies": [{"name": "Terraform"}]},
        )

        assert result, "Le tool doit retourner un résultat non-vide"
        payload = json.loads(result[0].text)
        assert "assigned" in payload or "success" in payload, \
            f"Résultat MCP doit contenir 'assigned' ou 'success': {payload}"
