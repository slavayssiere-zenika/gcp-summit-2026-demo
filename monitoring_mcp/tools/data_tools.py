"""
tools/data_tools.py — Data layer tools (Redis, PostgreSQL/AlloyDB, Pub/Sub DLQ).

Tools exposés :
  - get_redis_invalidation_state_internal(pattern)
  - execute_read_only_query_internal(query, db_name)
  - inspect_pubsub_dlq_internal(subscription_id, limit)
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


async def get_redis_invalidation_state_internal(pattern: str = "*") -> dict:
    """Inspecte les clés Redis correspondant au pattern donné (SCAN sans destructivité).

    Args:
        pattern: Pattern SCAN Redis (ex: 'items:list:*', 'session:*', '*').

    Returns:
        Dict {status, matched_keys_count, keys_sample, redis_url}.
    """
    try:
        import redis

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(redis_url, socket_timeout=2.0)

        keys = []
        cursor = "0"
        while cursor != 0:
            cursor, data = r.scan(cursor=cursor, match=pattern, count=100)
            keys.extend([k.decode("utf-8") for k in data])
            if len(keys) >= 100:
                break

        sample = {k: r.ttl(k) for k in keys[:20]}

        return {
            "status": "ok",
            "matched_keys_count": len(keys),
            "keys_sample": sample,
            "redis_url": redis_url,
        }
    except Exception as e:
        logger.exception(f"Error checking Redis state: {e}")
        return {"error": str(e)}


async def execute_read_only_query_internal(query: str, db_name: str = "zenika") -> dict:
    """Exécute une requête SQL SELECT (lecture seule) sur AlloyDB/PostgreSQL.

    Rejette les requêtes DDL/DML (INSERT, UPDATE, DELETE, DROP...) avant exécution.

    Args:
        query: Requête SQL SELECT à exécuter.
        db_name: Nom de la base de données cible.

    Returns:
        Dict {status, rows, count} ou {error}.
    """
    query_lower = query.lower().strip()
    forbidden_keywords = ["insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke"]
    if any(kw in query_lower for kw in forbidden_keywords):
        return {"error": "Only read-only SELECT queries are allowed."}

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        db_url = os.getenv("DATABASE_URL", f"postgresql+asyncpg://postgres:postgres@alloydb:5432/{db_name}")
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            result = await conn.execute(text(query))
            rows = result.mappings().all()
            formatted_rows = [
                {k: str(v) if isinstance(v, datetime) else (str(v) if v is not None else None) for k, v in row.items()}
                for row in rows
            ]

        await engine.dispose()
        return {"status": "ok", "rows": formatted_rows, "count": len(formatted_rows)}
    except Exception as e:
        logger.exception(f"Error executing DB query: {e}")
        return {"error": str(e)}


async def inspect_pubsub_dlq_internal(subscription_id: str = "cv-ingestion-dlq-sub", limit: int = 10) -> dict:
    """Lit les messages de la Dead Letter Queue Pub/Sub en mode lecture seule (sans ack).

    Args:
        subscription_id: ID de la souscription DLQ Pub/Sub.
        limit: Nombre maximum de messages à lire.

    Returns:
        Dict {status, messages, count} ou {error}.
    """
    try:
        from google.cloud import pubsub_v1

        project_id = os.getenv("GCP_PROJECT_ID", "")
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(project_id, subscription_id)

        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": limit},
            timeout=10.0,
        )

        messages = [
            {
                "message_id": rm.message.message_id,
                "publish_time": rm.message.publish_time.isoformat() if rm.message.publish_time else None,
                "attributes": dict(rm.message.attributes),
                "data": rm.message.data.decode("utf-8") if rm.message.data else None,
            }
            for rm in response.received_messages
        ]

        return {"status": "ok", "messages": messages, "count": len(messages)}
    except Exception as e:
        logger.exception(f"Error inspecting DLQ {subscription_id}: {e}")
        return {"error": str(e), "subscription": subscription_id}
