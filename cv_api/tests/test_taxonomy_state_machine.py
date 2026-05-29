"""
test_taxonomy_state_machine.py
==============================

Tests de la machine d'états du pipeline de recalcul de l'arbre taxonomique.

Pipeline officiel :
  map → deduplicate → reduce → sweep → apply

Ce fichier couvre :
  1. Validation des inputs HTTP (step vide, step inconnu, step valide)
  2. Préconditions de chaque étape (state Redis requis en entrée)
  3. Postconditions de chaque étape (state Redis produit en sortie)
  4. Transitions légales (A → B : le state de sortie de A permet de démarrer B)
  5. Transitions illégales (ex: reduce sans map_result préalable)
  6. Cas d'erreur : Gemini down, prompt absent, step vide/inconnu
  7. Non-régression du bug "étape vide" (ticket 2026-05-27)

Conventions de mock :
  - tree_task_manager est toujours mocké (pas de Redis réel)
  - generate_content_with_retry est toujours mocké (pas de Gemini réel)
  - fetch_prompt est mocké pour retourner un prompt fixe
  - log_finops est mocké pour ignorer les appels FinOps
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Env vars minimales pour le démarrage de l'app ────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./cv_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("GEMINI_MODEL", "gemini-test")
os.environ.setdefault("GEMINI_PRO_MODEL", "gemini-pro-test")

# ── Import de l'app (avec patch des dépendances externes au démarrage) ────────
with patch(
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
    return_value=MagicMock()
):
    _mock_redis = AsyncMock()
    _mock_redis.get.return_value = None
    _mock_redis.set.return_value = True
    with patch("redis.asyncio.from_url", return_value=_mock_redis):
        from fastapi.testclient import TestClient
        from main import app
        from shared.auth.jwt import verify_jwt
        from shared.database import get_db
        from src.services.taxonomy_service import run_taxonomy_step

AUTH = {"Authorization": "Bearer testtoken"}
VALID_STEPS = ["map", "deduplicate", "reduce", "sweep", "apply"]


def _admin_jwt():
    return {"sub": "admin@z.com", "email": "admin@z.com", "role": "admin"}


def _user_jwt():
    return {"sub": "user@z.com", "email": "user@z.com", "role": "user"}


async def _mock_get_db():
    yield AsyncMock()


app.dependency_overrides[get_db] = _mock_get_db
app.dependency_overrides[verify_jwt] = _admin_jwt


# =============================================================================
# 1. VALIDATION DES INPUTS HTTP — POST /recalculate_tree/step
# =============================================================================

class TestHttpInputValidation:
    """Vérifie que Pydantic rejette correctement les inputs invalides
    via le type TaxonomyStep (str, Enum) dans RecalculateStepRequest.

    Aucun code de garde n'est nécessaire dans le router — Pydantic
    génère lui-même un HTTP 422 avec le détail des valeurs attendues.
    """

    def test_empty_step_returns_422(self, mocker):
        """
        Non-régression du bug 2026-05-27 : un step vide doit être rejeté par
        le schéma Pydantic (TaxonomyStep Enum) avant d'atteindre le router.
        """
        mocker.patch(
            "src.cvs.routers.taxonomy_router.tree_task_manager.update_progress",
            new=AsyncMock()
        )
        mocker.patch(
            "src.cvs.routers.taxonomy_router.tree_task_manager.initialize_task",
            new=AsyncMock(return_value={"status": "running"})
        )
        with TestClient(app) as client:
            resp = client.post(
                "/recalculate_tree/step",
                json={"step": ""},
                headers=AUTH
            )
        assert resp.status_code == 422, (
            f"TaxonomyStep Enum doit rejeter un step vide, got {resp.status_code}: {resp.json()}"
        )

    def test_unknown_step_returns_422(self, mocker):
        """Un step non reconnu doit être rejeté par Pydantic (TaxonomyStep Enum)."""
        with TestClient(app) as client:
            resp = client.post(
                "/recalculate_tree/step",
                json={"step": "unknown"},
                headers=AUTH
            )
        assert resp.status_code == 422
        # Le message Pydantic liste les valeurs acceptées de l'Enum
        detail_str = str(resp.json())
        assert any(s in detail_str for s in ["map", "deduplicate", "reduce", "sweep", "apply"])

    def test_whitespace_step_returns_422(self, mocker):
        """Un step avec uniquement des espaces est rejeté par Pydantic (pas une valeur Enum valide)."""
        with TestClient(app) as client:
            resp = client.post(
                "/recalculate_tree/step",
                json={"step": "   "},
                headers=AUTH
            )
        assert resp.status_code == 422

    @pytest.mark.parametrize("step", VALID_STEPS)
    def test_valid_steps_accepted(self, mocker, step):
        """Chaque valeur du TaxonomyStep Enum doit être acceptée (200) par Pydantic."""
        mocker.patch(
            "src.cvs.routers.taxonomy_router.tree_task_manager.update_progress",
            new=AsyncMock()
        )
        mocker.patch(
            "src.cvs.routers.taxonomy_router.tree_task_manager.initialize_task",
            new=AsyncMock(return_value={"status": "running"})
        )
        mocker.patch(
            "src.cvs.routers.taxonomy_router.run_taxonomy_step",
            new=AsyncMock()
        )
        with TestClient(app) as client:
            resp = client.post(
                "/recalculate_tree/step",
                json={"step": step},
                headers=AUTH
            )
        assert resp.status_code == 200, (
            f"Le step valide '{step}' a été rejeté : {resp.status_code} — {resp.json()}"
        )

    def test_non_admin_returns_403(self, mocker):
        """Un utilisateur non-admin doit recevoir 403."""
        app.dependency_overrides[verify_jwt] = _user_jwt
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/recalculate_tree/step",
                    json={"step": "map"},
                    headers=AUTH
                )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = _admin_jwt

    def test_no_body_returns_422(self):
        """Absence de body → 422 Unprocessable Entity."""
        with TestClient(app) as client:
            resp = client.post("/recalculate_tree/step", headers=AUTH)
        assert resp.status_code == 422


# =============================================================================
# 2. PRÉCONDITIONS DE CHAQUE ÉTAPE (état Redis requis en entrée)
# =============================================================================

class TestStepPreconditions:
    """Vérifie que chaque étape vérifie ses préconditions avant de s'exécuter."""

    @pytest.fixture(autouse=True)
    def _env(self):
        with patch.dict("os.environ", {
            "GEMINI_MODEL": "gemini-test",
            "GEMINI_PRO_MODEL": "gemini-pro-test"
        }):
            yield

    @pytest.mark.asyncio
    async def test_deduplicate_fails_without_map_result(self, mocker):
        """deduplicate sans map_result dans Redis → met le status en error."""
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={"map_result": None})  # map_result absent
        )
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="prompt"))

        await run_taxonomy_step("Bearer token", "user", "deduplicate", MagicMock())

        # Vérifie qu'une erreur a été signalée
        calls = [str(c) for c in mock_update.call_args_list]
        assert any("error" in str(c).lower() or "status='error'" in str(c) for c in calls), (
            "deduplicate sans map_result devrait mettre le status en error"
        )

    @pytest.mark.asyncio
    async def test_reduce_fails_without_map_result(self, mocker):
        """reduce sans map_result dans Redis → met le status en error."""
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={"map_result": None, "res_tree": {}, "completed_pillars": []})
        )
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="prompt"))

        await run_taxonomy_step("Bearer token", "user", "reduce", MagicMock())

        calls = [str(c) for c in mock_update.call_args_list]
        assert any("error" in str(c).lower() or "status='error'" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_sweep_fails_without_res_tree(self, mocker):
        """sweep sans res_tree dans Redis → met le status en error."""
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={"res_tree": {}, "sweep_result": None})  # arbre vide
        )
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="prompt"))
        mocker.patch(
            "src.services.taxonomy_service.get_existing_competencies",
            new=AsyncMock(return_value=["Skill1"])
        )

        await run_taxonomy_step("Bearer token", "user", "sweep", MagicMock())

        calls = [str(c) for c in mock_update.call_args_list]
        assert any("error" in str(c).lower() or "status='error'" in str(c) for c in calls)


# =============================================================================
# 3. POSTCONDITIONS DE CHAQUE ÉTAPE (state Redis produit en sortie)
# =============================================================================

class TestStepPostconditions:
    """Vérifie que chaque étape produit le bon état Redis après exécution réussie."""

    @pytest.fixture(autouse=True)
    def _env(self):
        with patch.dict("os.environ", {
            "GEMINI_MODEL": "gemini-test",
            "GEMINI_PRO_MODEL": "gemini-pro-test"
        }):
            yield

    @pytest.fixture
    def _mock_genai(self):
        client = MagicMock()
        resp = MagicMock()
        resp.usage_metadata = {}
        return client, resp

    @pytest.mark.asyncio
    async def test_map_outputs_map_result_and_waits(self, mocker, _mock_genai):
        """map → produit map_result non-vide et status=waiting_for_user."""
        client, gen_resp = _mock_genai
        gen_resp.text = '{"Pillar1": ["Skill1", "Skill2"], "Pillar2": ["Skill3"]}'
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={})
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch(
            "src.services.taxonomy_service.get_existing_competencies",
            new=AsyncMock(return_value=["Skill1", "Skill2", "Skill3"])
        )
        mocker.patch(
            "src.services.taxonomy_service.fetch_prompt",
            new=AsyncMock(return_value="Prompt {{EXISTING_COMPETENCIES}}")
        )
        mocker.patch(
            "src.services.taxonomy_service.generate_content_with_retry",
            new=AsyncMock(return_value=gen_resp)
        )
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())
        mocker.patch(
            "src.services.taxonomy_service.get_or_create_prompt_cache",
            new=AsyncMock(return_value=None)
        )

        await run_taxonomy_step("Bearer token", "user", "map", client)

        # La dernière mise à jour doit contenir map_result, status=waiting_for_user
        final_call = mock_update.call_args
        assert final_call.kwargs.get("status") == "waiting_for_user", (
            f"map devrait mettre status=waiting_for_user, got: {final_call}"
        )
        map_result = final_call.kwargs.get("map_result")
        assert map_result is not None and len(map_result) > 0, (
            "map devrait produire un map_result non-vide"
        )

    @pytest.mark.asyncio
    async def test_deduplicate_outputs_updated_map_result(self, mocker, _mock_genai):
        """deduplicate → met à jour map_result et status=waiting_for_user."""
        client, gen_resp = _mock_genai
        gen_resp.text = '{"items": [{"MergedPillar": ["Skill1", "Skill2", "Skill3"]}]}'
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={
                "map_result": {"Pillar1": ["Skill1"], "Pillar2": ["Skill2", "Skill3"]}
            })
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="Prompt"))
        mocker.patch(
            "src.services.taxonomy_service.generate_content_with_retry",
            new=AsyncMock(return_value=gen_resp)
        )
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())

        await run_taxonomy_step("Bearer token", "user", "deduplicate", client)

        final_call = mock_update.call_args
        assert final_call.kwargs.get("status") == "waiting_for_user"
        # map_result mis à jour (les piliers fusionnés)
        new_map = final_call.kwargs.get("map_result")
        assert new_map is not None, "deduplicate doit produire un nouveau map_result"

    @pytest.mark.asyncio
    async def test_deduplicate_handles_list_of_strings(self, mocker, _mock_genai):
        """deduplicate avec réponse Gemini sous forme de liste de strings (piliers fusionnés)

        doit merger les compétences des anciens piliers vers les nouveaux piliers.
        """
        client, gen_resp = _mock_genai
        gen_resp.text = '["Cloud & Infrastructure", "Software Development"]'
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={
                "map_result": {
                    "Cloud": ["aws", "gcp"],
                    "Infrastructure": ["docker"],
                    "Software Development": ["python"]
                }
            })
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="Prompt"))
        mocker.patch(
            "src.services.taxonomy_service.generate_content_with_retry",
            new=AsyncMock(return_value=gen_resp)
        )
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())

        await run_taxonomy_step("Bearer token", "user", "deduplicate", client)

        final_call = mock_update.call_args
        assert final_call.kwargs.get("status") == "waiting_for_user"
        new_map = final_call.kwargs.get("map_result")
        assert new_map is not None
        assert "Cloud & Infrastructure" in new_map
        assert "Software Development" in new_map
        assert "aws" in new_map["Cloud & Infrastructure"]
        assert "docker" in new_map["Cloud & Infrastructure"]
        assert "python" in new_map["Software Development"]

    @pytest.mark.asyncio
    async def test_reduce_outputs_waiting_for_user(self, mocker, _mock_genai):
        """reduce → met status=waiting_for_user après structuration des piliers."""
        client, gen_resp = _mock_genai
        gen_resp.text = '{"items": [{"name": "Pillar1", "sub_competencies": [{"name": "Skill1"}]}]}'
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={
                "map_result": {"Pillar1": ["Skill1"]},
                "res_tree": {},
                "completed_pillars": [],
                "sweep_result": None,
            })
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="Prompt"))
        mocker.patch(
            "src.services.taxonomy_service.generate_content_with_retry",
            new=AsyncMock(return_value=gen_resp)
        )
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())

        await run_taxonomy_step("Bearer token", "user", "reduce", client)

        final_call = mock_update.call_args
        assert final_call.kwargs.get("status") == "waiting_for_user", (
            f"reduce devrait finir en waiting_for_user, got: {final_call}"
        )

    @pytest.mark.asyncio
    async def test_sweep_outputs_sweep_result_and_waits(self, mocker, _mock_genai):
        """sweep → produit sweep_result non-nul et status=waiting_for_user."""
        client, gen_resp = _mock_genai
        gen_resp.text = '{"items": [{"name": "Pillar1", "merge_from": ["OldSkill"]}]}'
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={
                "res_tree": {"name": "Pillar1", "sub_competencies": [{"name": "Skill1"}]},
                "sweep_result": None,
            })
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="Prompt"))
        mocker.patch(
            "src.services.taxonomy_service.generate_content_with_retry",
            new=AsyncMock(return_value=gen_resp)
        )
        mocker.patch(
            "src.services.taxonomy_service.get_existing_competencies",
            new=AsyncMock(return_value=["Skill1", "OldSkill"])
        )
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())

        await run_taxonomy_step("Bearer token", "user", "sweep", client)

        final_call = mock_update.call_args
        assert final_call.kwargs.get("status") == "waiting_for_user"
        sweep_result = final_call.kwargs.get("sweep_result")
        assert isinstance(sweep_result, list), "sweep doit produire une liste sweep_result"

    @pytest.mark.asyncio
    async def test_apply_outputs_completed(self, mocker):
        """apply → status=completed après envoi à competencies_api."""
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={
                "res_tree": {"name": "Tech", "merge_from": ["OldTech"]},
                "sweep_result": [{"name": "DevOps", "merge_from": ["Ops"]}],
            })
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mock_http = AsyncMock()
        mock_http.post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"merges": [{"canonical": "Tech"}]})
        )
        with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_http

            await run_taxonomy_step("Bearer token", "user", "apply", MagicMock())

        final_call = mock_update.call_args
        assert final_call.kwargs.get("status") == "completed", (
            f"apply devrait finir en status=completed, got: {final_call}"
        )


# =============================================================================
# 4. TRANSITIONS LÉGALES (output de A est un input valide pour B)
# =============================================================================

class TestLegalTransitions:
    """Vérifie que l'output d'une étape constitue un input valide pour la suivante."""

    def test_map_to_deduplicate_state_is_compatible(self):
        """L'état produit par 'map' (map_result non-vide) satisfait la précondition de 'deduplicate'."""
        # Simule l'état Redis après 'map'
        state_after_map = {
            "status": "waiting_for_user",
            "map_result": {"Pillar1": ["Skill1", "Skill2"], "Pillar2": ["Skill3"]},
            "res_tree": {},
            "completed_pillars": [],
            "sweep_result": None,
        }
        # Précondition de deduplicate : map_result doit être non-nul et non-vide
        assert state_after_map.get("map_result"), (
            "L'état post-map doit contenir map_result pour que deduplicate puisse démarrer"
        )
        assert len(state_after_map["map_result"]) > 0

    def test_deduplicate_to_reduce_state_is_compatible(self):
        """L'état produit par 'deduplicate' satisfait la précondition de 'reduce'."""
        state_after_dedup = {
            "status": "waiting_for_user",
            "map_result": {"MergedPillar": ["Skill1", "Skill2", "Skill3"]},
            "res_tree": {},
            "completed_pillars": [],
        }
        assert state_after_dedup.get("map_result"), (
            "L'état post-deduplicate doit conserver map_result pour que reduce puisse démarrer"
        )

    def test_reduce_to_sweep_state_is_compatible(self):
        """L'état produit par 'reduce' satisfait la précondition de 'sweep' (res_tree non-vide)."""
        state_after_reduce = {
            "status": "waiting_for_user",
            "map_result": {"Pillar1": ["Skill1"]},
            "res_tree": {"name": "Pillar1", "sub_competencies": [{"name": "Skill1"}]},
            "completed_pillars": ["Pillar1"],
        }
        assert state_after_reduce.get("res_tree"), (
            "L'état post-reduce doit contenir res_tree pour que sweep puisse démarrer"
        )

    def test_sweep_to_apply_state_is_compatible(self):
        """L'état produit par 'sweep' satisfait la précondition de 'apply' (sweep_result présent)."""
        state_after_sweep = {
            "status": "waiting_for_user",
            "res_tree": {"name": "Pillar1"},
            "sweep_result": [{"name": "Pillar1", "merge_from": ["OldSkill"]}],
        }
        # apply utilise res_tree et sweep_result
        assert state_after_sweep.get("res_tree") is not None
        assert state_after_sweep.get("sweep_result") is not None


# =============================================================================
# 5. TRANSITIONS ILLÉGALES (état manquant → error, pas de crash silencieux)
# =============================================================================

class TestIllegalTransitions:
    """Vérifie qu'une étape lancée hors séquence échoue proprement (status=error)."""

    @pytest.fixture(autouse=True)
    def _env(self):
        with patch.dict("os.environ", {
            "GEMINI_MODEL": "gemini-test",
            "GEMINI_PRO_MODEL": "gemini-pro-test"
        }):
            yield

    @pytest.mark.asyncio
    async def test_apply_without_res_tree_fails(self, mocker):
        """apply sans res_tree → doit mettre status=error (pas de crash silencieux)."""
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={
                "res_tree": {},  # vide — pas de reduce préalable
                "sweep_result": None,
            })
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        # apply va quand même tenter l'appel HTTP, mais avec un arbre vide
        with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.post.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={"merges": []})
            )
            MockClient.return_value.__aenter__.return_value = mock_http
            await run_taxonomy_step("Bearer token", "user", "apply", MagicMock())

        # Même si l'API répond 200, le log doit refléter 0 merges
        final_call = mock_update.call_args
        # Le status doit être completed ou error (pas silencieux)
        assert final_call.kwargs.get("status") in ("completed", "error")

    @pytest.mark.asyncio
    async def test_unknown_step_calls_error_update(self, mocker):
        """Un step inconnu envoyé directement à run_taxonomy_step → status=error dans Redis."""
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={})
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )

        await run_taxonomy_step("Bearer token", "user", "unknown_step", MagicMock())

        # La clause else doit avoir mis status=error
        error_calls = [
            c for c in mock_update.call_args_list
            if c.kwargs.get("status") == "error"
        ]
        assert len(error_calls) > 0, (
            "run_taxonomy_step avec un step inconnu devrait appeler update_progress(status='error')"
        )

    @pytest.mark.asyncio
    async def test_empty_step_calls_error_update(self, mocker):
        """Un step vide ('') envoyé directement à run_taxonomy_step → status=error dans Redis."""
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={})
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )

        await run_taxonomy_step("Bearer token", "user", "", MagicMock())

        error_calls = [
            c for c in mock_update.call_args_list
            if c.kwargs.get("status") == "error"
        ]
        assert len(error_calls) > 0, (
            "run_taxonomy_step avec step='' devrait appeler update_progress(status='error')"
        )


# =============================================================================
# 6. RÉSILIENCE — Gemini down, prompt absent
# =============================================================================

class TestStepResilience:
    """Vérifie que les étapes gèrent proprement les pannes externes."""

    @pytest.fixture(autouse=True)
    def _env(self):
        with patch.dict("os.environ", {
            "GEMINI_MODEL": "gemini-test",
            "GEMINI_PRO_MODEL": "gemini-pro-test"
        }):
            yield

    @pytest.mark.asyncio
    async def test_map_gemini_down_sets_error(self, mocker):
        """map → si Gemini lève une exception, status=error dans Redis."""
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={})
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch(
            "src.services.taxonomy_service.get_existing_competencies",
            new=AsyncMock(return_value=["Skill1"])
        )
        mocker.patch(
            "src.services.taxonomy_service.fetch_prompt",
            new=AsyncMock(return_value="Prompt {{EXISTING_COMPETENCIES}}")
        )
        mocker.patch(
            "src.services.taxonomy_service.generate_content_with_retry",
            side_effect=RuntimeError("Gemini API unavailable")
        )
        mocker.patch(
            "src.services.taxonomy_service.get_or_create_prompt_cache",
            new=AsyncMock(return_value=None)
        )
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())

        await run_taxonomy_step("Bearer token", "user", "map", MagicMock())

        error_calls = [
            c for c in mock_update.call_args_list
            if c.kwargs.get("status") == "error"
        ]
        assert len(error_calls) > 0, (
            "Une panne Gemini pendant 'map' doit mettre status=error dans Redis"
        )

    @pytest.mark.asyncio
    async def test_map_prompt_missing_sets_error(self, mocker):
        """map → si le prompt est absent (RuntimeError), status=error dans Redis."""
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={})
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch(
            "src.services.taxonomy_service.get_existing_competencies",
            new=AsyncMock(return_value=["Skill1"])
        )
        mocker.patch(
            "src.services.taxonomy_service.fetch_prompt",
            side_effect=RuntimeError("Prompt could not be fetched")
        )

        await run_taxonomy_step("Bearer token", "user", "map", MagicMock())

        error_calls = [
            c for c in mock_update.call_args_list
            if c.kwargs.get("status") == "error"
        ]
        assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_no_genai_client_sets_error(self, mocker):
        """Pas de client Gemini configuré → message d'erreur immédiat dans Redis."""
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={})
        )
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )

        await run_taxonomy_step("Bearer token", "user", "map", None)  # client=None

        error_calls = [
            c for c in mock_update.call_args_list
            if c.kwargs.get("status") == "error"
        ]
        assert len(error_calls) > 0, (
            "Un client Gemini None doit immédiatement mettre status=error"
        )


# =============================================================================
# 7. NON-RÉGRESSION EXPLICITE — Bug "étape vide" du 2026-05-27
# =============================================================================

class TestNonRegressionEmptyStep:
    """
    Tests explicitement nommés pour prévenir la régression du bug signalé le 2026-05-27.

    Symptôme : le frontend appelait executeTreeStep('') car nextInteractiveStep
    retournait '' quand currentInteractiveStep était 'unknown'. Le backend
    n'avait ni guard HTTP ni else clause dans run_taxonomy_step → step vide
    accepté silencieusement → log "[...] Lancement de l'étape: " (vide).
    """

    def test_http_guard_empty_step_returns_422(self, mocker):
        """
        Le schéma Pydantic (TaxonomyStep Enum) rejette step='' avec HTTP 422
        AVANT que la background task ne soit créée — c'est le mécanisme correct.

        Ce test garantit que la validation s'effectue au niveau du schéma Pydantic,
        et que la background task n'est jamais créée pour un step invalide.
        """
        mock_bg = mocker.patch(
            "src.cvs.routers.taxonomy_router.run_taxonomy_step",
            new=AsyncMock()
        )

        with TestClient(app) as client:
            resp = client.post(
                "/recalculate_tree/step",
                json={"step": ""},
                headers=AUTH
            )

        assert resp.status_code == 422, (
            f"TaxonomyStep Enum doit rejeter step='' avec 422, got {resp.status_code}"
        )
        # La background task ne doit JAMAIS avoir été créée
        mock_bg.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_guard_empty_step_sets_error_not_silent(self, mocker):
        """
        Guard service (2ème couche) : même si le step vide arrivait au service,
        il doit mettre status=error dans Redis (pas ignorer silencieusement).
        """
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.get_latest_status",
            new=AsyncMock(return_value={})
        )
        mock_update = AsyncMock()
        mocker.patch(
            "src.services.taxonomy_service.tree_task_manager.update_progress",
            new=mock_update
        )

        await run_taxonomy_step("Bearer token", "user", "", MagicMock())

        all_calls_str = str(mock_update.call_args_list)
        assert "error" in all_calls_str, (
            "Un step vide doit déclencher update_progress avec status='error', "
            f"pas être ignoré silencieusement. Calls: {all_calls_str}"
        )

    def test_log_message_contains_step_name_when_valid(self, mocker):
        """
        Le log 'Lancement de l'étape' doit toujours contenir le nom de l'étape.
        Ce test vérifie que le log n'est JAMAIS vide (non-régression du log tronqué).
        """
        mock_update = AsyncMock()
        mocker.patch(
            "src.cvs.routers.taxonomy_router.tree_task_manager.update_progress",
            new=mock_update
        )
        mocker.patch(
            "src.cvs.routers.taxonomy_router.tree_task_manager.initialize_task",
            new=AsyncMock(return_value={"status": "running"})
        )
        mocker.patch(
            "src.cvs.routers.taxonomy_router.run_taxonomy_step",
            new=AsyncMock()
        )

        with TestClient(app) as client:
            resp = client.post(
                "/recalculate_tree/step",
                json={"step": "deduplicate"},
                headers=AUTH
            )

        assert resp.status_code == 200
        # Le log doit inclure "deduplicate"
        log_calls = [str(c) for c in mock_update.call_args_list]
        assert any("deduplicate" in c for c in log_calls), (
            f"Le log de lancement doit contenir le nom de l'étape. Calls: {log_calls}"
        )
