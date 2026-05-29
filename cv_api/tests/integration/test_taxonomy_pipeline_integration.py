"""
test_taxonomy_pipeline_integration.py
======================================

Test d'intégration de bout en bout de la machine d'état du recalcul de l'arbre.
Simule les appels HTTP POST /recalculate_tree/step pour chaque étape et vérifie
que le champ explicite 'batch_step' progresse correctement de bout en bout :
  map -> deduplicate -> reduce -> sweep -> apply
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ── Env vars minimales pour le démarrage ─────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./cv_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("GEMINI_MODEL", "gemini-test")
os.environ.setdefault("GEMINI_PRO_MODEL", "gemini-pro-test")

# Patch des dépendances externes
with patch(
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
    return_value=MagicMock()
):
    from fastapi.testclient import TestClient
    from main import app
    from shared.auth.jwt import verify_jwt
    from src.cvs.task_state import tree_task_manager
    from src.services.taxonomy_service import run_taxonomy_step

AUTH = {"Authorization": "Bearer testtoken"}


def _admin_jwt():
    return {"sub": "admin@z.com", "email": "admin@z.com", "role": "admin"}


app.dependency_overrides[verify_jwt] = _admin_jwt


@pytest.mark.asyncio
class TestTaxonomyPipelineIntegration:
    """Valide l'intégration de bout en bout et les transitions d'état de la taxonomie."""

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

    async def test_full_interactive_pipeline_transitions(self, mocker, _mock_genai):
        """Simule l'exécution successive de chaque étape du recalcul interactif.

        Vérifie la progression stricte du champ explicite 'batch_step' dans Redis.
        """
        client, gen_resp = _mock_genai
        
        # 1. Mock de l'état persistant Redis (TreeTaskState)
        # On va simuler un Redis partagé en mémoire locale via un dictionnaire.
        in_memory_state = {}
        
        async def mock_get_status():
            return in_memory_state
            
        async def mock_initialize():
            nonlocal in_memory_state
            in_memory_state = {
                "status": "running",
                "logs": [],
                "map_result": None,
                "res_tree": {},
                "completed_pillars": [],
                "sweep_result": None,
                "batch_step": None,
            }
            return in_memory_state
            
        async def mock_update(**kwargs):
            nonlocal in_memory_state
            for k, v in kwargs.items():
                if v is not None or k in ("sweep_result", "map_result"):
                    in_memory_state[k] = v
            # completed_pillar est géré à part par update_progress
            if "completed_pillar" in kwargs and kwargs["completed_pillar"]:
                cp = kwargs["completed_pillar"]
                if "completed_pillars" not in in_memory_state:
                    in_memory_state["completed_pillars"] = []
                if cp not in in_memory_state["completed_pillars"]:
                    in_memory_state["completed_pillars"].append(cp)
            return in_memory_state

        mocker.patch.object(tree_task_manager, "get_latest_status", new=mock_get_status)
        mocker.patch.object(tree_task_manager, "initialize_task", new=mock_initialize)
        mocker.patch.object(tree_task_manager, "update_progress", new=mock_update)

        # Mocks des dépendances d'API externes pour run_taxonomy_step
        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="Prompt {{EXISTING_COMPETENCIES}}"))
        mocker.patch("src.services.taxonomy_service.get_existing_competencies", new=AsyncMock(return_value=["AWS", "Python", "Docker"]))
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())
        mocker.patch("src.services.taxonomy_service.get_or_create_prompt_cache", new=AsyncMock(return_value=None))
        mocker.patch("src.cvs.routers.taxonomy_router.run_taxonomy_step", new=AsyncMock())

        # ── 1. Étape MAP ─────────────────────────────────────────────────────
        gen_resp.text = '{"Cloud": ["AWS"], "Development": ["Python"], "Containers": ["Docker"]}'
        mocker.patch("src.services.taxonomy_service.generate_content_with_retry", new=AsyncMock(return_value=gen_resp))

        # Initialisation via Router POST /recalculate_tree/step
        with TestClient(app) as test_client:
            resp = test_client.post("/recalculate_tree/step", json={"step": "map"}, headers=AUTH)
            assert resp.status_code == 200

        # Exécution de l'étape Map
        await run_taxonomy_step("Bearer test", "admin", "map", client)
        
        # Vérification postconditions Map
        assert in_memory_state["status"] == "waiting_for_user"
        assert in_memory_state["batch_step"] == "map"
        assert "Cloud" in in_memory_state["map_result"]

        # ── 2. Étape DEDUPLICATE ─────────────────────────────────────────────
        # Gemini retourne le tableau consolidé de Strings (les piliers finaux)
        gen_resp.text = '["Cloud & Infrastructure", "Development"]'
        mocker.patch("src.services.taxonomy_service.generate_content_with_retry", new=AsyncMock(return_value=gen_resp))

        with TestClient(app) as test_client:
            resp = test_client.post("/recalculate_tree/step", json={"step": "deduplicate"}, headers=AUTH)
            assert resp.status_code == 200
            assert in_memory_state["status"] == "running"

        # Exécution de l'étape Deduplicate
        await run_taxonomy_step("Bearer test", "admin", "deduplicate", client)

        # Vérification postconditions Deduplicate
        assert in_memory_state["status"] == "waiting_for_user"
        assert in_memory_state["batch_step"] == "deduplicate"
        # Les compétences ont été fusionnées/mappées via difflib !
        assert "Cloud & Infrastructure" in in_memory_state["map_result"]
        assert "Development" in in_memory_state["map_result"]
        assert "AWS" in in_memory_state["map_result"]["Cloud & Infrastructure"]
        assert "Docker" in in_memory_state["map_result"]["Cloud & Infrastructure"]

        # ── 3. Étape REDUCE ──────────────────────────────────────────────────
        gen_resp.text = '{"Cloud & Infrastructure": {"sub_competencies": [{"name": "AWS"}]}}'
        mocker.patch("src.services.taxonomy_service.generate_content_with_retry", new=AsyncMock(return_value=gen_resp))

        with TestClient(app) as test_client:
            resp = test_client.post("/recalculate_tree/step", json={"step": "reduce"}, headers=AUTH)
            assert resp.status_code == 200

        # Exécution de l'étape Reduce
        await run_taxonomy_step("Bearer test", "admin", "reduce", client)

        # Vérification postconditions Reduce
        assert in_memory_state["status"] == "waiting_for_user"
        assert in_memory_state["batch_step"] == "reduce"
        assert "Cloud & Infrastructure" in in_memory_state["res_tree"]

        # ── 4. Étape SWEEP ───────────────────────────────────────────────────
        # Aucune compétence orpheline
        mocker.patch("src.services.taxonomy_service.get_existing_competencies", new=AsyncMock(return_value=["AWS"]))
        
        with TestClient(app) as test_client:
            resp = test_client.post("/recalculate_tree/step", json={"step": "sweep"}, headers=AUTH)
            assert resp.status_code == 200

        # Exécution de l'étape Sweep
        await run_taxonomy_step("Bearer test", "admin", "sweep", client)

        # Vérification postconditions Sweep
        assert in_memory_state["status"] == "waiting_for_user"
        assert in_memory_state["batch_step"] == "sweep"
        assert in_memory_state["sweep_result"] == []

        # ── 5. Étape APPLY ───────────────────────────────────────────────────
        mock_http = AsyncMock()
        mock_http.post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"merges": []})
        )
        with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_http
            
            with TestClient(app) as test_client:
                resp = test_client.post("/recalculate_tree/step", json={"step": "apply"}, headers=AUTH)
                assert resp.status_code == 200

            # Exécution de l'étape Apply
            await run_taxonomy_step("Bearer test", "admin", "apply", client)

        # Vérification postconditions finales Apply (Terminé !)
        assert in_memory_state["status"] == "completed"
        assert in_memory_state["batch_step"] == "apply"

    async def test_pipeline_crash_resilience(self, mocker, _mock_genai):
        """Vérifie la résilience du pipeline en cas d'erreur de l'API Gemini.

        S'assure que le statut passe à 'error' et qu'un message d'erreur est écrit.
        """
        client, _ = _mock_genai
        in_memory_state = {}

        async def mock_get_status():
            return in_memory_state

        async def mock_initialize():
            nonlocal in_memory_state
            in_memory_state = {
                "status": "running",
                "logs": [],
                "map_result": None,
                "res_tree": {},
                "completed_pillars": [],
                "sweep_result": None,
                "batch_step": None,
            }
            return in_memory_state

        async def mock_update(**kwargs):
            nonlocal in_memory_state
            for k, v in kwargs.items():
                in_memory_state[k] = v
            return in_memory_state

        mocker.patch.object(tree_task_manager, "get_latest_status", new=mock_get_status)
        mocker.patch.object(tree_task_manager, "initialize_task", new=mock_initialize)
        mocker.patch.object(tree_task_manager, "update_progress", new=mock_update)

        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="Prompt {{EXISTING_COMPETENCIES}}"))
        mocker.patch("src.services.taxonomy_service.get_existing_competencies", new=AsyncMock(return_value=["AWS"]))
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())

        # Simuler une panne de Gemini (Timeout / Rate Limit)
        mocker.patch(
            "src.services.taxonomy_service.generate_content_with_retry",
            new=AsyncMock(side_effect=Exception("Gemini API Overloaded (Quota Exceeded)"))
        )

        # Initialisation via Router
        with TestClient(app) as test_client:
            resp = test_client.post("/recalculate_tree/step", json={"step": "map"}, headers=AUTH)
            assert resp.status_code == 200

        # Exécution de l'étape Map qui va crasher
        await run_taxonomy_step("Bearer test", "admin", "map", client)

        # Vérification de l'état d'erreur et nettoyage du verrou Redis
        assert in_memory_state["status"] == "error"
        assert "Gemini API Overloaded" in in_memory_state["error"]

    async def test_pipeline_edge_cases_and_robustness(self, mocker, _mock_genai):
        """Vérifie la robustesse du pipeline face aux edge cases de production.

        Test :
        - MAP : Gemini répond avec un JSON pollué par des balises Markdown ```json.
        - DEDUPLICATE : Gemini répond avec un dictionnaire enveloppé {"pillars": [...]}
                        ET avec des fautes de frappe et des casses mélangées (ex: "develpment", "CLouD & Infrastructure").
        - SWEEP : Gemini répond avec un dictionnaire vide {}.
        """
        client, gen_resp = _mock_genai
        in_memory_state = {}

        async def mock_get_status():
            return in_memory_state

        async def mock_initialize():
            nonlocal in_memory_state
            in_memory_state = {
                "status": "running",
                "logs": [],
                "map_result": None,
                "res_tree": {},
                "completed_pillars": [],
                "sweep_result": None,
                "batch_step": None,
            }
            return in_memory_state

        async def mock_update(**kwargs):
            nonlocal in_memory_state
            for k, v in kwargs.items():
                if v is not None or k in ("sweep_result", "map_result"):
                    in_memory_state[k] = v
            return in_memory_state

        mocker.patch.object(tree_task_manager, "get_latest_status", new=mock_get_status)
        mocker.patch.object(tree_task_manager, "initialize_task", new=mock_initialize)
        mocker.patch.object(tree_task_manager, "update_progress", new=mock_update)

        mocker.patch("src.services.taxonomy_service.fetch_prompt", new=AsyncMock(return_value="Prompt {{EXISTING_COMPETENCIES}}"))
        mocker.patch("src.services.taxonomy_service.get_existing_competencies", new=AsyncMock(return_value=["AWS", "Python"]))
        mocker.patch("src.services.taxonomy_service.log_finops", new=AsyncMock())
        mocker.patch("src.services.taxonomy_service.get_or_create_prompt_cache", new=AsyncMock(return_value=None))

        # ── 1. Étape MAP avec pollution Markdown ─────────────────────────────
        gen_resp.text = "```json\n{\n  \"Cloud\": [\"AWS\"],\n  \"Development\": [\"Python\"]\n}\n```"
        mocker.patch("src.services.taxonomy_service.generate_content_with_retry", new=AsyncMock(return_value=gen_resp))

        await run_taxonomy_step("Bearer test", "admin", "map", client)

        # Devrait avoir nettoyé le markdown et parsé le JSON avec succès !
        assert in_memory_state["status"] == "waiting_for_user"
        assert "Cloud" in in_memory_state["map_result"]

        # ── 2. Étape DEDUPLICATE avec enveloppe JSON et fautes de frappe ────
        gen_resp.text = "{\n  \"pillars\": [\"CLouD & Infrastructure\", \"develpment\"]\n}"
        mocker.patch("src.services.taxonomy_service.generate_content_with_retry", new=AsyncMock(return_value=gen_resp))

        await run_taxonomy_step("Bearer test", "admin", "deduplicate", client)

        # La similarité lexicale difflib et les casses doivent avoir matché :
        assert in_memory_state["status"] == "waiting_for_user"
        assert "CLouD & Infrastructure" in in_memory_state["map_result"]
        assert "develpment" in in_memory_state["map_result"]
        assert "AWS" in in_memory_state["map_result"]["CLouD & Infrastructure"]
        assert "Python" in in_memory_state["map_result"]["develpment"]

        # ── 3. Étape REDUCE ──────────────────────────────────────────────────
        gen_resp.text = '{"CLouD & Infrastructure": {"sub_competencies": [{"name": "AWS"}]}}'
        mocker.patch("src.services.taxonomy_service.generate_content_with_retry", new=AsyncMock(return_value=gen_resp))

        await run_taxonomy_step("Bearer test", "admin", "reduce", client)

        # ── 4. Étape SWEEP avec suggestion vide {} ───────────────────────────
        gen_resp.text = "{}"
        mocker.patch("src.services.taxonomy_service.generate_content_with_retry", new=AsyncMock(return_value=gen_resp))

        await run_taxonomy_step("Bearer test", "admin", "sweep", client)

        # Doit avoir traité le dictionnaire vide comme aucune suggestion de rattrapage
        assert in_memory_state["status"] == "waiting_for_user"
        assert in_memory_state["batch_step"] == "sweep"
        assert in_memory_state["sweep_result"] == []
