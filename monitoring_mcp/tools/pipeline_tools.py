"""
tools/pipeline_tools.py — Health checks et pipeline d'ingestion.

Tools exposés :
  - check_component_health_internal(component_name)
  - check_all_components_health_internal()
  - get_ingestion_pipeline_status_internal()
"""

import asyncio
import logging
import os

import httpx
from opentelemetry.propagate import inject

from context import mcp_auth_header_var

logger = logging.getLogger(__name__)

# Mapping composant → chemin ILB interne
_COMPONENT_PATH_MAP = {
    "users": "/api/users/",
    "items": "/api/items/",
    "prompts": "/api/prompts/",
    "analytics": "/api/analytics/",
    "monitoring": "/monitoring-mcp/",
    "cv": "/api/cv/",
    "missions": "/api/missions/",
    "competencies": "/api/competencies/",
    "drive": "/api/drive/",
    "agent-hr": "/api/agent-hr/",
    "agent-ops": "/api/agent-ops/",
    "router": "/api/",
    "auth": "/auth/",
}

ZENIKA_STATIC_SERVICES = [
    "users-api",
    "items-api",
    "competencies-api",
    "cv-api",
    "missions-api",
    "prompts-api",
    "drive-api",
    "agent-hr-api",
    "agent-ops-api",
    "agent-missions-api",
    "analytics-mcp",
    "monitoring-mcp",
    "agent-router-api",
]


async def check_component_health_internal(component_name: str) -> dict:
    """Vérifie l'état de santé d'un composant de la plateforme.

    Logique par ordre de priorité :
    1. Redis — PING via redis-py
    2. BigQuery / AlloyDB — appel API GCP
    3. Service Cloud Run — GET /health via ILB interne

    Args:
        component_name: Nom du composant (ex: 'users-api', 'redis-cache', 'alloydb').

    Returns:
        Dict {status: healthy|unhealthy|degraded|unreachable|not_found, component, ...}.
    """
    try:
        # 1. Redis Check
        if "redis" in component_name.lower():
            import redis as redis_lib
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            try:
                r = redis_lib.from_url(redis_url, socket_timeout=2.0)
                if r.ping():
                    return {"status": "healthy", "component": component_name, "message": "Redis PING successful"}
            except Exception as re:
                return {"status": "unhealthy", "component": component_name, "error": str(re)}

        # 2. BigQuery / AlloyDB Check
        if any(k in component_name.lower() for k in ["bigquery", "alloydb"]):
            try:
                from google.cloud import bigquery
                project_id = os.getenv("GCP_PROJECT_ID", "")
                bq_client = bigquery.Client(project=project_id)
                bq_client.list_datasets(max_results=1)
                return {"status": "healthy", "component": component_name, "message": "GCP Data APIs are responsive"}
            except Exception as be:
                return {"status": "degraded", "component": component_name, "error": str(be)}

        # 3. Cloud Run via ILB
        target_path = next(
            (path for key, path in _COMPONENT_PATH_MAP.items() if key in component_name.lower()),
            None,
        )
        if target_path:
            url = f"http://api.internal.zenika{target_path}health"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.get(url)
                    if res.status_code == 200:
                        return {"status": "healthy", "component": component_name, "url": url, "code": 200}
                    else:
                        return {"status": "unhealthy", "component": component_name, "url": url, "code": res.status_code, "detail": res.text[:200]}
            except Exception as he:
                return {"status": "unreachable", "component": component_name, "url": url, "error": str(he)}

        # 4. Fallback GCP discovery
        from .infra_tools import list_gcp_services_internal
        services = await list_gcp_services_internal()
        if any(s["name"] == component_name for s in services if isinstance(s, dict)):
            return {"status": "unknown", "component": component_name, "message": "Service exists in GCP but ILB mapping is missing."}

        return {"status": "not_found", "component": component_name}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def check_all_components_health_internal() -> list:
    """Réalise un health check global de TOUS les services et composants Zenika.

    Tente d'abord de récupérer la liste dynamique depuis GCP Cloud Run.
    Fallback sur la liste statique si GCP est indisponible.

    Returns:
        Liste de résultats check_component_health pour chaque composant.
    """
    try:
        from .infra_tools import list_gcp_services_internal

        gcp_services = await list_gcp_services_internal()
        is_valid_list = (
            isinstance(gcp_services, list)
            and len(gcp_services) > 0
            and not any("error" in s for s in gcp_services if isinstance(s, dict))
        )

        service_names = (
            [s["name"] for s in gcp_services if isinstance(s, dict) and "name" in s]
            if is_valid_list
            else ZENIKA_STATIC_SERVICES
        )
        if not is_valid_list:
            logger.warning("[healthcheck] GCP discovery failed, using static service list.")

        tasks = [check_component_health_internal(name) for name in service_names]
        tasks.extend([
            check_component_health_internal("redis-cache"),
            check_component_health_internal("alloydb-primary"),
            check_component_health_internal("bigquery-finops"),
        ])

        results = await asyncio.gather(*tasks)
        return list(results)
    except Exception as e:
        logger.exception("Error running global health check")
        return [{"status": "error", "error": str(e)}]


async def get_ingestion_pipeline_status_internal() -> dict:
    """Récupère l'état complet de la pipeline d'ingestion CV (Drive → Pub/Sub → cv_api).

    Interroge drive_api/status via l'ILB interne et enrichit la réponse
    avec des recommandations d'action automatiques si des blocages sont détectés.

    Returns:
        Dict {status, pipeline: {...}, recommendations: [...]}.
    """
    try:
        drive_api_url = os.getenv("DRIVE_API_URL", "http://api.internal.zenika/api/drive")
        auth = mcp_auth_header_var.get(None)
        headers = {}
        inject(headers)
        if auth:
            headers["Authorization"] = auth

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{drive_api_url.rstrip('/')}/status", headers=headers)
            res.raise_for_status()
            data = res.json()

        errors = data.get("errors", 0)
        queued = data.get("queued", 0)
        processing = data.get("processing", 0)
        pending = data.get("pending", 0)
        imported = data.get("imported", 0)
        total = data.get("total_files_scanned", 0)

        recommendations = []
        if errors > 0:
            recommendations.append(f"⚠️ {errors} CV(s) en erreur. Action : POST /drive/retry-errors.")
        if queued > 0:
            recommendations.append(f"ℹ️ {queued} CV(s) en file Pub/Sub. Pipeline active.")
        if processing > 0:
            recommendations.append(f"🔄 {processing} CV(s) en cours de traitement par cv_api.")
        if pending > 0 and queued == 0 and processing == 0:
            recommendations.append(f"⏸️ {pending} CV(s) en attente sans traitement actif. Sync Drive (/sync) nécessaire ?")
        if not recommendations:
            recommendations.append(f"✅ Pipeline saine — {imported}/{total} CVs importés, aucune erreur.")

        return {
            "status": "ok",
            "pipeline": {
                "total_files_scanned": total,
                "pending": pending,
                "queued": queued,
                "processing": processing,
                "imported": imported,
                "ignored": data.get("ignored", 0),
                "errors": errors,
                "last_processed_time": data.get("last_processed_time"),
            },
            "recommendations": recommendations,
        }
    except Exception as e:
        logger.exception(f"get_ingestion_pipeline_status failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "recommendations": ["❌ Impossible de joindre drive_api. Vérifier via check_component_health('drive')."],
        }
