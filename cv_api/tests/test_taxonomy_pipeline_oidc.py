"""
test_taxonomy_pipeline_oidc.py — Tests unitaires du pipeline Taxonomy Batch.

Couvre les régressions identifiées lors de la session de stabilisation :
1. _get_oidc_token_for_service : génération OIDC locale vs GCP
2. _handle_reduce_step : sweep non skippé quand orphelines existent
3. Validation pré-bulk_tree : piliers fantômes filtrés
4. Contrat : missing=[] déclenche bulk_tree direct
"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# json_repair requis par taxonomy_batch_service lors de l'import
sys.modules.setdefault("json_repair", MagicMock(loads=MagicMock(return_value={})))

from src.services.taxonomy_batch_service import TaxonomyBatchService  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_oidc_patch(token_value: str = "oidc-token"):
    """Patch asyncio.to_thread pour retourner un token OIDC fixe."""
    return patch(
        "src.services.taxonomy_batch_service.asyncio.to_thread",
        new_callable=AsyncMock,
        return_value=token_value,
    )


def _make_status(step: str, res_tree: dict | None = None) -> dict:
    return {
        "status": "running",
        "batch_job_id": "projects/1/locations/eu/batchPredictionJobs/123",
        "batch_step": step,
        "service_token": "persisted-hs256-token",
        "res_tree": res_tree or {"Cloud & Infrastructure": {"Cloud Platforms": {}}},
        "map_result": {"Cloud & Infrastructure": ["AWS", "GCP"]},
        "completed_pillars": [],
        "sweep_result": None,
        "missing_competencies": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. _get_oidc_token_for_service
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_oidc_token_local_mode_returns_empty():
    """En mode local (USE_IAM_AUTH != true), le token OIDC n'est pas généré."""
    with patch.dict(os.environ, {"USE_IAM_AUTH": "false"}):
        token = await TaxonomyBatchService._get_oidc_token_for_service(
            "http://api.internal/api/competencies", "competencies_api"
        )
    assert token == ""


@pytest.mark.asyncio
async def test_get_oidc_token_gcp_mode_returns_token():
    """En mode GCP (USE_IAM_AUTH=true), retourne le token généré via fetch_id_token."""
    with patch.dict(os.environ, {"USE_IAM_AUTH": "true"}):
        with _make_oidc_patch("fresh-oidc-abc"):
            token = await TaxonomyBatchService._get_oidc_token_for_service(
                "http://api.internal/api/competencies", "competencies_api"
            )
    assert token == "fresh-oidc-abc"


@pytest.mark.asyncio
async def test_get_oidc_token_failure_returns_empty():
    """Si fetch_id_token lève une exception, retourne '' sans propager."""
    with patch.dict(os.environ, {"USE_IAM_AUTH": "true"}):
        with patch(
            "src.services.taxonomy_batch_service.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=Exception("metadata server unreachable"),
        ):
            token = await TaxonomyBatchService._get_oidc_token_for_service(
                "http://api.internal/api/competencies", "competencies_api"
            )
    assert token == ""


@pytest.mark.asyncio
async def test_get_oidc_token_for_competencies_alias():
    """_get_oidc_token_for_competencies est un alias de _get_oidc_token_for_service."""
    with patch.dict(os.environ, {"USE_IAM_AUTH": "true"}):
        with _make_oidc_patch("alias-token"):
            token = await TaxonomyBatchService._get_oidc_token_for_competencies(
                "http://api.internal/api/competencies"
            )
    assert token == "alias-token"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Sweep non skippé : missing > 0 → Vertex Sweep lancé
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_reduce_step_sweep_not_skipped_when_orphans_exist():
    """
    Régression critique : quand _get_existing_competencies retournait [] (401),
    missing=[] → sweep skippé. Ici on vérifie que Vertex Sweep est lancé
    quand des compétences orphelines existent.
    """
    res_tree = {"Cloud & Infrastructure": {"sub": [{"name": "Cloud Platforms"}]}}
    status = _make_status("reduce", res_tree=res_tree)
    parsed_results = [json.dumps(res_tree)]

    mock_job = MagicMock()
    mock_job.name = "sweep-job-123"

    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status",
               new_callable=AsyncMock, return_value=status), \
         patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress",
               new_callable=AsyncMock) as mock_update, \
         patch("src.services.taxonomy_batch_service.TaxonomyBatchService"
               ".generate_autonomous_service_token",
               new_callable=AsyncMock, return_value=""), \
         patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock), \
         patch("src.services.taxonomy_batch_service._fetch_prompt",
               new_callable=AsyncMock, return_value="sweep prompt {{MISSING_COMPETENCIES}}"), \
         patch("src.services.taxonomy_batch_service._get_existing_competencies",
               new_callable=AsyncMock, return_value=["AWS", "Kubernetes", "Python", "Docker"]), \
         patch("src.services.taxonomy_batch_service.gcs_storage.Client"), \
         patch("src.services.taxonomy_batch_service._svc_config.vertex_batch_client") as mock_vbatch, \
         patch("src.services.taxonomy_batch_service.BATCH_GCS_BUCKET", "test-bucket"), \
         patch.dict(os.environ, {
             "USE_IAM_AUTH": "false",
             "PROMPTS_API_URL": "http://api.internal/api/prompts",
             "COMPETENCIES_API_URL": "http://api.internal/api/competencies",
             "GEMINI_PRO_MODEL": "gemini-test",
         }):

        sys.modules["json_repair"].loads.return_value = res_tree
        mock_vbatch.batches.create.return_value = mock_job

        result = await TaxonomyBatchService._handle_reduce_step(
            user_caller="test-user",
            auth_token="scheduler-oidc-token",
            parsed_results=parsed_results,
            latest_status=status,
            usage=MagicMock(),
            persisted_svc_token="persisted-hs256-token",
        )

    assert result.get("success") is True, f"Résultat inattendu: {result}"
    assert "sweep" in result.get("state", "").lower() or "job" in str(result).lower(), (
        f"Le Sweep Vertex n'a pas été lancé. Résultat: {result}"
    )
    # Aucun statut "completed" direct sans sweep
    progress_calls = [str(c) for c in mock_update.call_args_list]
    completed_direct = any("'completed'" in c for c in progress_calls)
    assert not completed_direct, (
        "Le sweep a été skippé : statut 'completed' posé directement sans Vertex Sweep. "
        "Vérifier que _get_existing_competencies utilise le token OIDC competencies_api."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validation pré-bulk_tree : piliers fantômes filtrés
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_sweep_step_filters_phantom_pillars():
    """
    Vérifie que les assignments vers des piliers absents de l'arbre Reduce
    sont filtrés avant l'envoi à bulk_tree.
    """
    res_tree = {"Cloud & Infrastructure": {}}
    sweep_assignments = [
        {"competency": "AWS Lambda", "pillar": "Cloud & Infrastructure"},   # valide
        {"competency": "GCP Run", "pillar": "Cloud & Infrastructure"},      # valide
        {"competency": "Foo", "pillar": "Ghost Pillar XYZ"},                # fantôme
    ]
    sweep_data_str = json.dumps({
        "assignments": sweep_assignments,
        "merges": [],
        "drops": [],
    })

    status = _make_status("sweep", res_tree=res_tree)
    status["batch_job_id"] = "projects/1/locations/eu/batchPredictionJobs/sweep-99"

    bulk_payload_captured = {}

    async def capture_bulk(*args, **kwargs):
        bulk_payload_captured.update(kwargs.get("json", {}))
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "{}"
        return resp

    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status",
               new_callable=AsyncMock, return_value=status), \
         patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress",
               new_callable=AsyncMock), \
         patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock), \
         patch("src.services.taxonomy_batch_service.TaxonomyBatchService"
               "._get_oidc_token_for_competencies",
               new_callable=AsyncMock, return_value="comp-oidc-token"), \
         patch("src.services.taxonomy_batch_service.gcs_storage.Client") as mock_gcs, \
         patch("src.services.taxonomy_batch_service.httpx.AsyncClient") as mock_http, \
         patch("src.services.taxonomy_batch_service.publish_data_quality_snapshot",
               new_callable=AsyncMock), \
         patch.dict(os.environ, {
             "USE_IAM_AUTH": "false",
             "COMPETENCIES_API_URL": "http://api.internal/api/competencies",
             "GEMINI_PRO_MODEL": "gemini-test",
         }):

        sys.modules["json_repair"].loads.return_value = {
            "assignments": sweep_assignments,
            "merges": [],
            "drops": [],
        }

        mock_blob = MagicMock()
        mock_blob.name = "sweep/output/predictions.jsonl"
        mock_blob.download_as_text.return_value = json.dumps({
            "response": {"candidates": [{"content": {"parts": [{"text": sweep_data_str}]}}]}
        })
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_gcs.return_value.bucket.return_value = mock_bucket

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.post = AsyncMock(side_effect=capture_bulk)
        mock_http.return_value = mock_ctx

        await TaxonomyBatchService._handle_sweep_step(
            user_caller="test-user",
            auth_token="oidc-token",
            parsed_results=[sweep_data_str],
            latest_status=status,
            usage=MagicMock(),
            persisted_svc_token="persisted",
        )

    assert mock_ctx.post.called, "bulk_tree n'a pas été appelé"
    sent = bulk_payload_captured.get("sweep_assignments", [])
    assert len(sent) == 2, (
        f"Attendu 2 assignments (pilier fantôme filtré), reçu {len(sent)}: {sent}"
    )
    assert all(a["pillar"] != "Ghost Pillar XYZ" for a in sent), (
        "Le pilier fantôme 'Ghost Pillar XYZ' n'a pas été filtré."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. missing=[] → bulk_tree direct, pas de Vertex Sweep
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_reduce_step_no_orphans_goes_to_bulk_directly():
    """
    Quand existing_competencies est entièrement dans l'arbre,
    bulk_tree doit être appelé directement sans lancer Vertex Sweep.
    """
    res_tree = {"Cloud & Infrastructure": {"sub": [{"name": "AWS"}, {"name": "GCP"}]}}
    status = _make_status("reduce", res_tree=res_tree)
    parsed_results = [json.dumps(res_tree)]

    bulk_called = {"called": False}

    async def capture_bulk(*args, **kwargs):
        bulk_called["called"] = True
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "{}"
        return resp

    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status",
               new_callable=AsyncMock, return_value=status), \
         patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress",
               new_callable=AsyncMock) as mock_update, \
         patch("src.services.taxonomy_batch_service.TaxonomyBatchService"
               ".generate_autonomous_service_token",
               new_callable=AsyncMock, return_value=""), \
         patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock), \
         patch("src.services.taxonomy_batch_service._fetch_prompt",
               new_callable=AsyncMock, return_value="sweep prompt"), \
         patch("src.services.taxonomy_batch_service._get_existing_competencies",
               new_callable=AsyncMock, return_value=["AWS", "GCP"]), \
         patch("src.services.taxonomy_batch_service.TaxonomyBatchService"
               "._get_oidc_token_for_competencies",
               new_callable=AsyncMock, return_value="comp-oidc"), \
         patch("src.services.taxonomy_batch_service.httpx.AsyncClient") as mock_http, \
         patch("src.services.taxonomy_batch_service.publish_data_quality_snapshot",
               new_callable=AsyncMock), \
         patch.dict(os.environ, {
             "USE_IAM_AUTH": "false",
             "PROMPTS_API_URL": "http://api.internal/api/prompts",
             "COMPETENCIES_API_URL": "http://api.internal/api/competencies",
             "GEMINI_PRO_MODEL": "gemini-test",
         }):

        sys.modules["json_repair"].loads.return_value = res_tree
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.post = AsyncMock(side_effect=capture_bulk)
        mock_http.return_value = mock_ctx

        result = await TaxonomyBatchService._handle_reduce_step(
            user_caller="test-user",
            auth_token="scheduler-oidc-token",
            parsed_results=parsed_results,
            latest_status=status,
            usage=MagicMock(),
            persisted_svc_token="persisted",
        )

    assert result.get("success") is True, f"Résultat inattendu: {result}"
    assert bulk_called["called"], "bulk_tree direct n'a pas été appelé quand missing=[]"
    completed_calls = [
        c for c in mock_update.call_args_list
        if c.kwargs.get("status") == "completed" or "'completed'" in str(c)
    ]
    assert len(completed_calls) > 0, "Le statut 'completed' n'a pas été posé après bulk_tree direct"
