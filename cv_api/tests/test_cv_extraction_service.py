import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from src.services.cv_extraction_service import CVExtractionService
import unittest


@pytest.mark.asyncio
async def test_fetch_cv_content_invalid_url_scheme():
    with pytest.raises(HTTPException) as exc:
        await CVExtractionService.fetch_cv_content("ftp://invalid")
    assert exc.value.status_code == 400
    assert "Invalid URL scheme" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_internal_url():
    with pytest.raises(HTTPException) as exc:
        await CVExtractionService.fetch_cv_content("http://localhost/test")
    assert exc.value.status_code == 400
    assert "Internal URLs are not allowed" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_docx_invalid_url():
    with pytest.raises(HTTPException) as exc:
        await CVExtractionService.fetch_cv_content("https://docs.google.com/invalid", file_type="docx")
    assert exc.value.status_code == 400
    assert "impossible d'extraire le file_id" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_docx_no_token():
    with pytest.raises(HTTPException) as exc:
        await CVExtractionService.fetch_cv_content("https://docs.google.com/file/d/123", file_type="docx")
    assert exc.value.status_code == 400
    assert "google_access_token OAuth2 requis" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_docx_auth_error():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        with pytest.raises(HTTPException) as exc:
            await CVExtractionService.fetch_cv_content("https://docs.google.com/file/d/123", google_token="token", file_type="docx")
        assert exc.value.status_code == 400
        assert "Accès refusé pour le DOCX Drive" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_docx_too_large():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"0" * (11 * 1024 * 1024)  # 11 MB
        mock_get.return_value = mock_resp

        with pytest.raises(HTTPException) as exc:
            await CVExtractionService.fetch_cv_content("https://docs.google.com/file/d/123", google_token="token", file_type="docx")
        assert exc.value.status_code == 400
        assert "trop volumineux" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_docx_invalid_magic():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"INVALID_MAGIC_BYTES"
        mock_get.return_value = mock_resp

        with pytest.raises(HTTPException) as exc:
            await CVExtractionService.fetch_cv_content("https://docs.google.com/file/d/123", google_token="token", file_type="docx")
        assert exc.value.status_code == 400
        assert "signature ZIP invalide" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_docx_success():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"PK\x03\x04MockDOCXContent"
        mock_get.return_value = mock_resp

        with patch("docx.Document") as mock_document:
            mock_doc_instance = MagicMock()

            mock_p1 = MagicMock()
            mock_p1.text = "Hello World"
            mock_p2 = MagicMock()
            mock_p2.text = "  "
            mock_doc_instance.paragraphs = [mock_p1, mock_p2]

            mock_table = MagicMock()
            mock_row = MagicMock()
            mock_cell = MagicMock()
            mock_cell.text = "Table content"
            mock_row.cells = [mock_cell]
            mock_table.rows = [mock_row]
            mock_doc_instance.tables = [mock_table]

            mock_document.return_value = mock_doc_instance

            res = await CVExtractionService.fetch_cv_content("https://docs.google.com/file/d/123", google_token="token", file_type="docx")
            assert "Hello World" in res
            assert "Table content" in res


@pytest.mark.asyncio
async def test_fetch_cv_content_google_doc_no_token():
    with pytest.raises(HTTPException) as exc:
        await CVExtractionService.fetch_cv_content("https://docs.google.com/document/d/123", file_type="google_doc")
    assert exc.value.status_code == 400
    assert "google_access_token OAuth2 est requis" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_google_doc_auth_error():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        with pytest.raises(HTTPException) as exc:
            await CVExtractionService.fetch_cv_content("https://docs.google.com/document/d/123", google_token="token", file_type="google_doc")
        assert exc.value.status_code == 400
        assert "Accès refusé par l'API Drive" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_cv_content_google_doc_success():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Google Doc Text"
        mock_get.return_value = mock_resp

        res = await CVExtractionService.fetch_cv_content("https://docs.google.com/document/d/123", google_token="token", file_type="google_doc")
        assert res == "Google Doc Text"


@pytest.mark.asyncio
async def test_analyze_cv_tree_context_fallback_http():
    with patch("src.services.cv_extraction_service.get_cache", side_effect=lambda k: "cached_prompt" if k == "cv_api:prompt" else None):
        with patch("src.services.cv_extraction_service.set_cache", new_callable=AsyncMock) as mock_set:
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                # Mock pagination response structure
                mock_resp.json.return_value = {
                    "items": [{"id": 1, "name": "Python", "category": "Language", "parent_id": 2}],
                    "total": 1,
                    "skip": 0,
                    "limit": 100
                }
                # Return empty response for second page
                mock_resp_empty = MagicMock()
                mock_resp_empty.status_code = 200
                mock_resp_empty.json.return_value = {
                    "items": [],
                    "total": 1,
                    "skip": 100,
                    "limit": 100
                }
                mock_get.side_effect = [mock_resp, mock_resp_empty]

                with patch("src.services.cv_extraction_service.generate_content_with_retry", new_callable=AsyncMock) as mock_gen:
                    mock_gen_resp = MagicMock()
                    mock_gen_resp.text = '{"is_cv": true, "competencies": [], "missions": []}'
                    mock_gen.return_value = mock_gen_resp

                    await CVExtractionService.analyze_cv_with_llm("raw text", headers={"Authorization": "Bearer test"}, genai_client=MagicMock())

                    calls = [call.args[0] for call in mock_set.call_args_list]
                    assert "cv_api:tree_context" in calls


@pytest.mark.asyncio
async def test_analyze_cv_tree_context_fallback_error():
    with patch("src.services.cv_extraction_service.get_cache", side_effect=lambda k: "cached_prompt" if k == "cv_api:prompt" else None):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("HTTP Error")

            with patch("src.services.cv_extraction_service.generate_content_with_retry", new_callable=AsyncMock) as mock_gen:
                mock_gen_resp = MagicMock()
                mock_gen_resp.text = '{"is_cv": true, "competencies": [], "missions": []}'
                mock_gen.return_value = mock_gen_resp

                # Should not raise, just logs warning
                res, _ = await CVExtractionService.analyze_cv_with_llm("raw text", headers={"Authorization": "Bearer test"}, genai_client=MagicMock())
                assert res.get("is_cv") is True


@pytest.mark.asyncio
async def test_fetch_cv_content_plain_text_success():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Plain Text CV"
        mock_get.return_value = mock_resp

        res = await CVExtractionService.fetch_cv_content("https://example.com/cv.txt", google_token="token", file_type="plain")
        assert res == "Plain Text CV"


@pytest.mark.asyncio
async def test_fetch_cv_content_plain_text_auth_error():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        with pytest.raises(HTTPException) as exc:
            await CVExtractionService.fetch_cv_content("https://example.com/cv.txt", google_token="token", file_type="plain")
        assert exc.value.status_code == 400
        assert "Accès refusé" in exc.value.detail


@pytest.mark.asyncio
async def test_analyze_cv_fetch_prompt_from_api():
    with patch("src.services.cv_extraction_service.get_cache", side_effect=lambda k: "cached_context" if k == "cv_api:tree_context" else None):
        with patch("src.services.cv_extraction_service.set_cache", new_callable=AsyncMock) as mock_set:
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"value": "API Prompt"}
                mock_get.return_value = mock_resp

                with patch("src.services.cv_extraction_service.generate_content_with_retry", new_callable=AsyncMock) as mock_gen:
                    mock_gen_resp = MagicMock()
                    mock_gen_resp.text = '{"is_cv": true, "competencies": [], "missions": []}'
                    mock_gen.return_value = mock_gen_resp

                    await CVExtractionService.analyze_cv_with_llm("raw text", headers={"Authorization": "Bearer test"}, genai_client=MagicMock())

                    mock_set.assert_any_call("cv_api:prompt", "API Prompt", ttl_seconds=3600)


@pytest.mark.asyncio
async def test_analyze_cv_fetch_prompt_file_fallback():
    with patch("src.services.cv_extraction_service.get_cache", side_effect=lambda k: "cached_context" if k == "cv_api:tree_context" else None):
        with patch("src.services.cv_extraction_service.set_cache", new_callable=AsyncMock):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.side_effect = Exception("API Down")

                with patch("os.path.exists", return_value=True):
                    with patch("builtins.open", unittest.mock.mock_open(read_data="File Prompt")):
                        with patch("src.services.cv_extraction_service.generate_content_with_retry", new_callable=AsyncMock) as mock_gen:
                            mock_gen_resp = MagicMock()
                            mock_gen_resp.text = '{"is_cv": true, "competencies": [], "missions": []}'
                            mock_gen.return_value = mock_gen_resp

                            await CVExtractionService.analyze_cv_with_llm("raw text", headers={"Authorization": "Bearer test"}, genai_client=MagicMock())
