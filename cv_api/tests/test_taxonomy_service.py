from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services.taxonomy_service import (fetch_prompt,
                                           get_existing_competencies,
                                           run_taxonomy_step)


@pytest.mark.asyncio
async def test_fetch_prompt_success():
    with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"value": "Prompt content"}
        client_instance.get.return_value = mock_resp

        result = await fetch_prompt("prompt_name", "Bearer token")
        assert result == "Prompt content"


@pytest.mark.asyncio
async def test_get_existing_competencies_success():
    with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"items": [{"name": "Java"}], "total": 1}
        client_instance.get.return_value = mock_resp

        # On ne veut pas tester la DB ici, on mock database.get_db
        with patch("src.services.taxonomy_service.database.get_db", return_value=AsyncMock()):
            # Simulate empty DB result for CV keywords
            result = await get_existing_competencies("Bearer token")
            assert "Java" in result


@pytest.mark.asyncio
async def test_get_existing_competencies_fail_fast():
    with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        mock_resp = MagicMock(status_code=200)
        # Invalid payload (missing 'items' and 'total') to trigger ValidationError
        mock_resp.json.return_value = {"bad_key": "data"}
        client_instance.get.return_value = mock_resp

        with patch("src.services.taxonomy_service.logger.error") as mock_logger, \
             patch("src.services.taxonomy_service.database.get_db", return_value=AsyncMock()):
            result = await get_existing_competencies("Bearer token")
            # Result should be empty because of fail-fast on first page
            assert result == []
            mock_logger.assert_called_once()
            assert "Rupture de contrat API competencies" in mock_logger.call_args[0][0]


@pytest.mark.asyncio
async def test_run_taxonomy_step_apply():
    mock_genai_client = MagicMock()

    with patch("src.services.taxonomy_service.tree_task_manager.update_progress") as mock_update, \
         patch("src.services.taxonomy_service.tree_task_manager.get_latest_status") as mock_get_status:

        mock_get_status.return_value = {
            "res_tree": {"name": "Tech", "merge_from": ["OldTech"]},
            "sweep_result": [{"name": "DevOps", "merge_from": ["Ops"]}]
        }

        with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            MockClient.return_value.__aenter__.return_value = client_instance

            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {"merges": [{"canonical": "Tech"}]}
            client_instance.post.return_value = mock_resp

            await run_taxonomy_step("Bearer token", "user_1", "apply", mock_genai_client)

            # Vérifie que la mise à jour finale contient status='completed'
            mock_update.assert_called_with(
                new_log="Terminé. 1 doublon(s) fusionné(s).",
                tree={"name": "Tech", "merge_from": ["OldTech"]},
                usage={"merges_applied": 1},
                status="completed"
            )


@pytest.mark.asyncio
async def test_fetch_prompt_error():
    with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        client_instance.get.side_effect = Exception("API Down")

        with pytest.raises(RuntimeError) as exc:
            await fetch_prompt("prompt_name", "Bearer token")
        assert "could not be fetched" in str(exc.value)


@pytest.mark.asyncio
async def test_get_existing_competencies_db_fallback():
    with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"items": [{"name": "Java"}], "total": 1}
        client_instance.get.return_value = mock_resp

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_cv = MagicMock()
        mock_cv.competencies_keywords = ["Java", "Python", " C++ "]
        mock_result.scalars().all.return_value = [mock_cv]
        mock_db.execute.return_value = mock_result

        # Async generator mock for database.get_db
        async def mock_get_db():
            yield mock_db

        with patch("src.services.taxonomy_service.database.get_db", mock_get_db):
            result = await get_existing_competencies("Bearer token")
            assert "Java" in result
            assert "Python" in result
            assert "C++" in result


@pytest.mark.asyncio
async def test_run_taxonomy_step_map():
    mock_genai_client = MagicMock()

    with patch("src.services.taxonomy_service.tree_task_manager.get_latest_status") as mock_get_status, \
         patch("src.services.taxonomy_service.tree_task_manager.update_progress") as mock_update, \
         patch("src.services.taxonomy_service.get_existing_competencies") as mock_get_existing, \
         patch("src.services.taxonomy_service.fetch_prompt") as mock_fetch, \
         patch("src.services.taxonomy_service.generate_content_with_retry") as mock_gen, \
         patch("src.services.taxonomy_service.log_finops"):

        mock_get_status.return_value = {}
        mock_get_existing.return_value = ["Skill1", "Skill2"]
        mock_fetch.return_value = "Prompt {{EXISTING_COMPETENCIES}}"

        mock_gen_resp = MagicMock()
        mock_gen_resp.text = '{"items": [{"Pillar1": ["Skill1"]}, {"Pillar2": ["Skill2"]}]}'
        mock_gen_resp.usage_metadata = {}
        mock_gen.return_value = mock_gen_resp

        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-test", "GEMINI_PRO_MODEL": "gemini-pro-test"}):
            await run_taxonomy_step("Bearer token", "user_1", "map", mock_genai_client)

        mock_update.assert_called_with(
            map_result={"Pillar1": ["Skill1"], "Pillar2": ["Skill2"]},
            res_tree={},
            completed_pillars=[],
            sweep_result=None,
            status="waiting_for_user",
            new_log="Map terminé. 2 piliers générés. En attente de validation."
        )


@pytest.mark.asyncio
async def test_run_taxonomy_step_deduplicate():
    mock_genai_client = MagicMock()

    with patch("src.services.taxonomy_service.tree_task_manager.get_latest_status") as mock_get_status, \
         patch("src.services.taxonomy_service.tree_task_manager.update_progress") as mock_update, \
         patch("src.services.taxonomy_service.fetch_prompt") as mock_fetch, \
         patch("src.services.taxonomy_service.generate_content_with_retry") as mock_gen, \
         patch("src.services.taxonomy_service.log_finops"):

        mock_get_status.return_value = {"map_result": {"Pillar1": ["Skill1"], "Pillar2": ["Skill2"]}}
        mock_fetch.return_value = "Prompt"

        mock_gen_resp = MagicMock()
        mock_gen_resp.text = '{"items": [{"DedupPillar": ["Skill1", "Skill2"]}]}'
        mock_gen_resp.usage_metadata = {}
        mock_gen.return_value = mock_gen_resp

        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-test", "GEMINI_PRO_MODEL": "gemini-pro-test"}):
            await run_taxonomy_step("Bearer token", "user_1", "deduplicate", mock_genai_client)

        mock_update.assert_called_with(
            map_result={"DedupPillar": ["Skill1", "Skill2"]},
            status="waiting_for_user",
            new_log="Déduplication terminée. En attente de validation."
        )


@pytest.mark.asyncio
async def test_run_taxonomy_step_reduce():
    mock_genai_client = MagicMock()

    with patch("src.services.taxonomy_service.tree_task_manager.get_latest_status") as mock_get_status, \
         patch("src.services.taxonomy_service.tree_task_manager.update_progress") as mock_update, \
         patch("src.services.taxonomy_service.fetch_prompt") as mock_fetch, \
         patch("src.services.taxonomy_service.generate_content_with_retry") as mock_gen, \
         patch("src.services.taxonomy_service.log_finops"):

        mock_get_status.return_value = {"map_result": {"Pillar1": ["Skill1"]}}
        mock_fetch.return_value = "Prompt"

        mock_gen_resp = MagicMock()
        mock_gen_resp.text = '{"items": [{"name": "Pillar1", "sub_competencies": [{"name": "Skill1"}]}]}'
        mock_gen_resp.usage_metadata = {}
        mock_gen.return_value = mock_gen_resp

        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-test", "GEMINI_PRO_MODEL": "gemini-pro-test"}):
            await run_taxonomy_step("Bearer token", "user_1", "reduce", mock_genai_client)

        mock_update.assert_called_with(
            status="waiting_for_user",
            new_log="Étape Reduce terminée. En attente de validation."
        )


@pytest.mark.asyncio
async def test_run_taxonomy_step_sweep():
    mock_genai_client = MagicMock()

    with patch("src.services.taxonomy_service.tree_task_manager.get_latest_status") as mock_get_status, \
         patch("src.services.taxonomy_service.tree_task_manager.update_progress") as mock_update, \
         patch("src.services.taxonomy_service.get_existing_competencies") as mock_get_existing, \
         patch("src.services.taxonomy_service.fetch_prompt") as mock_fetch, \
         patch("src.services.taxonomy_service.generate_content_with_retry") as mock_gen, \
         patch("src.services.taxonomy_service.log_finops"):

        mock_get_status.return_value = {"res_tree": {"name": "Pillar1", "sub_competencies": [{"name": "Skill1"}]}}
        mock_get_existing.return_value = ["Skill1", "Skill2"]
        mock_fetch.return_value = "Prompt"

        mock_gen_resp = MagicMock()
        mock_gen_resp.text = '{"items": [{"name": "Pillar1", "merge_from": ["Skill2"]}]}'
        mock_gen_resp.usage_metadata = {}
        mock_gen.return_value = mock_gen_resp

        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-test", "GEMINI_PRO_MODEL": "gemini-pro-test"}):
            await run_taxonomy_step("Bearer token", "user_1", "sweep", mock_genai_client)

        mock_update.assert_called_with(
            sweep_result=[{"name": "Pillar1", "merge_from": ["Skill2"]}],
            status="waiting_for_user",
            new_log="Sweep terminé. 1 suggestions de rattrapage générées."
        )
