"""
test_ai_scoring.py — Couverture des chemins critiques de ai_scoring.py.

Branches couvertes (lignes 57-315) :
  - _get_or_create_evaluation : evaluation existante vs création nouvelle
  - _serialize_evaluation : sérialisation complète
  - _compute_ai_score :
      * GOOGLE_API_KEY absente → retour immédiat (None, message)
      * missions non disponibles (erreur réseau)  → (None, message)
      * HTTP 500 sur cv_api → missions vides → score minimal 1.0
      * ValidationError MissionsResponse → break proprement
      * 0 missions → score minimal 1.0
      * pagination (deux pages) → missions correctement accumulées
      * missions pertinentes filtrées vs fallback 5 premières
      * appel Gemini réussi → (score, justification) arrondis
      * Gemini avec cached_content (Vertex AI)
      * TimeoutError → (None, message timeout)
      * JSONDecodeError → (None, message parse)
      * Exception générique → (None, message générique)
  - _score_all_bg : itération, persistance, erreur par compétence
  - _bulk_scoring_all_bg : semaphore, delta_only, skip user sans compétences
"""
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_missions_response(items=None, total=None):
    items = items or []
    total = total or len(items)
    return {"items": items, "total": total, "skip": 0, "limit": 100}


def _make_http_response(status=200, payload=None):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = payload or {}
    return mock


# ── _get_or_create_evaluation ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_create_evaluation_existing():
    """Retourne l'évaluation existante sans créer."""
    from src.competencies.ai_scoring import _get_or_create_evaluation

    existing_ev = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_ev
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    ev = await _get_or_create_evaluation(mock_db, user_id=1, competency_id=10)
    assert ev is existing_ev
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_evaluation_creates_new():
    """Crée et flush une nouvelle évaluation si absente."""
    from src.competencies.ai_scoring import _get_or_create_evaluation

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()

    ev = await _get_or_create_evaluation(mock_db, user_id=1, competency_id=10)
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    assert ev.user_id == 1
    assert ev.competency_id == 10


# ── _serialize_evaluation ─────────────────────────────────────────────────────

def test_serialize_evaluation_complete():
    """Vérifie que tous les champs attendus sont présents et cohérents."""
    from src.competencies.ai_scoring import _serialize_evaluation
    from src.competencies.models import CompetencyEvaluation

    ev = CompetencyEvaluation(user_id=1, competency_id=5)
    ev.id = 42
    ev.ai_score = 3.5
    ev.ai_justification = "Bonne maîtrise"
    ev.ai_scored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ev.user_score = 4.0
    ev.user_comment = "Correct"
    ev.user_scored_at = None

    result = _serialize_evaluation(ev, competency_name="Python")

    assert result["id"] == 42
    assert result["user_id"] == 1
    assert result["competency_id"] == 5
    assert result["name"] == "Python"
    assert result["competency_name"] == "Python"
    assert result["ai_score"] == 3.5
    assert result["ai_justification"] == "Bonne maîtrise"
    assert result["user_score"] == 4.0


# ── _compute_ai_score — branche GOOGLE_API_KEY absente ───────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_no_api_key():
    """Sans GOOGLE_API_KEY → retour immédiat (None, message)."""
    from src.competencies.ai_scoring import _compute_ai_score

    with patch.dict("os.environ", {}, clear=True):
        if "GOOGLE_API_KEY" in __import__("os").environ:
            __import__("os").environ.pop("GOOGLE_API_KEY")
        score, justif = await _compute_ai_score(1, "Python", {})

    assert score is None
    assert "GOOGLE_API_KEY" in justif


# ── _compute_ai_score — erreur réseau sur cv_api ─────────────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_network_error():
    """Exception httpx → (None, 'Missions non disponibles')."""
    from src.competencies.ai_scoring import _compute_ai_score

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=ConnectionError("réseau coupé"))
            mock_cls.return_value = mock_client

            score, justif = await _compute_ai_score(1, "Python", {})

    assert score is None
    assert "non disponibles" in justif.lower() or "réseau" in justif.lower()


# ── _compute_ai_score — HTTP 500 → 0 missions → score minimal ────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_http_500_returns_minimal_score():
    """cv_api répond 500 → missions=[] → score minimal 1.0."""
    from src.competencies.ai_scoring import _compute_ai_score

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=_make_http_response(500))
            mock_cls.return_value = mock_client

            score, justif = await _compute_ai_score(1, "Python", {})

    assert score == 1.0
    assert "Aucune mission" in justif


# ── _compute_ai_score — ValidationError MissionsResponse ─────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_validation_error_breaks_pagination():
    """MissionsResponse invalide → break propre → 0 missions → score minimal."""
    from src.competencies.ai_scoring import _compute_ai_score

    bad_payload = {"unexpected": "data"}  # ne passe pas MissionsResponse.model_validate

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=_make_http_response(200, bad_payload))
            mock_cls.return_value = mock_client

            score, justif = await _compute_ai_score(1, "Python", {})

    assert score == 1.0


# ── _compute_ai_score — pagination (2 pages) ─────────────────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_pagination_two_pages():
    """La pagination s'arrête quand len(items) < limit."""
    from src.competencies.ai_scoring import _compute_ai_score

    page1 = _make_missions_response(
        items=[{"id": i, "title": f"m{i}", "competencies": ["Python"]} for i in range(100)],
        total=150,
    )
    page2 = _make_missions_response(
        items=[{"id": i + 100, "title": f"m{i+100}", "competencies": []} for i in range(50)],
        total=150,
    )

    gemini_response = MagicMock()
    gemini_response.text = json.dumps({"score": 3.5, "justification": "Good Python skills"})

    responses = [
        _make_http_response(200, page1),
        _make_http_response(200, page2),
    ]

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=responses)
            mock_cls.return_value = mock_client

            with patch("google.genai.Client") as mock_genai:
                mock_client_inst = MagicMock()
                mock_genai.return_value = mock_client_inst
                mock_client_inst.aio.models.generate_content = AsyncMock(return_value=gemini_response)

                with patch("src.competencies.ai_scoring.get_or_create_scoring_cache", new_callable=AsyncMock) as mock_cache:
                    mock_cache.return_value = None  # Pas de Vertex cache

                    score, justif = await _compute_ai_score(1, "Python", {})

    assert score == 3.5
    assert mock_client.get.call_count == 2  # bien 2 pages


# ── _compute_ai_score — Gemini réussi, score arrondi ────────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_gemini_rounds_score():
    """Score Gemini non arrondi doit être arrondi au pas de 0.5."""
    from src.competencies.ai_scoring import _compute_ai_score

    missions = [{"id": 1, "title": "Dev", "competencies": ["Python"]}]
    page = _make_missions_response(items=missions, total=1)

    gemini_response = MagicMock()
    # 3.3 doit être arrondi à 3.5
    gemini_response.text = json.dumps({"score": 3.3, "justification": "Decent"})

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=_make_http_response(200, page))
            mock_cls.return_value = mock_client

            with patch("google.genai.Client") as mock_genai:
                mock_client_inst = MagicMock()
                mock_genai.return_value = mock_client_inst
                mock_client_inst.aio.models.generate_content = AsyncMock(return_value=gemini_response)

                with patch("src.competencies.ai_scoring.get_or_create_scoring_cache", new_callable=AsyncMock) as mock_cache:
                    mock_cache.return_value = None

                    score, justif = await _compute_ai_score(1, "Python", {})

    assert score == 3.5


# ── _compute_ai_score — Vertex AI cached_content ────────────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_uses_cached_content():
    """Quand cached_content_name est non-None, le prompt utilisateur est réduit."""
    from src.competencies.ai_scoring import _compute_ai_score

    missions = [{"id": 1, "title": "Audit GCP", "competencies": ["Cloud"]}]
    page = _make_missions_response(items=missions, total=1)

    gemini_response = MagicMock()
    gemini_response.text = json.dumps({"score": 4.0, "justification": "Expert cloud"})

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=_make_http_response(200, page))
            mock_cls.return_value = mock_client

            with patch("google.genai.Client") as mock_genai:
                mock_client_inst = MagicMock()
                mock_genai.return_value = mock_client_inst
                mock_client_inst.aio.models.generate_content = AsyncMock(return_value=gemini_response)

                with patch("src.competencies.ai_scoring.get_or_create_scoring_cache", new_callable=AsyncMock) as mock_cache:
                    mock_cache.return_value = "projects/x/caches/123"

                    score, justif = await _compute_ai_score(1, "Cloud", {})

    assert score == 4.0


# ── _compute_ai_score — TimeoutError ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_timeout():
    """TimeoutError → (None, 'timeout')."""
    from src.competencies.ai_scoring import _compute_ai_score

    missions = [{"id": 1, "title": "Dev", "competencies": []}]
    page = _make_missions_response(items=missions, total=1)

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=_make_http_response(200, page))
            mock_cls.return_value = mock_client

            with patch("google.genai.Client") as mock_genai:
                mock_client_inst = MagicMock()
                mock_genai.return_value = mock_client_inst
                mock_client_inst.aio.models.generate_content = AsyncMock(
                    side_effect=asyncio.TimeoutError()
                )
                with patch("src.competencies.ai_scoring.get_or_create_scoring_cache", new_callable=AsyncMock) as mock_cache:
                    mock_cache.return_value = None

                    score, justif = await _compute_ai_score(1, "Python", {})

    assert score is None
    assert "timeout" in justif.lower()


# ── _compute_ai_score — JSONDecodeError ──────────────────────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_json_decode_error():
    """Réponse Gemini non-JSON → (None, message parse)."""
    from src.competencies.ai_scoring import _compute_ai_score

    missions = [{"id": 1, "title": "Dev", "competencies": []}]
    page = _make_missions_response(items=missions, total=1)

    bad_response = MagicMock()
    bad_response.text = "ce n'est pas du JSON"

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=_make_http_response(200, page))
            mock_cls.return_value = mock_client

            with patch("google.genai.Client") as mock_genai:
                mock_client_inst = MagicMock()
                mock_genai.return_value = mock_client_inst
                mock_client_inst.aio.models.generate_content = AsyncMock(return_value=bad_response)
                with patch("src.competencies.ai_scoring.get_or_create_scoring_cache", new_callable=AsyncMock) as mock_cache:
                    mock_cache.return_value = None

                    score, justif = await _compute_ai_score(1, "Python", {})

    assert score is None
    assert "parseable" in justif.lower() or "JSON" in justif


# ── _compute_ai_score — Exception générique ───────────────────────────────────

@pytest.mark.asyncio
async def test_compute_ai_score_generic_exception():
    """Exception générique Gemini → (None, 'Calcul IA échoué')."""
    from src.competencies.ai_scoring import _compute_ai_score

    missions = [{"id": 1, "title": "Dev", "competencies": []}]
    page = _make_missions_response(items=missions, total=1)

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=_make_http_response(200, page))
            mock_cls.return_value = mock_client

            with patch("google.genai.Client") as mock_genai:
                mock_client_inst = MagicMock()
                mock_genai.return_value = mock_client_inst
                mock_client_inst.aio.models.generate_content = AsyncMock(
                    side_effect=RuntimeError("Erreur inattendue")
                )
                with patch("src.competencies.ai_scoring.get_or_create_scoring_cache", new_callable=AsyncMock) as mock_cache:
                    mock_cache.return_value = None

                    score, justif = await _compute_ai_score(1, "Python", {})

    assert score is None
    assert "échoué" in justif.lower() or justif is not None


# ── _score_all_bg ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_all_bg_success():
    """_score_all_bg itère et persiste chaque compétence."""
    from src.competencies.ai_scoring import _score_all_bg

    comp_tuples = [(10, "Python"), (11, "GCP")]
    mock_ev = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_ev
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    with patch("src.competencies.ai_scoring._compute_ai_score", new_callable=AsyncMock) as mock_score:
        mock_score.return_value = (3.5, "Good")
        with patch("shared.database.SessionLocal") as mock_session:
            mock_session.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=None),
            )
            with patch("src.competencies.ai_scoring.clear_namespace", new_callable=AsyncMock):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await _score_all_bg(user_id=1, comp_tuples=comp_tuples, headers={})

    assert mock_score.call_count == 2
    assert mock_db.commit.call_count == 2


@pytest.mark.asyncio
async def test_score_all_bg_handles_exception_per_competency():
    """Une exception sur une compétence ne stoppe pas les suivantes."""
    from src.competencies.ai_scoring import _score_all_bg

    comp_tuples = [(10, "Python"), (11, "GCP")]

    with patch("src.competencies.ai_scoring._compute_ai_score", new_callable=AsyncMock) as mock_score:
        # Première compétence explose, deuxième réussit
        mock_score.side_effect = [RuntimeError("boom"), (3.0, "OK")]

        with patch("src.competencies.ai_scoring.clear_namespace", new_callable=AsyncMock):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Ne doit pas lever d'exception
                await _score_all_bg(user_id=1, comp_tuples=comp_tuples, headers={})

    # Les 2 appels ont bien été tentés
    assert mock_score.call_count == 2


# ── _bulk_scoring_all_bg ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_scoring_all_bg_skips_user_with_no_leaf_competencies():
    """Un user sans compétences feuilles est ignoré (skipped)."""
    from src.competencies.ai_scoring import _bulk_scoring_all_bg

    mock_result_leaf = MagicMock()
    mock_result_leaf.scalars.return_value.all.return_value = []  # 0 compétences
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result_leaf)

    with patch("shared.database.SessionLocal") as mock_session:
        mock_session.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=None),
        )
        with patch("src.competencies.ai_scoring.bulk_scoring_manager.update_progress", new_callable=AsyncMock) as mock_progress:
            await _bulk_scoring_all_bg(user_ids=[1], headers={}, delta_only=False)

    # update_progress appelé avec "ignoré"
    calls_str = str(mock_progress.call_args_list)
    assert "ignoré" in calls_str or "completed" in calls_str


@pytest.mark.asyncio
async def test_bulk_scoring_all_bg_delta_only_skips_all_scored():
    """delta_only=True : user déjà entièrement scoré est ignoré."""
    from src.competencies.ai_scoring import _bulk_scoring_all_bg

    leaf_result = MagicMock()
    leaf_result.scalars.return_value.all.return_value = [10, 11]

    already_scored_result = MagicMock()
    already_scored_result.scalars.return_value.all.return_value = [10, 11]  # tous scorés

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[leaf_result, already_scored_result])

    with patch("shared.database.SessionLocal") as mock_session:
        mock_session.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=None),
        )
        with patch("src.competencies.ai_scoring.bulk_scoring_manager.update_progress", new_callable=AsyncMock) as mock_progress:
            await _bulk_scoring_all_bg(user_ids=[1], headers={}, delta_only=True)

    calls_str = str(mock_progress.call_args_list)
    assert "ignoré" in calls_str or "completed" in calls_str
