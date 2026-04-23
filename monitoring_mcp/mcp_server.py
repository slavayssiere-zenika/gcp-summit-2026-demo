import asyncio
import json
import os
import logging
import contextvars
from datetime import datetime
from mcp.server import Server
from mcp.types import Tool, TextContent
from google.protobuf.timestamp_pb2 import Timestamp
import time
from google.cloud import logging_v2 as logging_cloud
from google.cloud import run_v2

# Standard context var for MCP auth
mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Config
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
    pid = os.getenv("GCP_PROJECT_ID")
    if pid:
        return pid
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"}
            )
            if res.status_code == 200:
                project_id = res.text.strip()
                logger.info("[metadata] GCP Project ID retrieved: %s", project_id)
                return project_id
    except Exception as e:
        logger.debug("[metadata] Metadata server unavailable: %s", e)
    return get_gcp_project_id()


PROJECT_ID = get_gcp_project_id()

server = Server("monitoring-mcp")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_infrastructure_topology",
            description="Récupère la topologie dynamique de l'infrastructure en analysant les traces GCP Cloud Trace. Retourne un graphe de dépendances entre services.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_lookback": {"type": "integer", "description": "Nombre d'heures d'historique à analyser (défaut 1).", "default": 1}
                }
            }
        ),
        Tool(
            name="get_service_logs",
            description="Extrait les logs récents d'un service Cloud Run spécifique. Permet d'investiguer les erreurs 500 ou les timeouts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Le nom du service Cloud Run (ex: 'agent-router-api-dev')."},
                    "limit": {"type": "integer", "description": "Nombre de lignes à remonter (défaut 10).", "default": 10},
                    "hours_lookback": {"type": "integer", "description": "Nombre d'heures d'historique (défaut 1).", "default": 1},
                    "severity": {"type": "string", "description": "Niveau minimum de sévérité (ex: 'ERROR', 'INFO').", "default": "DEFAULT"}
                },
                "required": ["service_name"]
            }
        ),
        Tool(
            name="list_gcp_services",
            description="Liste tous les services Cloud Run de la plateforme Zenika déployés dans le projet GCP.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="check_component_health",
            description="Vérifie l'état de santé d'un composant de la plateforme (Service Cloud Run, Redis, BigQuery, AlloyDB).",
            inputSchema={
                "type": "object",
                "properties": {
                    "component_name": {"type": "string", "description": "Nom du service ou composant (ex: 'users-api', 'redis-cache', 'alloydb')."}
                },
                "required": ["component_name"]
            }
        ),
        Tool(
            name="check_all_components_health",
            description="Réalise un check de santé global de TOUS les services et composants de la plateforme Zenika.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_ingestion_pipeline_status",
            description="Récupère l'état complet de la pipeline d'ingéstion des CVs (Discovery Drive → Queue Pub/Sub → Traitement cv_api). Retourne les compteurs par statut (pending, queued, processing, imported, errors) et signale les blocages. Utiliser pour diagnostiquer : 'combien de CVs sont en attente ?', 'y a-t-il des erreurs d'import ?', 'la pipeline est-elle active ?'.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="search_cloud_logs_by_trace",
            description="Récupère le flux de logs (Cloud Logging) complet associé à un trace ID spécifique (Tempo / OTel). Idéal pour comprendre le contexte complet d'une erreur distribuée.",
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string", "description": "L'ID de la trace (sans le préfixe project)."},
                    "limit": {"type": "integer", "description": "Nombre de logs max.", "default": 50}
                },
                "required": ["trace_id"]
            }
        ),
        Tool(
            name="get_recent_500_errors",
            description="Recherche les erreurs HTTP 5xx récentes sur l'ensemble des services Cloud Run GCP.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Nombre de logs max.", "default": 10},
                    "hours_lookback": {"type": "integer", "description": "Nombre d'heures d'historique.", "default": 1}
                }
            }
        ),
        Tool(
            name="inspect_pubsub_dlq",
            description="Examine les messages dans la file d'attente (Dead Letter Queue) Pub/Sub sans les acquitter (lecture seule). Permet d'investiguer les échecs d'ingestion asynchrones.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string", "description": "L'ID de la souscription DLQ.", "default": "cv-ingestion-dlq-sub"},
                    "limit": {"type": "integer", "description": "Nombre max de messages à lire.", "default": 10}
                }
            }
        ),
        Tool(
            name="get_redis_invalidation_state",
            description="Vérifie l'état des clés dans Redis (cache sémantique, sessions). Utile pour déboguer des problèmes d'invalidation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Pattern de recherche de clés (ex: 'items:list:*', 'session:*').", "default": "*"}
                }
            }
        ),
        Tool(
            name="execute_read_only_query",
            description="Exécute une requête SQL SELECT (lecture seule) sur la base de données PostgreSQL/AlloyDB pour vérifier la consistance des données.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La requête SQL SELECT."},
                    "db_name": {"type": "string", "description": "Nom de la base.", "default": "zenika"}
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "get_infrastructure_topology":
            hours = arguments.get("hours_lookback", 1)
            data = await get_infrastructure_topology(hours)
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "get_service_logs":
            service_name = arguments.get("service_name")
            limit = arguments.get("limit", 10)
            hours = arguments.get("hours_lookback", 1)
            severity = arguments.get("severity", "DEFAULT")
            data = await get_service_logs_internal(service_name, limit, hours, severity)
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "list_gcp_services":
            data = await list_gcp_services_internal()
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "check_component_health":
            component_name = arguments.get("component_name")
            data = await check_component_health_internal(component_name)
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "check_all_components_health":
            data = await check_all_components_health_internal()
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "get_ingestion_pipeline_status":
            data = await get_ingestion_pipeline_status_internal()
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "search_cloud_logs_by_trace":
            trace_id = arguments.get("trace_id")
            limit = arguments.get("limit", 50)
            data = await search_cloud_logs_by_trace_internal(trace_id, limit)
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "get_recent_500_errors":
            limit = arguments.get("limit", 10)
            hours = arguments.get("hours_lookback", 1)
            data = await get_recent_500_errors_internal(limit, hours)
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "inspect_pubsub_dlq":
            sub_id = arguments.get("subscription_id", "cv-ingestion-dlq-sub")
            limit = arguments.get("limit", 10)
            data = await inspect_pubsub_dlq_internal(sub_id, limit)
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "get_redis_invalidation_state":
            pattern = arguments.get("pattern", "*")
            data = await get_redis_invalidation_state_internal(pattern)
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "execute_read_only_query":
            query = arguments.get("query")
            db_name = arguments.get("db_name", "zenika")
            data = await execute_read_only_query_internal(query, db_name)
            return [TextContent(type="text", text=json.dumps(data))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        logger.exception(f"Error in monitoring-mcp tool call '{name}'")
        return [TextContent(type="text", text=json.dumps({
            "error": str(e),
            "tool": name,
            "status": "failure"
        }))]

async def get_infrastructure_topology(hours_lookback: int = 1) -> dict:
    """Standalone logic to fetch infrastructure topology from GCP Cloud Trace."""
    try:
        from google.cloud import trace_v1
        v1_client = trace_v1.TraceServiceClient()
        
        # Time range
        now = time.time()
        start_time = now - (hours_lookback * 3600)
        
        start_ts = Timestamp()
        start_ts.FromSeconds(int(start_time))
        end_ts = Timestamp()
        end_ts.FromSeconds(int(now))
        
        request = trace_v1.ListTracesRequest(
            project_id=PROJECT_ID,
            start_time=start_ts,
            end_time=end_ts,
            view=trace_v1.ListTracesRequest.ViewType.COMPLETE
        )
        import asyncio
        traces_pager = await asyncio.to_thread(v1_client.list_traces, request=request)
        
        nodes_data = {} # name -> id for dedup
        links = []
        seen_links = set()
        root_services = set()
        
        for i, trace_obj in enumerate(traces_pager):
            if i >= 500: # Limit the number of traces processed to avoid timeout
                break
            
            # 0. Check if we should skip this trace (health/metrics)
            skip_trace = False
            for span in trace_obj.spans:
                labels = span.labels if hasattr(span, 'labels') else {}
                url = labels.get("/http/url", "")
                if "/health" in url or "/metrics" in url:
                    skip_trace = True
                    break
            
            if skip_trace:
                continue

            span_to_service = {}
            # 1. First pass: map all spans to services
            for span in trace_obj.spans:
                s_id = str(span.span_id)
                service_name = "unknown"
                node_type = "unknown"
                node_label = "unknown"
                labels = span.labels if hasattr(span, 'labels') else {}
                
                # Priority extraction
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
                        from urllib.parse import urlparse
                        path = urlparse(url).path

                    if not h and url:
                        from urllib.parse import urlparse
                        h = urlparse(url).netloc
                        
                    import re
                    if "api.internal.zenika" in h or h == "api":
                        if path.startswith("/api/users/"): service_name = "users-api-dev"
                        elif path.startswith("/api/items/"): service_name = "items-api-dev"
                        elif path.startswith("/api/prompts/"): service_name = "prompts-api-dev"
                        elif path.startswith("/api/market/"): service_name = "market-mcp-dev"
                        elif path.startswith("/monitoring-mcp/") or path.startswith("/api/monitoring/"): service_name = "monitoring-mcp-dev"
                        elif path.startswith("/api/cv/"): service_name = "cv-api-dev"
                        elif path.startswith("/api/missions/"): service_name = "missions-api-dev"
                        elif path.startswith("/api/competencies/"): service_name = "competencies-api-dev"
                        elif path.startswith("/api/drive/"): service_name = "drive-api-dev"
                        elif path.startswith("/api/agent-hr/"): service_name = "agent-hr-api-dev"
                        elif path.startswith("/api/agent-ops/"): service_name = "agent-ops-api-dev"
                        elif path.startswith("/api/agent-missions/"): service_name = "agent-missions-api-dev"
                        elif path.startswith("/auth/"): service_name = "users-api-dev"
                        elif path.startswith("/api/"): service_name = "agent-router-api-dev"
                        else: service_name = "lb_private"
                    elif h:
                        if re.match(r'^\d{1,3}(\.\d{1,3}){3}(:\d+)?$', h):
                            service_name = h
                        else:
                            service_name = h.split('.')[0]

                if node_type == "unknown" and service_name != "unknown":
                    if "169." in service_name or service_name == "169":
                        service_name = "unknown" # Ignorer metadata
                    elif "127." in service_name or service_name == "127" or "localhost" in service_name:
                        service_name = "unknown" # Ignorer localhost
                    elif service_name == "api" or "internal" in service_name or service_name == "lb_private":
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
                    elif "api" in service_name or "mcp" in service_name or "frontend" in service_name or "agent" in service_name:
                        node_type = "cloud_run"
                        node_label = service_name
                    else:
                        node_type = "service"
                        node_label = service_name
                
                span_to_service[s_id] = service_name
                if service_name != "unknown":
                    nodes_data[service_name] = {"id": service_name, "type": node_type, "label": node_label}
                    
                    # Détection d'un span racine
                    if not span.parent_span_id:
                        root_services.add(service_name)
            
            # 2. Second pass: find links using normalized IDs
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
                            
        # 2.5 Inject User node and connect to root services
        nodes_data["utilisateur"] = {"id": "utilisateur", "type": "user", "label": "Utilisateur (Externe)"}
        nodes_data["lb_public"] = {"id": "lb_public", "type": "lb_public", "label": "LB Public"}
        
        for root_svr in root_services:
            if root_svr not in ("utilisateur", "lb_public", "lb_private") and "pubsub" not in root_svr:
                # Add forced link: User -> LB Public -> Root Service
                user_lb_link = "utilisateur->lb_public"
                lb_svc_link = f"lb_public->{root_svr}"
                
                if user_lb_link not in seen_links:
                    links.append({"source": "utilisateur", "target": "lb_public"})
                    seen_links.add(user_lb_link)
                
                if lb_svc_link not in seen_links:
                    links.append({"source": "lb_public", "target": root_svr})
                    seen_links.add(lb_svc_link)

        
        # 3. Filter nodes: Keep Zenika services OR nodes involved in links
        zenika_keywords = ["api", "mcp", "agent", "frontend", "market", "monitoring", "users", "items", "cv", "competencies", "missions", "prompts", "prompt", "drive", "utilisateur", "lb_public"]
        final_nodes = []
        linked_service_names = set()
        for l in links:
            linked_service_names.add(l["source"])
            linked_service_names.add(l["target"])
            
        for name, data in nodes_data.items():
            is_zenika = any(k in name.lower() for k in zenika_keywords)
            is_linked = name in linked_service_names
            if is_zenika or is_linked:
                final_nodes.append(data)
        
        return {
            "nodes": final_nodes,
            "links": links
        }
    except Exception as e:
        logger.exception(f"Failed to fetch topology from GCP: {e}")
        raise e

async def get_service_logs_internal(service_name: str, limit: int = 10, hours_lookback: int = 1, severity: str = "DEFAULT") -> list:
    """Fetch logs from Cloud Logging for a specific Cloud Run service."""
    try:
        # Autocomplétion intelligente du nom de service via GCP (Fuzzy Matching)
        services = await list_gcp_services_internal()
        valid_services = [s["name"] for s in services if isinstance(s, dict) and "name" in s]
        
        normalized_query = service_name.lower().replace(" ", "-")
        matched_service = next((s for s in valid_services if normalized_query in s.lower()), None)
        target_service = matched_service if matched_service else service_name

        client_logging = logging_cloud.Client(project=PROJECT_ID)
        
        # Calculate time filter
        from datetime import datetime, timedelta, timezone
        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours_lookback)).isoformat()
        
        filter_str = (
            f'resource.type="cloud_run_revision" '
            f'AND resource.labels.service_name="{target_service}" '
            f'AND timestamp >= "{start_time}"'
        )
        if severity != "DEFAULT":
            filter_str += f' AND severity >= {severity}'
            
        entries = client_logging.list_entries(filter_=filter_str, order_by=logging_cloud.DESCENDING, page_size=limit)
        
        logs = []
        for entry in entries:
            log_content = entry.text_payload
            if hasattr(entry, 'json_payload') and entry.json_payload:
                if isinstance(entry.json_payload, dict):
                    log_content = entry.json_payload.get("message", entry.json_payload)
                else:
                    log_content = entry.json_payload

            logs.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "severity": entry.severity,
                "cloud_run_service": target_service,
                "message": log_content
            })
            if len(logs) >= limit:
                break
                
        return logs
    except Exception as e:
        logger.exception(f"Error fetching logs for {service_name}: {e}")
        return {"error": str(e), "service": service_name}

async def search_cloud_logs_by_trace_internal(trace_id: str, limit: int = 50) -> list:
    """Fetch logs associated with a specific Cloud Trace ID."""
    try:
        client_logging = logging_cloud.Client(project=PROJECT_ID)
        trace_path = f"projects/{PROJECT_ID}/traces/{trace_id}" if "projects/" not in trace_id else trace_id
        
        filter_str = f'trace="{trace_path}"'
        entries = client_logging.list_entries(filter_=filter_str, order_by=logging_cloud.ASCENDING, page_size=limit)
        
        logs = []
        for entry in entries:
            log_content = entry.text_payload
            if hasattr(entry, 'json_payload') and entry.json_payload:
                if isinstance(entry.json_payload, dict):
                    log_content = entry.json_payload.get("message", entry.json_payload)
                else:
                    log_content = entry.json_payload

            logs.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "severity": entry.severity,
                "resource_type": entry.resource.type if hasattr(entry, 'resource') else None,
                "message": log_content
            })
            if len(logs) >= limit:
                break
        return logs
    except Exception as e:
        logger.exception(f"Error fetching logs for trace {trace_id}: {e}")
        return {"error": str(e), "trace_id": trace_id}

async def get_recent_500_errors_internal(limit: int = 10, hours_lookback: int = 1) -> list:
    """Fetch recent 500 errors across all Cloud Run services."""
    try:
        client_logging = logging_cloud.Client(project=PROJECT_ID)
        from datetime import datetime, timedelta, timezone
        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours_lookback)).isoformat()
        
        filter_str = (
            f'resource.type="cloud_run_revision" '
            f'AND httpRequest.status >= 500 '
            f'AND timestamp >= "{start_time}"'
        )
        entries = client_logging.list_entries(filter_=filter_str, order_by=logging_cloud.DESCENDING, page_size=limit)
        
        logs = []
        for entry in entries:
            log_content = entry.text_payload
            if hasattr(entry, 'json_payload') and entry.json_payload:
                if isinstance(entry.json_payload, dict):
                    log_content = entry.json_payload.get("message", entry.json_payload)
                else:
                    log_content = entry.json_payload
            
            service_name = "unknown"
            if hasattr(entry, 'resource') and hasattr(entry.resource, 'labels'):
                service_name = entry.resource.labels.get("service_name", "unknown")

            trace_id = entry.trace.split('/')[-1] if entry.trace else None
            
            req_info = {}
            if hasattr(entry, 'http_request') and entry.http_request:
                hr = entry.http_request
                if isinstance(hr, dict):
                    req_info = {
                        "method": hr.get('requestMethod', ''),
                        "url": hr.get('requestUrl', ''),
                        "status": hr.get('status', 0),
                    }
                else:
                    req_info = {
                        "method": getattr(hr, 'requestMethod', ''),
                        "url": getattr(hr, 'requestUrl', ''),
                        "status": getattr(hr, 'status', 0),
                    }

            logs.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "service": service_name,
                "trace_id": trace_id,
                "request": req_info,
                "message": log_content
            })
            if len(logs) >= limit:
                break
        return logs
    except Exception as e:
        logger.exception(f"Error fetching 500 errors: {e}")
        return {"error": str(e)}

async def inspect_pubsub_dlq_internal(subscription_id: str = "cv-ingestion-dlq-sub", limit: int = 10) -> list:
    """Pull messages from a Pub/Sub Dead Letter Queue."""
    try:
        from google.cloud import pubsub_v1
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(PROJECT_ID, subscription_id)
        
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": limit},
            timeout=10.0
        )
        
        messages = []
        for received_message in response.received_messages:
            msg = received_message.message
            messages.append({
                "message_id": msg.message_id,
                "publish_time": msg.publish_time.isoformat() if msg.publish_time else None,
                "attributes": dict(msg.attributes),
                "data": msg.data.decode("utf-8") if msg.data else None
            })
            
        return {"status": "ok", "messages": messages, "count": len(messages)}
    except Exception as e:
        logger.exception(f"Error inspecting DLQ {subscription_id}: {e}")
        return {"error": str(e), "subscription": subscription_id}

async def get_redis_invalidation_state_internal(pattern: str = "*") -> dict:
    """Scan Redis keys to check caching/invalidation state."""
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(redis_url, socket_timeout=2.0)
        
        keys = []
        cursor = '0'
        while cursor != 0:
            cursor, data = r.scan(cursor=cursor, match=pattern, count=100)
            keys.extend([k.decode('utf-8') for k in data])
            if len(keys) >= 100:
                break
                
        sample = {}
        for k in keys[:20]:
            sample[k] = r.ttl(k)
            
        return {
            "status": "ok", 
            "matched_keys_count": len(keys),
            "keys_sample": sample,
            "redis_url": redis_url
        }
    except Exception as e:
        logger.exception(f"Error checking Redis state: {e}")
        return {"error": str(e)}

async def execute_read_only_query_internal(query: str, db_name: str = "zenika") -> dict:
    """Execute a read-only query on AlloyDB / PostgreSQL."""
    query_lower = query.lower().strip()
    forbidden_keywords = ["insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke"]
    if any(keyword in query_lower for keyword in forbidden_keywords):
        return {"error": "Only read-only SELECT queries are allowed."}
        
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        
        db_url = os.getenv("DATABASE_URL", f"postgresql+asyncpg://postgres:postgres@alloydb:5432/{db_name}")
        
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            result = await conn.execute(text(query))
            rows = result.mappings().all()
            
            formatted_rows = []
            for row in rows:
                formatted_row = {}
                for k, v in row.items():
                    if isinstance(v, datetime):
                        formatted_row[k] = str(v)
                    else:
                        formatted_row[k] = str(v) if v is not None else None
                formatted_rows.append(formatted_row)
                
        await engine.dispose()
        return {"status": "ok", "rows": formatted_rows, "count": len(formatted_rows)}
    except Exception as e:
        logger.exception(f"Error executing DB query: {e}")
        return {"error": str(e)}

async def list_gcp_services_internal() -> list:
    try:
        project_id = await get_gcp_project_id_from_metadata()
        client_run = run_v2.ServicesAsyncClient()
        parent = f"projects/{project_id}/locations/-"
        services_pager = await client_run.list_services(parent=parent)
        zenika_keywords = ["api", "mcp", "agent", "frontend", "market", "monitoring", "users", "items", "cv", "competencies", "missions", "prompts", "prompt", "drive"]
        results = []
        async for service in services_pager:
            name = service.name.split("/")[-1]
            if any(k in name.lower() for k in zenika_keywords):
                results.append({
                    "name": name,
                    "uri": service.uri,
                    "location": service.name.split("/")[3],
                    "labels": dict(service.labels) if service.labels else {}
                })
        logger.info("[list_gcp_services] Found %d Zenika services in project %s", len(results), project_id)
        return results
    except Exception as e:
        logger.exception(f"Error listing Cloud Run services: {e}")
        return {"error": str(e)}

async def check_component_health_internal(component_name: str) -> dict:
    try:
        # 1. Redis Check
        if "redis" in component_name.lower():
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            try:
                r = redis.from_url(redis_url, socket_timeout=2.0)
                if r.ping():
                    return {"status": "healthy", "component": component_name, "message": "Redis PING successful"}
            except Exception as re:
                return {"status": "unhealthy", "component": component_name, "error": str(re)}

        # 2. BigQuery / AlloyDB Check
        if any(k in component_name.lower() for k in ["bigquery", "alloydb"]):
            try:
                from google.cloud import bigquery
                bq_client = bigquery.Client(project=PROJECT_ID)
                bq_client.list_datasets(max_results=1)
                return {"status": "healthy", "component": component_name, "message": "GCP Data APIs are responsive"}
            except Exception as be:
                return {"status": "degraded", "component": component_name, "error": str(be)}

        # 3. Cloud Run Service Check via Internal Load Balancer
        mapping = {
            "users": "/api/users/",
            "items": "/api/items/",
            "prompts": "/api/prompts/",
            "market": "/api/market/",
            "monitoring": "/monitoring-mcp/",
            "cv": "/api/cv/",
            "missions": "/api/missions/",
            "competencies": "/api/competencies/",
            "drive": "/api/drive/",
            "agent-hr": "/api/agent-hr/",
            "agent-ops": "/api/agent-ops/",
            "router": "/api/",
            "auth": "/auth/"
        }
        
        target_path = None
        for key, path in mapping.items():
            if key in component_name.lower():
                target_path = path
                break
        
        if target_path:
            import httpx
            url = f"http://api.internal.zenika{target_path}health" if target_path != "/monitoring-mcp/" else f"http://api.internal.zenika/api/monitoring/health"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.get(url)
                    if res.status_code == 200:
                        return {"status": "healthy", "component": component_name, "url": url, "code": 200}
                    else:
                        return {"status": "unhealthy", "component": component_name, "url": url, "code": res.status_code, "detail": res.text[:200]}
            except Exception as he:
                return {"status": "unreachable", "component": component_name, "url": url, "error": str(he)}

        services = await list_gcp_services_internal()
        if any(s["name"] == component_name for s in services if isinstance(s, dict)):
            return {"status": "unknown", "component": component_name, "message": "Service exists in GCP but component name mapping for ILB is missing."}
            
        return {"status": "not_found", "component": component_name}
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def check_all_components_health_internal() -> list:
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
        "market-mcp",
        "monitoring-mcp",
        "agent-router-api",
    ]

    try:
        gcp_services = await list_gcp_services_internal()
        is_valid_list = isinstance(gcp_services, list) and len(gcp_services) > 0 and not any("error" in s for s in gcp_services if isinstance(s, dict))

        if is_valid_list:
            service_names = [s["name"] for s in gcp_services if isinstance(s, dict) and "name" in s]
        else:
            logger.warning("[healthcheck] GCP discovery failed, using static service list.")
            service_names = ZENIKA_STATIC_SERVICES

        import asyncio
        tasks = []
        for name in service_names:
            tasks.append(check_component_health_internal(name))
            
        # Add core data components
        tasks.append(check_component_health_internal("redis-cache"))
        tasks.append(check_component_health_internal("alloydb-primary"))
        tasks.append(check_component_health_internal("bigquery-finops"))
        
        results = await asyncio.gather(*tasks)
        return list(results)
    except Exception as e:
        logger.exception("Error running global health check")
        return [{"status": "error", "error": str(e)}]


async def get_ingestion_pipeline_status_internal() -> dict:
    """
    Interroge drive_api/status via l'ILB interne pour retourner l'état de la
    pipeline d'ingestion CV (Discovery → Pub/Sub → cv_api).

    Ajoute une recommandation d'action si des erreurs ou des blocages sont détectés.
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

        # Analyse et recommandation automatique
        errors = data.get("errors", 0)
        queued = data.get("queued", 0)
        processing = data.get("processing", 0)
        pending = data.get("pending", 0)
        imported = data.get("imported", 0)
        total = data.get("total_files_scanned", 0)

        recommendations = []
        if errors > 0:
            recommendations.append(f"⚠️ {errors} CV(s) en erreur d'import. Action recommandée : déclencher un retry via POST /drive/retry-errors.")
        if queued > 0:
            recommendations.append(f"ℹ️ {queued} CV(s) en file Pub/Sub (en attente de traitement par cv_api). Pipeline active.")
        if processing > 0:
            recommendations.append(f"🔄 {processing} CV(s) en cours de traitement par cv_api.")
        if pending > 0 and queued == 0 and processing == 0:
            recommendations.append(f"⏸️ {pending} CV(s) en attente mais aucun traitement en cours. Une synchronisation Drive (/sync) est peut-être nécessaire.")
        if not recommendations:
            recommendations.append(f"✅ Pipeline saine — {imported}/{total} CVs importés, aucune erreur ni blocage.")

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
            "recommendations": ["❌ Impossible de joindre drive_api. Vérifier la santé du service via check_component_health('drive')."]
        }
