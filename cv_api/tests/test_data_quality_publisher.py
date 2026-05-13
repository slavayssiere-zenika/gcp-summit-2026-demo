"""
test_data_quality_publisher.py — Tests unitaires du publisher de snapshots DQ.

Couvre :
  - Publication réussie avec db fourni
  - Publication réussie avec db=None (ouvre sa propre session)
  - Gestion d'erreur Pub/Sub (publie l'erreur sans lever d'exception)
  - Gestion topic non configuré (DATA_QUALITY_PUBSUB_TOPIC absent)
  - Payload conforme au schéma BQ (tous les champs requis présents)
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_REPORT = {
    "computed_at": "2026-05-06T10:00:00+00:00",
    "total_cvs": 42,
    "users_with_cv": 38,
    "score": 87,
    "grade": "A",
    "metrics": {
        "embedding":              {"pct": 95, "ok": 40, "total": 42, "status": "ok"},
        "missions":               {"pct": 90, "ok": 38, "total": 42, "status": "ok"},
        "competencies":           {"pct": 88, "ok": 37, "total": 42, "status": "ok"},
        "summary":                {"pct": 85, "ok": 36, "total": 42, "status": "ok"},
        "current_role":           {"pct": 80, "ok": 34, "total": 42, "status": "ok"},
        "competency_assignment":  {"pct": 92, "ok": 35, "total": 38, "status": "ok"},
        "ai_scoring":             {"pct": 84, "ok": 32, "total": 38, "status": "ok"},
        "processing_errors":      {"pct": 100, "ok": 42, "total": 42, "status": "ok"},
    },
    "issues": [],
    "recommendation": "Tous les indicateurs sont dans les seuils nominaux.",
    "rag": {
        "recall_at_5": 0.85,
        "nb_cases": 10,
        "nb_cases_ok": 8,
        "embedding_model": "text-embedding-004",
    },
}

EXPECTED_PAYLOAD_KEYS = {
    "computed_at", "total_cvs", "users_with_cv", "score", "grade",
    "embedding_pct", "missions_pct", "competencies_pct", "summary_pct",
    "current_role_pct", "competency_assignment_pct", "ai_scoring_pct",
    "processing_errors_pct", "issues_count", "trigger",
    # Champs RAG ajoutés lors du feature R6 (rag_quality dans data_quality_publisher)
    "rag_recall_at_5", "rag_nb_cases", "rag_nb_cases_ok", "rag_embedding_model",
}


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_success_with_db():
    """Publication réussie quand une session DB est fournie."""
    mock_db = AsyncMock()
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-id-abc"

    with patch.dict("os.environ", {"DATA_QUALITY_PUBSUB_TOPIC": "projects/p/topics/dq"}), \
         patch("src.services.data_quality_publisher.compute_data_quality_report",
               new_callable=AsyncMock, return_value=SAMPLE_REPORT) as mock_compute, \
         patch("src.services.data_quality_publisher.pubsub_v1.PublisherClient") as mock_client_cls:

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.publish.return_value = mock_future

        from src.services.data_quality_publisher import publish_data_quality_snapshot
        result = await publish_data_quality_snapshot(mock_db, "Bearer tok", "scheduler")

    assert result["success"] is True
    assert result["message_id"] == "msg-id-abc"
    assert result["score"] == 87
    mock_compute.assert_awaited_once_with(mock_db, "Bearer tok")

    # Vérifier le payload publié
    call_args = mock_client.publish.call_args
    topic_arg = call_args[0][0]
    data_arg = json.loads(call_args[0][1].decode())
    assert topic_arg == "projects/p/topics/dq"
    assert data_arg["trigger"] == "scheduler"
    assert data_arg["grade"] == "A"
    assert EXPECTED_PAYLOAD_KEYS == set(data_arg.keys())
    # computed_at doit être un entier (microsecondes Unix) pour Avro timestamp-micros
    assert isinstance(data_arg["computed_at"], int)
    assert data_arg["computed_at"] > 1_700_000_000_000_000  # après 2023-11-14


@pytest.mark.asyncio
async def test_publish_success_with_db_none():
    """db=None doit ouvrir sa propre session DB via SessionLocal."""
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-id-xyz"

    mock_own_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_own_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_db_module = MagicMock()
    mock_db_module.SessionLocal.return_value = mock_session_ctx

    with patch.dict("os.environ", {"DATA_QUALITY_PUBSUB_TOPIC": "projects/p/topics/dq"}), \
         patch("src.services.data_quality_publisher.compute_data_quality_report",
               new_callable=AsyncMock, return_value=SAMPLE_REPORT) as mock_compute, \
         patch("src.services.data_quality_publisher.pubsub_v1.PublisherClient") as mock_client_cls, \
         patch.dict("sys.modules", {"database": mock_db_module}):

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.publish.return_value = mock_future

        from src.services.data_quality_publisher import publish_data_quality_snapshot
        result = await publish_data_quality_snapshot(None, "Bearer tok", "batch_completed")

    assert result["success"] is True
    assert result["message_id"] == "msg-id-xyz"
    # Vérifie que le report a été calculé avec la session ouverte (own_db)
    mock_compute.assert_awaited_once_with(mock_own_db, "Bearer tok")


@pytest.mark.asyncio
async def test_publish_topic_not_configured():
    """Retourne une erreur sans lever d'exception si le topic n'est pas configuré."""
    with patch.dict("os.environ", {}, clear=True):
        # Supprimer la variable si elle existe
        import os
        os.environ.pop("DATA_QUALITY_PUBSUB_TOPIC", None)

        from src.services.data_quality_publisher import publish_data_quality_snapshot
        result = await publish_data_quality_snapshot(AsyncMock(), "Bearer tok", "manual")

    assert result["success"] is False
    assert "not configured" in result["error"]


@pytest.mark.asyncio
async def test_publish_pubsub_error_does_not_raise():
    """Une erreur Pub/Sub est loguée mais ne propage pas d'exception (non-bloquant)."""
    mock_future = MagicMock()
    mock_future.result.side_effect = Exception("Pub/Sub unavailable")

    with patch.dict("os.environ", {"DATA_QUALITY_PUBSUB_TOPIC": "projects/p/topics/dq"}), \
         patch("src.services.data_quality_publisher.compute_data_quality_report",
               new_callable=AsyncMock, return_value=SAMPLE_REPORT), \
         patch("src.services.data_quality_publisher.pubsub_v1.PublisherClient") as mock_client_cls:

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.publish.return_value = mock_future

        from src.services.data_quality_publisher import publish_data_quality_snapshot
        result = await publish_data_quality_snapshot(AsyncMock(), "Bearer tok")

    assert result["success"] is False
    assert "Pub/Sub unavailable" in result["error"]


@pytest.mark.asyncio
async def test_publish_compute_error_does_not_raise():
    """Une erreur dans compute_data_quality_report est gérée gracieusement."""
    with patch.dict("os.environ", {"DATA_QUALITY_PUBSUB_TOPIC": "projects/p/topics/dq"}), \
         patch("src.services.data_quality_publisher.compute_data_quality_report",
               new_callable=AsyncMock, side_effect=Exception("DB unavailable")):

        from src.services.data_quality_publisher import publish_data_quality_snapshot
        result = await publish_data_quality_snapshot(AsyncMock(), "Bearer tok")

    assert result["success"] is False
    assert "DB unavailable" in result["error"]


@pytest.mark.asyncio
async def test_payload_triggers_propagated():
    """Vérifie que le champ 'trigger' est correctement transmis dans le payload Pub/Sub."""
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-id-trigger"

    with patch.dict("os.environ", {"DATA_QUALITY_PUBSUB_TOPIC": "projects/p/topics/dq"}), \
         patch("src.services.data_quality_publisher.compute_data_quality_report",
               new_callable=AsyncMock, return_value=SAMPLE_REPORT), \
         patch("src.services.data_quality_publisher.pubsub_v1.PublisherClient") as mock_client_cls:

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.publish.return_value = mock_future

        from src.services.data_quality_publisher import publish_data_quality_snapshot

        for trigger in ("scheduler", "batch_completed", "manual"):
            await publish_data_quality_snapshot(AsyncMock(), "Bearer tok", trigger)
            call_args = mock_client.publish.call_args
            data = json.loads(call_args[0][1].decode())
            assert data["trigger"] == trigger, f"Trigger '{trigger}' non transmis dans le payload"
