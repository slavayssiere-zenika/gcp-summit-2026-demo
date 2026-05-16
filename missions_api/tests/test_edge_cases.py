"""Tests des cas limites non couverts — missions_api.

Sections :
  A. document_extractor.py — URL malformée, DOCX vide, url+file simultanés
  B. crud_router.py — transition invalide, rôle non autorisé, terminal states
  C. crud_router.py — list_missions avec statut invalide (non enum)
  D. gemini_retry.py — comportement sous erreurs
"""
import io
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./missions_edge_test.db")


# ─────────────────────────────────────────────────────────────────────────────
# Section A — document_extractor.py : cas limites non couverts
# ─────────────────────────────────────────────────────────────────────────────

class TestDocumentExtractorEdgeCases:

    @pytest.mark.asyncio
    async def test_url_and_file_both_provided_file_takes_precedence(self):
        """Quand url ET file_bytes sont fournis → le file est traité (pas l'URL)."""
        from src.missions.document_extractor import extract_document_contents
        http_client = AsyncMock()
        # Si file_bytes est non vide, la branche URL ne doit pas être appelée
        file_bytes = b"%PDF-1.4 fake"
        contents, description = await extract_document_contents(
            url="https://example.com/doc",
            file_bytes=file_bytes,
            file_mime="application/pdf",
            description="",
            headers={},
            http_client=http_client,
        )
        # L'URL ne doit pas avoir été fetchée
        http_client.get.assert_not_called()
        # Le fichier doit avoir été traité
        assert len(contents) >= 1

    @pytest.mark.asyncio
    async def test_docx_with_no_text_logs_warning(self):
        """DOCX sans paragraphes de texte → warning logué, pas d'erreur."""
        from src.missions.document_extractor import extract_document_contents
        import docx as python_docx

        # Créer un DOCX vide réel
        doc = python_docx.Document()
        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()

        http_client = AsyncMock()
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        contents, description = await extract_document_contents(
            url="",
            file_bytes=docx_bytes,
            file_mime=mime,
            description="",
            headers={},
            http_client=http_client,
        )
        # DOCX vide → aucun contenu textuel ajouté
        # La fonction ne lève pas d'erreur (juste un warning)
        assert isinstance(contents, list)

    @pytest.mark.asyncio
    async def test_no_url_no_file_only_description(self):
        """Sans URL ni fichier → description utilisée comme contenu texte."""
        from src.missions.document_extractor import extract_document_contents
        http_client = AsyncMock()
        contents, final_desc = await extract_document_contents(
            url="",
            file_bytes=b"",
            file_mime="",
            description="Mission de conseil DevOps",
            headers={},
            http_client=http_client,
        )
        assert any("Mission de conseil DevOps" in str(c) for c in contents)
        assert final_desc == "Mission de conseil DevOps"

    @pytest.mark.asyncio
    async def test_url_fetch_returns_non_200_logs_warning(self):
        """Fetch URL retournant 404 → warning, aucun contenu ajouté."""
        from src.missions.document_extractor import extract_document_contents
        http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        http_client.get.return_value = mock_resp

        contents, _ = await extract_document_contents(
            url="https://example.com/notfound",
            file_bytes=b"",
            file_mime="",
            description="",
            headers={},
            http_client=http_client,
        )
        assert contents == []

    @pytest.mark.asyncio
    async def test_google_docs_url_transformed(self):
        """URL Google Docs → transformée en export ?format=txt."""
        from src.missions.document_extractor import extract_document_contents
        http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Contenu du document"
        http_client.get.return_value = mock_resp

        await extract_document_contents(
            url="https://docs.google.com/document/d/FAKE_DOC_ID/edit",
            file_bytes=b"",
            file_mime="",
            description="",
            headers={},
            http_client=http_client,
        )
        # L'URL appelée doit être l'export txt
        called_url = http_client.get.call_args[0][0]
        assert "export?format=txt" in called_url

    @pytest.mark.asyncio
    async def test_docx_without_python_docx_raises_runtime_error(self):
        """Si python-docx n'est pas installé et DOCX fourni → RuntimeError."""
        from src.missions.document_extractor import extract_document_contents
        http_client = AsyncMock()
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        with patch("src.missions.document_extractor.docx", None):
            with pytest.raises(RuntimeError, match="python-docx"):
                await extract_document_contents(
                    url="",
                    file_bytes=b"fake docx",
                    file_mime=mime,
                    description="",
                    headers={},
                    http_client=http_client,
                )


# ─────────────────────────────────────────────────────────────────────────────
# Section B — crud_router.py : transitions de statut
# ─────────────────────────────────────────────────────────────────────────────

class TestMissionStatusTransitions:

    def _make_client(self, role="admin"):
        from fastapi.testclient import TestClient
        from main import app
        from shared.auth.jwt import verify_jwt
        from shared.database import get_db

        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": f"{role}@zenika.com",
            "role": role,
        }
        app.dependency_overrides[get_db] = lambda: AsyncMock()
        return TestClient(app, raise_server_exceptions=False)

    def test_transition_invalid_role_returns_403(self):
        """Un utilisateur avec rôle 'user' ne peut pas changer le statut → 403."""
        from fastapi.testclient import TestClient
        from main import app
        from shared.auth.jwt import verify_jwt
        from shared.database import get_db

        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "user@zenika.com", "role": "user"
        }

        mock_db = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = 1
        mock_mission.status = "STAFFED"
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_mission
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            "/missions/1/status",
            json={"status": "NO_GO", "reason": "Test"},
            headers={"Authorization": "Bearer fake"},
        )
        app.dependency_overrides.clear()
        assert resp.status_code == 403

    def test_terminal_state_no_transition_returns_422(self):
        """Mission en état terminal (WON, LOST, NO_GO) → aucune transition possible → 422."""
        from fastapi.testclient import TestClient
        from main import app
        from shared.auth.jwt import verify_jwt
        from shared.database import get_db
        from src.missions.models import MissionStatus

        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "admin@zenika.com", "role": "admin"
        }

        mock_db = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = 1
        mock_mission.status = MissionStatus.WON  # État terminal
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_mission
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            "/missions/1/status",
            json={"status": "STAFFED", "reason": "Retour arrière"},
            headers={"Authorization": "Bearer fake"},
        )
        app.dependency_overrides.clear()
        # WON → STAFFED est une transition invalide → 422
        assert resp.status_code == 422

    def test_list_missions_invalid_status_filter(self):
        """list_missions avec un statut invalide (non-enum) → 200 avec liste vide."""
        from fastapi.testclient import TestClient
        from main import app
        from shared.auth.jwt import verify_jwt
        from shared.database import get_db

        app.dependency_overrides[verify_jwt] = lambda: {
            "sub": "u@zenika.com", "role": "user"
        }

        mock_db = AsyncMock()
        mock_scalar = MagicMock()
        mock_scalar.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(return_value=mock_scalar)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/missions?status=INVALID_STATUS",
            headers={"Authorization": "Bearer fake"},
        )
        app.dependency_overrides.clear()
        # L'API filtre par le texte tel quel — 200 avec 0 résultats
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Section C — gemini_retry.py : comportement sous erreurs
# ─────────────────────────────────────────────────────────────────────────────

class TestGeminiRetryEdgeCases:

    def test_gemini_retry_module_importable(self):
        """gemini_retry.py est importable et expose les fonctions attendues."""
        from src.gemini_retry import generate_content_with_retry, embed_content_with_retry
        assert callable(generate_content_with_retry)
        assert callable(embed_content_with_retry)

    @pytest.mark.asyncio
    async def test_generate_content_with_retry_success(self):
        """generate_content_with_retry réussit au 1er appel → retourne le résultat."""
        from src.gemini_retry import generate_content_with_retry

        mock_response = MagicMock()
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await generate_content_with_retry(mock_client, model="gemini-flash", contents="test")
        assert result is mock_response
        assert mock_client.aio.models.generate_content.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_content_non_retryable_error_raises_immediately(self):
        """Erreur non-retryable (ex: ValueError) → propagée immédiatement sans retry."""
        from src.gemini_retry import generate_content_with_retry

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=ValueError("Argument invalide")
        )

        with pytest.raises(ValueError, match="Argument invalide"):
            await generate_content_with_retry(mock_client, model="gemini-flash", contents="test")

        # ValueError n'est pas retryable → 1 seul appel
        assert mock_client.aio.models.generate_content.call_count == 1

    def test_is_retryable_detects_429_text(self):
        """_is_retryable détecte les erreurs 429 par le texte de l'exception."""
        from src.gemini_retry import _is_retryable
        exc_429 = Exception("429 Resource Exhausted — high traffic")
        assert _is_retryable(exc_429) is True

    def test_is_retryable_detects_503_text(self):
        """_is_retryable détecte les erreurs 503 par le texte."""
        from src.gemini_retry import _is_retryable
        exc_503 = Exception("503 Service Unavailable")
        assert _is_retryable(exc_503) is True

    def test_is_retryable_returns_false_for_normal_errors(self):
        """_is_retryable retourne False pour les erreurs normales."""
        from src.gemini_retry import _is_retryable
        assert _is_retryable(ValueError("bad input")) is False
        assert _is_retryable(RuntimeError("logic error")) is False
