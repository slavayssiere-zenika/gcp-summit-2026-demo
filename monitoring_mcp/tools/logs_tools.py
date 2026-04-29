"""
tools/logs_tools.py — Cloud Logging query tools.

Tools exposés :
  - get_service_logs_internal(service_name, limit, hours_lookback, severity)
  - search_cloud_logs_by_trace_internal(trace_id, limit)
  - get_recent_500_errors_internal(limit, hours_lookback)
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from google.cloud import logging_v2 as logging_cloud

logger = logging.getLogger(__name__)


def _get_project_id() -> str:
    """Résolution locale du project ID (sync)."""
    return os.getenv("GCP_PROJECT_ID", "")


async def get_service_logs_internal(
    service_name: str,
    limit: int = 10,
    hours_lookback: int = 1,
    severity: str = "DEFAULT",
) -> list:
    """Extrait les logs récents d'un service Cloud Run spécifique.

    Effectue une auto-complétion fuzzy du nom de service via la liste GCP
    pour tolérer les variations (ex: 'cv-api' vs 'cv-api-dev').

    Args:
        service_name: Nom partiel ou exact du service Cloud Run.
        limit: Nombre maximum de lignes à retourner.
        hours_lookback: Profondeur historique en heures.
        severity: Niveau minimum de sévérité (ERROR, WARNING, INFO, DEFAULT).

    Returns:
        Liste de dicts {timestamp, severity, cloud_run_service, message}.
    """
    try:
        from .infra_tools import list_gcp_services_internal

        services = await list_gcp_services_internal()
        valid_services = [s["name"] for s in services if isinstance(s, dict) and "name" in s]
        normalized_query = service_name.lower().replace(" ", "-")
        matched_service = next((s for s in valid_services if normalized_query in s.lower()), None)
        target_service = matched_service if matched_service else service_name

        project_id = _get_project_id()
        client_logging = logging_cloud.Client(project=project_id)
        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours_lookback)).isoformat()

        filter_str = (
            f'resource.type="cloud_run_revision" '
            f'AND resource.labels.service_name="{target_service}" '
            f'AND timestamp >= "{start_time}"'
        )
        if severity != "DEFAULT":
            filter_str += f" AND severity >= {severity}"

        entries = client_logging.list_entries(
            filter_=filter_str,
            order_by=logging_cloud.DESCENDING,
            page_size=limit,
        )

        logs = []
        for entry in entries:
            log_content = getattr(entry, "payload", None)
            if hasattr(entry, "json_payload") and entry.json_payload:
                if isinstance(entry.json_payload, dict):
                    log_content = entry.json_payload.get("message", entry.json_payload)
                else:
                    log_content = entry.json_payload

            logs.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "severity": entry.severity,
                "cloud_run_service": target_service,
                "message": log_content,
            })
            if len(logs) >= limit:
                break

        return logs
    except Exception as e:
        logger.exception(f"Error fetching logs for {service_name}: {e}")
        return {"error": str(e), "service": service_name}


async def search_cloud_logs_by_trace_internal(trace_id: str, limit: int = 50) -> list:
    """Récupère tous les logs Cloud Logging associés à un trace ID OTel.

    Utile pour investiguer le contexte complet d'une erreur distribuée depuis
    un seul trace ID Tempo ou Jaeger.

    Args:
        trace_id: L'ID de la trace (sans le préfixe 'projects/...'  si non présent).
        limit: Nombre maximum de logs à retourner.

    Returns:
        Liste de dicts {timestamp, severity, resource_type, message}.
    """
    try:
        project_id = _get_project_id()
        client_logging = logging_cloud.Client(project=project_id)
        trace_path = (
            f"projects/{project_id}/traces/{trace_id}"
            if "projects/" not in trace_id
            else trace_id
        )

        entries = client_logging.list_entries(
            filter_=f'trace="{trace_path}"',
            order_by=logging_cloud.ASCENDING,
            page_size=limit,
        )

        logs = []
        for entry in entries:
            log_content = getattr(entry, "payload", None)
            if hasattr(entry, "json_payload") and entry.json_payload:
                if isinstance(entry.json_payload, dict):
                    log_content = entry.json_payload.get("message", entry.json_payload)
                else:
                    log_content = entry.json_payload

            logs.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "severity": entry.severity,
                "resource_type": entry.resource.type if hasattr(entry, "resource") else None,
                "message": log_content,
            })
            if len(logs) >= limit:
                break

        return logs
    except Exception as e:
        logger.exception(f"Error fetching logs for trace {trace_id}: {e}")
        return {"error": str(e), "trace_id": trace_id}


async def get_recent_500_errors_internal(limit: int = 10, hours_lookback: int = 1) -> list:
    """Recherche les erreurs HTTP 5xx récentes sur l'ensemble des services Cloud Run.

    Args:
        limit: Nombre maximum d'entrées à retourner.
        hours_lookback: Profondeur historique en heures.

    Returns:
        Liste de dicts {timestamp, service, trace_id, request, message}.
    """
    try:
        project_id = _get_project_id()
        client_logging = logging_cloud.Client(project=project_id)
        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours_lookback)).isoformat()

        filter_str = (
            f'resource.type="cloud_run_revision" '
            f'AND httpRequest.status >= 500 '
            f'AND timestamp >= "{start_time}"'
        )
        entries = client_logging.list_entries(
            filter_=filter_str,
            order_by=logging_cloud.DESCENDING,
            page_size=limit,
        )

        logs = []
        for entry in entries:
            log_content = getattr(entry, "payload", None)
            if hasattr(entry, "json_payload") and entry.json_payload:
                if isinstance(entry.json_payload, dict):
                    log_content = entry.json_payload.get("message", entry.json_payload)
                else:
                    log_content = entry.json_payload

            svc_name = "unknown"
            if hasattr(entry, "resource") and hasattr(entry.resource, "labels"):
                svc_name = entry.resource.labels.get("service_name", "unknown")

            trace_id_val = entry.trace.split("/")[-1] if entry.trace else None

            req_info = {}
            if hasattr(entry, "http_request") and entry.http_request:
                hr = entry.http_request
                if isinstance(hr, dict):
                    req_info = {"method": hr.get("requestMethod", ""), "url": hr.get("requestUrl", ""), "status": hr.get("status", 0)}
                else:
                    req_info = {"method": getattr(hr, "requestMethod", ""), "url": getattr(hr, "requestUrl", ""), "status": getattr(hr, "status", 0)}

            logs.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "service": svc_name,
                "trace_id": trace_id_val,
                "request": req_info,
                "message": log_content,
            })
            if len(logs) >= limit:
                break

        return logs
    except Exception as e:
        logger.exception(f"Error fetching 500 errors: {e}")
        return {"error": str(e)}
