#!/usr/bin/env python3
"""
mcp_cli.py — CLI Antigravity pour interagir avec les MCP services de la plateforme Zenika.

Usage:
    python3 mcp_cli.py tools [analytics|monitoring]
    python3 mcp_cli.py call [analytics|monitoring] <tool_name> [--args '{"key": "value"}']
    python3 mcp_cli.py finops [daily|weekly|monthly]
    python3 mcp_cli.py errors [--hours 1] [--limit 10]
    python3 mcp_cli.py redis [--pattern '*']
    python3 mcp_cli.py dlq [--sub cv-ingestion-dlq-sub] [--limit 10]
    python3 mcp_cli.py query <sql>
    python3 mcp_cli.py health

Authentification :
    1. Récupère le token via `gcloud auth print-access-token` (ADC local)
    2. S'authentifie sur la prd via POST /auth/login avec l'email gcloud
    3. Stocke le JWT dans ~/.cache/zenika_mcp_cli_token.json (TTL 1h)

Configuration (env vars ou .antigravity_env) :
    ZENIKA_BASE_URL   : base URL de la prd (défaut: https://zenika.slavayssiere.fr)
    GCLOUD_BIN        : chemin vers gcloud (défaut: gcloud)
    ZENIKA_USER_EMAIL : email admin à utiliser pour le login (optionnel, résolu via gcloud)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Charger .antigravity_env si présent
_antigravity_env = Path(__file__).parent / ".antigravity_env"
if _antigravity_env.exists():
    for line in _antigravity_env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

BASE_URL = os.getenv("ZENIKA_BASE_URL", "https://prd.zenika.slavayssiere.fr")
GCLOUD_BIN = os.getenv("GCLOUD_BIN", "gcloud")
TOKEN_CACHE = Path.home() / ".cache" / "zenika_mcp_cli_token.json"
TOKEN_TTL = 3300  # 55 minutes (JWT expire en 1h)

MCP_ENDPOINTS = {
    "analytics": f"{BASE_URL}/mcp/analytics",
    "monitoring": f"{BASE_URL}/mcp/monitoring",  # à adapter selon lb.tf si besoin
}

# ─────────────────────────────────────────────────────────────────────────────
# Authentification
# ─────────────────────────────────────────────────────────────────────────────

def _gcloud_email() -> str:
    """Récupère l'email du compte gcloud actif."""
    result = subprocess.run(
        [GCLOUD_BIN, "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
        capture_output=True, text=True, timeout=10,
    )
    email = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if not email:
        print("❌ Aucun compte gcloud actif. Lancez : gcloud auth login", file=sys.stderr)
        sys.exit(1)
    return email


def _gcloud_admin_password() -> str:
    """Récupère le mot de passe admin depuis Secret Manager via gcloud."""
    # Secret name en prd : admin-password-prd (pas admin-password)
    for secret_name in ["admin-password-prd", "admin-password"]:
        for project in ["prod-ia-staffing", "slavayssiere-sandbox-462015"]:
            result = subprocess.run(
                [GCLOUD_BIN, "secrets", "versions", "access", "latest",
                 f"--secret={secret_name}", f"--project={project}"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

    print("❌ Impossible de récupérer le mot de passe admin depuis Secret Manager.", file=sys.stderr)
    sys.exit(1)


def _login_admin() -> str:
    """Effectue le login admin sur la prd et retourne le JWT."""
    # Le compte admin de la plateforme est admin@zenika.com (créé par Terraform)
    admin_email = os.getenv("ZENIKA_ADMIN_EMAIL", "admin@zenika.com")
    password = _gcloud_admin_password()

    print(f"🔐 Authentification sur {BASE_URL} en tant que : {admin_email}", file=sys.stderr)
    resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"email": admin_email, "password": password},
        timeout=15.0,
    )
    if resp.status_code != 200:
        print(f"❌ Login échoué [{resp.status_code}]: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    token = resp.json().get("access_token")
    if not token:
        print(f"❌ Réponse login sans access_token : {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    return token


def _load_cached_token() -> str | None:
    """Charge le token depuis le cache local si encore valide."""
    if not TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(TOKEN_CACHE.read_text())
        if time.time() < data.get("expires_at", 0):
            return data["token"]
    except Exception:
        pass
    return None


def _save_token(token: str) -> None:
    """Sauvegarde le token dans le cache local."""
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({
        "token": token,
        "expires_at": time.time() + TOKEN_TTL,
    }))


def get_jwt() -> str:
    """
    Obtient un JWT valide pour la prd Zenika.

    Stratégie :
    1. Cache local (~/.cache/zenika_mcp_cli_token.json) si encore valide
    2. Login via POST /auth/login (admin@zenika.com + password Secret Manager)
    """
    cached = _load_cached_token()
    if cached:
        return cached

    token = _login_admin()
    _save_token(token)
    print("✅ Token JWT obtenu et mis en cache.", file=sys.stderr)
    return token


# ─────────────────────────────────────────────────────────────────────────────
# Appels MCP
# ─────────────────────────────────────────────────────────────────────────────

def mcp_list_tools(service: str, token: str) -> list:
    """Liste les tools disponibles sur un service MCP."""
    base = MCP_ENDPOINTS.get(service)
    if not base:
        print(f"❌ Service inconnu : {service}. Choix : {list(MCP_ENDPOINTS)}", file=sys.stderr)
        sys.exit(1)

    resp = httpx.get(f"{base}/tools", headers={"Authorization": f"Bearer {token}"}, timeout=15.0)
    if resp.status_code != 200:
        print(f"❌ [{resp.status_code}] {resp.text[:400]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def mcp_call_tool(service: str, tool_name: str, arguments: dict, token: str) -> dict:
    """Invoque un tool MCP et retourne le résultat."""
    base = MCP_ENDPOINTS.get(service)
    if not base:
        print(f"❌ Service inconnu : {service}.", file=sys.stderr)
        sys.exit(1)

    resp = httpx.post(
        f"{base}/call",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": tool_name, "arguments": arguments},
        timeout=30.0,
    )
    if resp.status_code != 200:
        print(f"❌ [{resp.status_code}] {resp.text[:400]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def _extract_result(raw: dict) -> any:
    """Extrait le contenu textuel du résultat MCP."""
    results = raw.get("result", [])
    if not results:
        return raw
    first = results[0]
    text = first.get("text", "")
    try:
        return json.loads(text)
    except Exception:
        return text


def _print_json(data: any) -> None:
    """Affiche en JSON coloré si possible."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ─────────────────────────────────────────────────────────────────────────────
# Commandes CLI
# ─────────────────────────────────────────────────────────────────────────────

def cmd_tools(args, token: str):
    service = args.service or "analytics"
    tools = mcp_list_tools(service, token)
    print(f"\n📦 Tools disponibles sur '{service}' ({len(tools)}) :")
    for t in tools:
        print(f"  • {t['name']:40s} — {t.get('description','')[:70]}")


def cmd_call(args, token: str):
    service = args.service or "analytics"
    tool_name = args.tool
    arguments = {}
    if args.args:
        try:
            arguments = json.loads(args.args)
        except json.JSONDecodeError as e:
            print(f"❌ --args invalide (JSON attendu) : {e}", file=sys.stderr)
            sys.exit(1)

    raw = mcp_call_tool(service, tool_name, arguments, token)
    _print_json(_extract_result(raw))


def cmd_finops(args, token: str):
    period = getattr(args, "period", "daily") or "daily"
    raw = mcp_call_tool("analytics", "get_finops_report", {"period": period}, token)
    data = _extract_result(raw)
    print(f"\n💰 Rapport FinOps ({period}) :")
    _print_json(data)


def cmd_errors(args, token: str):
    hours = getattr(args, "hours", 1) or 1
    limit = getattr(args, "limit", 10) or 10
    raw = mcp_call_tool("monitoring", "get_recent_500_errors",
                        {"hours_lookback": hours, "limit": limit}, token)
    data = _extract_result(raw)
    errors = data if isinstance(data, list) else data.get("errors", data)
    print(f"\n🚨 Erreurs 5xx récentes (dernières {hours}h, max {limit}) : {len(errors) if isinstance(errors, list) else '?'}")
    _print_json(errors)


def cmd_redis(args, token: str):
    pattern = getattr(args, "pattern", "*") or "*"
    raw = mcp_call_tool("monitoring", "get_redis_invalidation_state", {"pattern": pattern}, token)
    _print_json(_extract_result(raw))


def cmd_dlq(args, token: str):
    sub = getattr(args, "sub", "cv-ingestion-dlq-sub") or "cv-ingestion-dlq-sub"
    limit = getattr(args, "limit", 10) or 10
    raw = mcp_call_tool("monitoring", "inspect_pubsub_dlq",
                        {"subscription_id": sub, "limit": limit}, token)
    data = _extract_result(raw)
    msgs = data.get("messages", []) if isinstance(data, dict) else data
    print(f"\n📬 DLQ '{sub}' : {len(msgs)} message(s)")
    _print_json(data)


def cmd_query(args, token: str):
    sql = args.sql
    raw = mcp_call_tool("monitoring", "execute_read_only_query", {"query": sql}, token)
    _print_json(_extract_result(raw))


def cmd_health(args, token: str):
    raw = mcp_call_tool("monitoring", "check_all_components_health", {}, token)
    data = _extract_result(raw)
    components = data if isinstance(data, list) else [data]
    print(f"\n🏥 Health Check global ({len(components)} composants) :")
    for c in components:
        status = c.get("status", "?")
        icon = {"healthy": "✅", "unhealthy": "❌", "degraded": "⚠️", "unreachable": "🔌"}.get(status, "❓")
        print(f"  {icon} {c.get('component', c.get('name', '?')):40s} [{status}]")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CLI Antigravity — Interagit avec les MCP services de la plateforme Zenika (prd)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--no-cache", action="store_true", help="Forcer un nouveau login (ignorer le cache JWT)")
    parser.add_argument("--env", default="prd", choices=["prd", "dev", "uat"], help="Environnement cible")

    sub = parser.add_subparsers(dest="command", required=True)

    # tools
    p_tools = sub.add_parser("tools", help="Lister les tools d'un service MCP")
    p_tools.add_argument("service", nargs="?", default="analytics", choices=["analytics", "monitoring"],
                         help="Service MCP cible")
    p_tools.set_defaults(func=cmd_tools)

    # call
    p_call = sub.add_parser("call", help="Invoquer un tool MCP")
    p_call.add_argument("service", choices=["analytics", "monitoring"], help="Service MCP cible")
    p_call.add_argument("tool", help="Nom du tool MCP")
    p_call.add_argument("--args", default="{}", help="Arguments JSON (ex: '{\"period\": \"weekly\"}')")
    p_call.set_defaults(func=cmd_call)

    # finops
    p_finops = sub.add_parser("finops", help="Rapport FinOps IA")
    p_finops.add_argument("period", nargs="?", default="daily", choices=["daily", "weekly", "monthly"])
    p_finops.set_defaults(func=cmd_finops)

    # errors
    p_errors = sub.add_parser("errors", help="Erreurs HTTP 5xx récentes")
    p_errors.add_argument("--hours", type=int, default=1, help="Fenêtre temporelle en heures")
    p_errors.add_argument("--limit", type=int, default=10, help="Nombre max d'erreurs")
    p_errors.set_defaults(func=cmd_errors)

    # redis
    p_redis = sub.add_parser("redis", help="Inspecter les clés Redis")
    p_redis.add_argument("--pattern", default="*", help="Pattern SCAN Redis")
    p_redis.set_defaults(func=cmd_redis)

    # dlq
    p_dlq = sub.add_parser("dlq", help="Inspecter la Dead Letter Queue Pub/Sub")
    p_dlq.add_argument("--sub", default="cv-ingestion-dlq-sub", help="ID de la souscription DLQ")
    p_dlq.add_argument("--limit", type=int, default=10, help="Nombre max de messages")
    p_dlq.set_defaults(func=cmd_dlq)

    # query
    p_query = sub.add_parser("query", help="Requête SQL SELECT sur AlloyDB")
    p_query.add_argument("sql", help="Requête SQL SELECT")
    p_query.set_defaults(func=cmd_query)

    # health
    p_health = sub.add_parser("health", help="Health check global de tous les composants")
    p_health.set_defaults(func=cmd_health)

    args = parser.parse_args()

    # Override BASE_URL selon l'environnement
    global BASE_URL, MCP_ENDPOINTS
    if args.env == "dev":
        BASE_URL = os.getenv("ZENIKA_DEV_URL", "https://dev.zenika.slavayssiere.fr")
    elif args.env == "uat":
        BASE_URL = os.getenv("ZENIKA_UAT_URL", "https://uat.zenika.slavayssiere.fr")
    MCP_ENDPOINTS = {
        "analytics": f"{BASE_URL}/mcp/analytics",
        "monitoring": f"{BASE_URL}/monitoring-mcp/mcp",
    }

    # Authentification
    if args.no_cache and TOKEN_CACHE.exists():
        TOKEN_CACHE.unlink()
    token = get_jwt()

    # Dispatch
    args.func(args, token)


if __name__ == "__main__":
    main()
