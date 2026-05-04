#!/usr/bin/env python3
"""
analytics_mcp_proxy.py — Proxy MCP stdio → analytics_mcp prd Zenika.

Implémente le protocole MCP JSON-RPC 2.0 sur stdin/stdout.
Transmet les appels tools à https://prd.zenika.slavayssiere.fr/mcp/analytics/
après authentification automatique via gcloud Secret Manager.

Utilisé par Antigravity via mcp_config.json :
  "analytics-mcp-prd": { "command": "...analytics_mcp_proxy.py" }

Cache JWT : ~/.cache/zenika_mcp_cli_token.json (TTL 55 min).
"""

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

# Charger .antigravity_env si présent (chemin relatif au projet)
_REPO_ROOT = Path(__file__).parent.parent
_antigravity_env = _REPO_ROOT / ".antigravity_env"
if _antigravity_env.exists():
    for line in _antigravity_env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

BASE_URL = os.getenv("ZENIKA_BASE_URL", "https://prd.zenika.slavayssiere.fr")
MCP_URL = f"{BASE_URL}/mcp/analytics"
GCLOUD_BIN = os.getenv("GCLOUD_BIN", "gcloud")
ADMIN_EMAIL = os.getenv("ZENIKA_ADMIN_EMAIL", "admin@zenika.com")
TOKEN_CACHE = Path.home() / ".cache" / "zenika_mcp_cli_token.json"
TOKEN_TTL = 3300  # 55 minutes

# ─────────────────────────────────────────────────────────────────────────────
# Authentification
# ─────────────────────────────────────────────────────────────────────────────

def _get_secret() -> str:
    for secret_name in ["admin-password-prd", "admin-password"]:
        for project in ["prod-ia-staffing", "slavayssiere-sandbox-462015"]:
            r = subprocess.run(
                [GCLOUD_BIN, "secrets", "versions", "access", "latest",
                 f"--secret={secret_name}", f"--project={project}"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
    raise RuntimeError("Impossible de récupérer le mot de passe admin depuis Secret Manager.")


def _load_cached_token() -> str | None:
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
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({
        "token": token,
        "expires_at": time.time() + TOKEN_TTL,
    }))


def get_jwt() -> str:
    cached = _load_cached_token()
    if cached:
        return cached

    password = _get_secret()
    resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": password},
        timeout=15.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login échoué [{resp.status_code}]: {resp.text[:200]}")

    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"Réponse login sans access_token : {resp.text[:200]}")

    _save_token(token)
    return token


# ─────────────────────────────────────────────────────────────────────────────
# Appels MCP upstream
# ─────────────────────────────────────────────────────────────────────────────

def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {get_jwt()}"}


def upstream_list_tools() -> list:
    resp = httpx.get(f"{MCP_URL}/tools", headers=_auth_headers(), timeout=15.0)
    resp.raise_for_status()
    return resp.json()  # [{name, description, inputSchema}, ...]


def upstream_call_tool(name: str, arguments: dict) -> list:
    resp = httpx.post(
        f"{MCP_URL}/call",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json={"name": name, "arguments": arguments},
        timeout=30.0,
    )
    resp.raise_for_status()
    # La réponse analytics_mcp est {"result": [{type, text}]}
    return resp.json().get("result", [])


# ─────────────────────────────────────────────────────────────────────────────
# Protocole MCP stdio (JSON-RPC 2.0)
# ─────────────────────────────────────────────────────────────────────────────

def send(msg: dict) -> None:
    """Écrit un message JSON-RPC sur stdout."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def send_result(req_id, result) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "result": result})


def send_error(req_id, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle_initialize(req_id, params: dict) -> None:
    send_result(req_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "analytics-mcp-prd",
            "version": "1.0.0",
            "description": "Proxy vers analytics_mcp prd Zenika (BigQuery FinOps, Données Marché)",
        },
    })


def handle_tools_list(req_id) -> None:
    try:
        raw_tools = upstream_list_tools()
        # Convertir au format MCP stdio
        tools = []
        for t in raw_tools:
            tools.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "inputSchema": t.get("inputSchema", {"type": "object", "properties": {}}),
            })
        send_result(req_id, {"tools": tools})
    except Exception as e:
        send_error(req_id, -32603, f"Erreur liste tools analytics_mcp prd : {e}")


def handle_tools_call(req_id, params: dict) -> None:
    name = params.get("name", "")
    arguments = params.get("arguments", {})
    try:
        result_items = upstream_call_tool(name, arguments)
        # Convertir au format MCP stdio content
        content = []
        for item in result_items:
            content.append({
                "type": item.get("type", "text"),
                "text": item.get("text", ""),
            })
        if not content:
            content = [{"type": "text", "text": "{}"}]
        send_result(req_id, {"content": content})
    except Exception as e:
        send_error(req_id, -32603, f"Erreur appel tool '{name}' sur analytics_mcp prd : {e}")


def handle_notifications_initialized(params: dict) -> None:
    """Accusé de réception de l'initialisation (notification sans réponse)."""
    pass  # no-op, notifications n'ont pas d'id


def main() -> None:
    """Boucle principale stdin → dispatch → stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            send_error(None, -32700, f"Parse error: {e}")
            continue

        req_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        # Notifications (pas d'id, pas de réponse attendue)
        if req_id is None:
            if method == "notifications/initialized":
                handle_notifications_initialized(params)
            # Ignorer les autres notifications silencieusement
            continue

        # Requêtes
        if method == "initialize":
            handle_initialize(req_id, params)
        elif method == "tools/list":
            handle_tools_list(req_id)
        elif method == "tools/call":
            handle_tools_call(req_id, params)
        elif method == "ping":
            send_result(req_id, {})
        else:
            send_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
