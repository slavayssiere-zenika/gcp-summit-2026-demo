"""
tools/infra_tools.py — Infrastructure topology & Cloud Run service discovery.

Tools exposés :
  - get_infrastructure_topology(hours_lookback) : graphe de dépendances via GCP Cloud Trace
  - list_gcp_services_internal()                : liste les services Cloud Run Zenika
  - get_gcp_project_id()                        : résolution du GCP Project ID
  - get_gcp_project_id_from_metadata()          : résolution async via metadata server
"""

import asyncio
import logging
import os
import re
import time
from urllib.parse import urlparse

from google.cloud import run_v2
from google.protobuf.timestamp_pb2 import Timestamp

logger = logging.getLogger(__name__)


def get_gcp_project_id() -> str:
    """
    Résout le GCP project ID dans l'ordre de priorité :
    1. Variable d'environnement GCP_PROJECT_ID
    2. ADC via google.auth.default() (natif Cloud Run / gcloud CLI)
    3. Chaîne vide — les clients GCP lèveront des erreurs explicites
    """
    pid = os.getenv("GCP_PROJECT_ID", "").strip()
    if pid and pid not in ("your-gcp-project-id", "YOUR_GCP_PROJECT_ID"):
        return pid
    try:
        import google.auth
        _, project = google.auth.default()
        if project:
            logger.info("[GCP] Project ID résolu via ADC : '%s'", project)
            return project
    except Exception as e:
        logger.warning("[GCP] Impossible de résoudre le project ID via google.auth.default(): %s", e)
    return ""


async def get_gcp_project_id_from_metadata() -> str:
    """Résout le GCP Project ID via le serveur de métadonnées GCP (Cloud Run)."""
    pid = os.getenv("GCP_PROJECT_ID")
    if pid:
        return pid
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"},
            )
            if res.status_code == 200:
                project_id = res.text.strip()
                logger.info("[metadata] GCP Project ID retrieved: %s", project_id)
                return project_id
    except Exception as e:
        logger.debug("[metadata] Metadata server unavailable: %s", e)
    return get_gcp_project_id()


async def list_gcp_services_internal() -> list:
    """Liste tous les services Cloud Run Zenika déployés dans le projet GCP.

    Filtre sur les keywords Zenika (api, mcp, agent, frontend, etc.)
    pour exclure les services tiers hébergés dans le même projet.

    Returns:
        Liste de dicts {name, uri, location, labels} ou {"error": ...}.
    """
    try:
        project_id = await get_gcp_project_id_from_metadata()
        client_run = run_v2.ServicesAsyncClient()
        parent = f"projects/{project_id}/locations/-"
        services_pager = await client_run.list_services(parent=parent)
        zenika_keywords = [
            "api", "mcp", "agent", "frontend", "analytics",
            "monitoring", "users", "items", "cv", "competencies",
            "missions", "prompts", "prompt", "drive",
        ]
        results = []
        async for service in services_pager:
            name = service.name.split("/")[-1]
            if any(k in name.lower() for k in zenika_keywords):
                results.append({
                    "name": name,
                    "uri": service.uri,
                    "location": service.name.split("/")[3],
                    "labels": dict(service.labels) if service.labels else {},
                })
        logger.info("[list_gcp_services] Found %d Zenika services in project %s", len(results), project_id)
        return results
    except Exception as e:
        logger.exception(f"Error listing Cloud Run services: {e}")
        return {"error": str(e)}


async def get_infrastructure_topology(hours_lookback: int = 1) -> dict:
    """Récupère la topologie dynamique de l'infrastructure via GCP Cloud Trace.

    Analyse les traces des `hours_lookback` dernières heures et retourne un graphe
    de dépendances orienté {nodes, links} utilisable par le frontend (D3.js).

    Args:
        hours_lookback: Profondeur historique en heures (défaut 1).

    Returns:
        Dict {nodes: [...], links: [...]} ou lève une exception en cas d'erreur GCP.
    """
    try:
        from google.cloud import trace_v1

        project_id = get_gcp_project_id()
        v1_client = trace_v1.TraceServiceClient()

        now = time.time()
        start_time = now - (hours_lookback * 3600)
        start_ts = Timestamp()
        start_ts.FromSeconds(int(start_time))
        end_ts = Timestamp()
        end_ts.FromSeconds(int(now))

        request = trace_v1.ListTracesRequest(
            project_id=project_id,
            start_time=start_ts,
            end_time=end_ts,
            view=trace_v1.ListTracesRequest.ViewType.COMPLETE,
        )
        traces_pager = await asyncio.to_thread(v1_client.list_traces, request=request)

        nodes_data = {}
        links = []
        seen_links = set()
        root_services = set()

        for i, trace_obj in enumerate(traces_pager):
            if i >= 500:
                break

            # Skip health/metrics traces
            skip_trace = False
            for span in trace_obj.spans:
                labels = span.labels if hasattr(span, "labels") else {}
                url = labels.get("/http/url", "")
                if "/health" in url or "/metrics" in url:
                    skip_trace = True
                    break
            if skip_trace:
                continue

            span_to_service = {}

            # First pass: map spans → services
            for span in trace_obj.spans:
                s_id = str(span.span_id)
                service_name = "unknown"
                node_type = "unknown"
                node_label = "unknown"
                labels = span.labels if hasattr(span, "labels") else {}

                if "db.system" in labels:
                    sys = labels["db.system"]
                    if sys == "postgresql":
                        service_name = labels.get("db.name", "alloydb")
                        node_type = "alloydb"
                        node_label = f"AlloyDB ({service_name})"
                    elif sys == "redis":
                        service_name = "redis-cache"
                        node_type = "redis"
                        node_label = "Redis Cache"
                    else:
                        service_name = sys
                        node_type = "database"
                        node_label = sys
                elif "messaging.system" in labels:
                    sys = labels["messaging.system"]
                    service_name = labels.get("messaging.destination", sys)
                    node_type = "pubsub"
                    node_label = f"Pub/Sub ({service_name})"
                elif "g.co/r/cloud_run_revision/service_name" in labels:
                    service_name = labels["g.co/r/cloud_run_revision/service_name"]
                elif "service.name" in labels:
                    service_name = labels["service.name"]
                elif "/http/host" in labels or "/http/url" in labels or "http.url" in labels:
                    h = labels.get("/http/host", "")
                    url = labels.get("/http/url") or labels.get("http.url", "")
                    path = labels.get("http.target", "")

                    if not path and url:
                        path = urlparse(url).path
                    if not h and url:
                        h = urlparse(url).netloc

                    if "api.internal.zenika" in h or h == "api":
                        _path_map = {
                            "/api/users/": "users-api-dev",
                            "/api/items/": "items-api-dev",
                            "/api/prompts/": "prompts-api-dev",
                            "/api/analytics/": "analytics-mcp-dev",
                            "/monitoring-mcp/": "monitoring-mcp-dev",
                            "/api/monitoring/": "monitoring-mcp-dev",
                            "/api/cv/": "cv-api-dev",
                            "/api/missions/": "missions-api-dev",
                            "/api/competencies/": "competencies-api-dev",
                            "/api/drive/": "drive-api-dev",
                            "/api/agent-hr/": "agent-hr-api-dev",
                            "/api/agent-ops/": "agent-ops-api-dev",
                            "/api/agent-missions/": "agent-missions-api-dev",
                            "/auth/": "users-api-dev",
                            "/api/": "agent-router-api-dev",
                        }
                        service_name = next(
                            (v for k, v in _path_map.items() if path.startswith(k)),
                            "lb_private",
                        )
                    elif h:
                        if re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$", h):
                            service_name = h
                        else:
                            service_name = h.split(".")[0]

                if node_type == "unknown" and service_name != "unknown":
                    if "169." in service_name or service_name == "169":
                        service_name = "unknown"
                    elif "127." in service_name or "localhost" in service_name:
                        service_name = "unknown"
                    elif service_name in ("api", "lb_private") or "internal" in service_name:
                        node_type = "lb_private"
                        node_label = "LB Privé (api.internal.zenika)"
                        service_name = "lb_private"
                    elif service_name == "dev" or ".fr" in service_name:
                        node_type = "lb_public"
                        node_label = "LB Public"
                        service_name = "lb_public"
                    elif "pubsub" in service_name:
                        node_type = "pubsub"
                        node_label = "Google Pub/Sub"
                    elif any(k in service_name for k in ("api", "mcp", "frontend", "agent")):
                        node_type = "cloud_run"
                        node_label = service_name
                    else:
                        node_type = "service"
                        node_label = service_name

                span_to_service[s_id] = service_name
                if service_name != "unknown":
                    nodes_data[service_name] = {"id": service_name, "type": node_type, "label": node_label}
                    if not span.parent_span_id:
                        root_services.add(service_name)

            # Second pass: build links
            for span in trace_obj.spans:
                p_id = str(span.parent_span_id) if span.parent_span_id else None
                s_id = str(span.span_id)
                if p_id and p_id in span_to_service:
                    parent_service = span_to_service[p_id]
                    child_service = span_to_service[s_id]
                    if parent_service != child_service and parent_service != "unknown" and child_service != "unknown":
                        link_key = f"{parent_service}->{child_service}"
                        if link_key not in seen_links:
                            links.append({"source": parent_service, "target": child_service})
                            seen_links.add(link_key)

        # Inject user → lb_public → root
        nodes_data["utilisateur"] = {"id": "utilisateur", "type": "user", "label": "Utilisateur (Externe)"}
        nodes_data["lb_public"] = {"id": "lb_public", "type": "lb_public", "label": "LB Public"}
        for root_svr in root_services:
            if root_svr not in ("utilisateur", "lb_public", "lb_private") and "pubsub" not in root_svr:
                for src, tgt in [("utilisateur", "lb_public"), ("lb_public", root_svr)]:
                    k = f"{src}->{tgt}"
                    if k not in seen_links:
                        links.append({"source": src, "target": tgt})
                        seen_links.add(k)

        zenika_keywords = [
            "api", "mcp", "agent", "frontend", "analytics", "monitoring",
            "users", "items", "cv", "competencies", "missions", "prompts",
            "prompt", "drive", "utilisateur", "lb_public",
        ]
        linked_names = {lk["source"] for lk in links} | {lk["target"] for lk in links}
        final_nodes = [
            data for name, data in nodes_data.items()
            if any(k in name.lower() for k in zenika_keywords) or name in linked_names
        ]

        return {"nodes": final_nodes, "links": links}

    except Exception as e:
        logger.exception(f"Failed to fetch topology from GCP: {e}")
        raise
