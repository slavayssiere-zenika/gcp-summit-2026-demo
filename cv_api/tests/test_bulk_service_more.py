import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.bulk_helpers import _post_missions_bulk
from src.services.bulk_service import bg_bulk_reanalyse


@pytest.mark.asyncio
async def test_post_missions_bulk_success():
    mock_hc = AsyncMock()
    mock_post_resp = MagicMock(status_code=200)
    mock_hc.post.return_value = mock_post_resp

    with patch("src.services.bulk_service.log_finops", new_callable=AsyncMock):
        missions = [{"company": "Z", "skills": ["S1"],
                     "start_date": "2020", "end_date": "2021"}]
        await _post_missions_bulk(mock_hc, 1, missions, {"Auth": "Bearer x"})
        mock_hc.post.assert_called()


@pytest.mark.asyncio
async def test_post_missions_bulk_failures():
    mock_hc = AsyncMock()
    mock_hc.post.side_effect = Exception("post err")
    with patch("src.services.bulk_helpers.logger") as mock_logger:
        missions = [{"company": "Z"}]
        await _post_missions_bulk(mock_hc, 1, missions, {"Auth": "Bearer x"})
        mock_logger.warning.assert_called()

    # Test empty missions
    mock_hc.post.reset_mock()
    await _post_missions_bulk(mock_hc, 1, [], {"Auth": "Bearer x"})
    mock_hc.post.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# Regression tests — SRE incident 2026-07-06
# Ticket : InvalidRequestError: Instance <Item> is not present in this Session
# Cause  : _post_missions_bulk envoyait des missions dupliquées (même titre
#          pour le même user_id) directement issues du LLM sans déduplication.
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_missions_bulk_deduplication():
    """Régression SRE-2026-07-06 : deux missions avec le même titre ne doivent
    envoyer qu'un seul item à items-api /bulk."""
    mock_hc = AsyncMock()
    mock_hc.post.return_value = MagicMock(status_code=201)

    missions = [
        {"title": "Tech Lead", "company": "Acme",
            "start_date": "2020", "end_date": "2022"},
        {"title": "Tech Lead", "company": "Acme",
            "start_date": "2022", "end_date": "2023"},  # doublon
        {"title": "Consultant Senior", "company": "Zenika",
            "start_date": "2023", "end_date": None},
    ]

    await _post_missions_bulk(mock_hc, 42, missions, {})

    mock_hc.post.assert_called_once()
    sent_payload = mock_hc.post.call_args.kwargs["json"]
    sent_items = sent_payload["items"]

    # Seulement 2 items (le doublon "Tech Lead" est filtré)
    assert len(sent_items) == 2
    names = [it["name"] for it in sent_items]
    assert names.count("Tech Lead") == 1
    assert "Consultant Senior" in names


@pytest.mark.asyncio
async def test_post_missions_bulk_end_date_field():
    """Régression bug copier-coller : end_date était mappé sur m.get('company')
    au lieu de m.get('end_date')."""
    mock_hc = AsyncMock()
    mock_hc.post.return_value = MagicMock(status_code=201)

    missions = [{
        "title": "Dev",
        "company": "Acme Corp",
        "start_date": "2021-01",
        "end_date": "2023-06",
    }]

    await _post_missions_bulk(mock_hc, 1, missions, {})

    sent_items = mock_hc.post.call_args.kwargs["json"]["items"]
    meta = sent_items[0]["metadata_json"]

    assert meta["end_date"] == "2023-06",   "end_date doit venir de m['end_date']"
    assert meta["company"] == "Acme Corp",  "company doit venir de m['company']"
    assert meta["start_date"] == "2021-01"


@pytest.mark.asyncio
async def test_post_missions_bulk_all_duplicates_no_http_call():
    """Si toutes les missions sont des doublons, aucun appel HTTP ne doit être fait."""
    mock_hc = AsyncMock()

    missions = [
        {"title": "Même mission", "company": "X"},
        {"title": "Même mission", "company": "X"},
    ]

    await _post_missions_bulk(mock_hc, 1, missions, {})
    mock_hc.post.assert_called_once()


@pytest.mark.asyncio
async def test_bg_bulk_reanalyse_with_filters():
    with patch("src.services.bulk_service.database.SessionLocal") as mock_session_local:
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db

        mock_result = MagicMock()
        mock_result.all.return_value = [(1, "Content", 42)]
        mock_db.execute.return_value = mock_result

        with patch("src.services.bulk_service.gcs_storage.Client"):
            with patch("src.services.bulk_service.vertex_batch_client") as mock_vbg:
                mock_job = MagicMock()
                mock_job.name = "job123"
                mock_job.state.name = "JOB_STATE_SUCCEEDED"
                mock_vbg.batches.create.return_value = mock_job
                mock_vbg.batches.get.return_value = mock_job

                with patch("src.services.bulk_service._get_cv_extraction_prompt", new_callable=AsyncMock) as mock_prompt:
                    mock_prompt.return_value = "prompt"
                    with patch("src.services.bulk_service.bulk_reanalyse_manager.update_progress", new_callable=AsyncMock):
                        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                            mock_get.return_value = MagicMock(status_code=200)
                            with patch("src.services.bulk_service.asyncio.sleep", new_callable=AsyncMock):
                                await bg_bulk_reanalyse("token")
                                mock_vbg.batches.create.assert_called()
