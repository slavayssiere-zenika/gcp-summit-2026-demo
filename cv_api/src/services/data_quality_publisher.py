"""
data_quality_publisher.py — Publie un snapshot de data quality dans Pub/Sub → BigQuery.

Responsabilités :
  - Calculer le rapport DQ via compute_data_quality_report (service existant)
  - Sérialiser le snapshot au format attendu par la table BQ data_quality_history
  - Publier le message dans le topic Pub/Sub configuré par DATA_QUALITY_PUBSUB_TOPIC

Ce module est appelé :
  1. Par l'endpoint /pubsub/data-quality-snapshot (Cloud Scheduler, toutes les 4h)
  2. Par taxonomy_batch_service.py (post-batch, state=COMPLETED)

Non-bloquant : les erreurs Pub/Sub sont loguées sans propager d'exception.
"""
import json
import logging
import os
from datetime import datetime, timezone

from google.cloud import pubsub_v1

from src.services.data_quality_service import compute_data_quality_report

logger = logging.getLogger(__name__)

DATA_QUALITY_PUBSUB_TOPIC_ENV = "DATA_QUALITY_PUBSUB_TOPIC"


async def publish_data_quality_snapshot(
    db,
    auth_header: str,
    trigger: str = "scheduler",
) -> dict:
    """Calcule le rapport DQ et publie un snapshot dans Pub/Sub → BigQuery.

    Le message publié correspond exactement au schéma de la table BQ
    `finops_{env}.data_quality_history` (BigQuery Subscription native).

    Args:
        db: Session SQLAlchemy async injectée par FastAPI, ou None (ouvre sa propre session).
            Passer None lorsque appelé depuis un asyncio.Task hors contexte HTTP (ex: post-batch).
        auth_header: Header 'Authorization: Bearer <token>' pour les appels HTTP sortants.
        trigger: Source du déclenchement ('scheduler' | 'batch_completed' | 'manual').

    Returns:
        dict avec success, message_id (si succès) ou error (si échec).
    """
    topic_name = os.getenv(DATA_QUALITY_PUBSUB_TOPIC_ENV, "")
    if not topic_name:
        logger.warning(
            "[dq-publisher] %s non configuré — snapshot ignoré.",
            DATA_QUALITY_PUBSUB_TOPIC_ENV,
        )
        return {"success": False, "error": f"{DATA_QUALITY_PUBSUB_TOPIC_ENV} not configured"}

    try:
        if db is None:
            # Appelé depuis un asyncio.Task (ex: post-batch) sans session HTTP FastAPI.
            # On ouvre notre propre session DB pour les requêtes SQL.
            import database as _db_module  # Import tardif : évite circular import au toplevel
            async with _db_module.SessionLocal() as own_db:
                report = await compute_data_quality_report(own_db, auth_header)
        else:
            report = await compute_data_quality_report(db, auth_header)
    except Exception as exc:
        logger.error("[dq-publisher] Échec calcul data quality report: %s", exc)
        return {"success": False, "error": f"compute_data_quality_report failed: {exc}"}

    # Conversion computed_at ISO8601 → microsecondes Unix (requis par Avro timestamp-micros).
    # En encodage JSON Avro, logicalType timestamp-micros = integer (µs depuis epoch Unix).
    computed_at_str = report["computed_at"]
    try:
        dt = datetime.fromisoformat(computed_at_str)
    except ValueError:
        dt = datetime.now(timezone.utc)
    computed_at_micros = int(dt.timestamp() * 1_000_000)

    payload = {
        "computed_at": computed_at_micros,
        "total_cvs": report["total_cvs"],
        "users_with_cv": report["users_with_cv"],
        "score": report["score"],
        "grade": report["grade"],
        # Stockés en proportion (0.0 → 1.0) — division par 100 avant injection BQ
        "embedding_pct": round(report["metrics"]["embedding"]["pct"] / 100, 4),
        "missions_pct": round(report["metrics"]["missions"]["pct"] / 100, 4),
        "competencies_pct": round(report["metrics"]["competencies"]["pct"] / 100, 4),
        "summary_pct": round(report["metrics"]["summary"]["pct"] / 100, 4),
        "current_role_pct": round(report["metrics"]["current_role"]["pct"] / 100, 4),
        "competency_assignment_pct": round(report["metrics"]["competency_assignment"]["pct"] / 100, 4),
        "ai_scoring_pct": round(report["metrics"]["ai_scoring"]["pct"] / 100, 4),
        "issues_count": len(report["issues"]),
        "trigger": trigger,
    }

    try:
        publisher = pubsub_v1.PublisherClient()
        data = json.dumps(payload).encode("utf-8")
        future = publisher.publish(topic_name, data)
        message_id = future.result(timeout=10)
        logger.info(
            "[dq-publisher] Snapshot publié (message_id=%s, score=%d, grade=%s, trigger=%s).",
            message_id, payload["score"], payload["grade"], trigger,
        )
        return {"success": True, "message_id": message_id, "score": payload["score"]}
    except Exception as exc:
        logger.error("[dq-publisher] Échec publication Pub/Sub topic=%s: %s", topic_name, exc)
        return {"success": False, "error": str(exc)}
