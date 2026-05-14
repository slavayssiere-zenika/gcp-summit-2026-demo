#!/usr/bin/env python3
"""admin_helpers.py — Fonctions partagées pour l'admin CLI Zenika."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

_antigravity_env = Path(__file__).parent / ".antigravity_env"
if _antigravity_env.exists():
    for _line in _antigravity_env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

GCLOUD_BIN = os.getenv("GCLOUD_BIN", "gcloud")
TOKEN_TTL = 900  # 15 min

# Couleurs ANSI
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
GREY = "\033[90m"
MAGENTA = "\033[95m"


def c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


def banner(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{BLUE}── {title} {'─' * (55 - len(title))}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✅{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠️ {RESET} {msg}")


def err(msg: str) -> None:
    print(f"  {RED}❌{RESET} {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"  {CYAN}ℹ️ {RESET} {msg}")


def progress_bar(pct: int, width: int = 30) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    color = GREEN if pct >= 80 else YELLOW if pct >= 50 else RED
    return f"{color}[{bar}]{RESET} {pct:3d}%"


def grade_color(grade: str) -> str:
    colors = {"A": GREEN, "B": CYAN, "C": YELLOW, "D": RED}
    return c(colors.get(grade, RESET), f"[{grade}]")


def status_icon(status: str) -> str:
    icons = {
        "idle": "💤", "running": "🔄", "building": "🏗️",
        "batch_running": "⚙️", "applying": "📥", "completed": "✅",
        "error": "❌", "cancelled": "🚫", "ok": "✅",
        "warning": "⚠️", "critical": "🔴", "healthy": "✅",
        "unhealthy": "❌", "degraded": "⚠️",
    }
    return icons.get(status, "❓")


def print_kv(key: str, value, width: int = 28) -> None:
    print(f"  {GREY}{key:<{width}}{RESET}: {value}")


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_env_config(env: str) -> dict:
    """Retourne BASE_URL, GCP_PROJECT, secret_name selon l'environnement."""
    envs = {
        "prd": {
            "base_url": os.getenv("ZENIKA_BASE_URL", "https://prd.zenika.slavayssiere.fr"),
            "project": os.getenv("ZENIKA_GCP_PROJECT", "prod-ia-staffing"),
            "secret": "admin-password-prd",
        },
        "uat": {
            "base_url": os.getenv("ZENIKA_UAT_URL", "https://uat.zenika.slavayssiere.fr"),
            "project": os.getenv("ZENIKA_GCP_PROJECT_UAT", "prod-ia-staffing"),
            "secret": "admin-password-uat",
        },
        "dev": {
            "base_url": os.getenv("ZENIKA_DEV_URL", "https://dev.zenika.slavayssiere.fr"),
            "project": os.getenv("ZENIKA_GCP_PROJECT_DEV", "prod-ia-staffing"),
            "secret": "admin-password-dev",
        },
    }
    return envs.get(env, envs["prd"])


def _gcloud_admin_password(project: str, secret_name: str) -> str:
    result = subprocess.run(
        [GCLOUD_BIN, "secrets", "versions", "access", "latest",
         f"--secret={secret_name}", f"--project={project}"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    err(f"Secret '{secret_name}' introuvable dans '{project}'.")
    sys.exit(1)


def get_jwt(env: str = "prd", no_cache: bool = False) -> tuple[str, str]:
    """Retourne (jwt_token, base_url) pour l'environnement donné."""
    cfg = get_env_config(env)
    base_url = cfg["base_url"]
    token_cache = Path.home() / ".cache" / f"zenika_admin_cli_{env}.json"

    if not no_cache and token_cache.exists():
        try:
            json.loads(token_cache.read_text())
            # On laisse le check par sécurité, mais on force no_cache=True par défaut plus tard
            # ou on désactive juste la lecture du cache.
            # L'utilisateur a demandé "reforge le token a chaque fois que je lance le script".
            pass  # Ignorer le cache en lecture pour forcer un nouveau login à chaque exécution
        except Exception:
            pass

    admin_email = os.getenv("ZENIKA_ADMIN_EMAIL", "admin@zenika.com")
    password = _gcloud_admin_password(cfg["project"], cfg["secret"])

    info(f"Authentification sur {base_url} ({admin_email})…")
    try:
        resp = httpx.post(
            f"{base_url}/auth/login",
            json={"email": admin_email, "password": password},
            timeout=15.0,
        )
    except Exception as e:
        err(f"Connexion impossible : {e}")
        sys.exit(1)

    if resp.status_code != 200:
        err(f"Login échoué [{resp.status_code}]: {resp.text[:300]}")
        sys.exit(1)

    token = resp.json().get("access_token")
    if not token:
        err("Réponse login sans access_token.")
        sys.exit(1)

    token_cache.parent.mkdir(parents=True, exist_ok=True)
    token_cache.write_text(json.dumps({
        "token": token,
        "expires_at": time.time() + TOKEN_TTL,
    }))
    ok(f"Token JWT obtenu et mis en cache ({env}).")
    return token, base_url


# ── Appels API ─────────────────────────────────────────────────────────────────

def api_get(base_url: str, path: str, token: str, params: dict | None = None) -> dict | None:
    try:
        resp = httpx.get(
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=20.0,
        )
        if resp.status_code == 403:
            err(f"Accès refusé (403) sur {path}")
            return None
        if resp.status_code >= 400:
            err(f"HTTP {resp.status_code} sur {path}: {resp.text[:200]}")
            return None
        return resp.json()
    except Exception as e:
        err(f"Erreur réseau {path}: {e}")
        return None


def api_post(base_url: str, path: str, token: str,
             body: dict | None = None, params: dict | None = None) -> dict | None:
    try:
        resp = httpx.post(
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body or {},
            params=params or {},
            timeout=30.0,
        )
        if resp.status_code == 403:
            err(f"Accès refusé (403) sur {path}")
            return None
        if resp.status_code >= 400:
            err(f"HTTP {resp.status_code} sur {path}: {resp.text[:300]}")
            return None
        return resp.json()
    except Exception as e:
        err(f"Erreur réseau {path}: {e}")
        return None


def api_delete(base_url: str, path: str, token: str, params: dict | None = None) -> dict | None:
    try:
        resp = httpx.delete(
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=20.0,
        )
        if resp.status_code >= 400:
            err(f"HTTP {resp.status_code} sur {path}: {resp.text[:200]}")
            return None
        return resp.json()
    except Exception as e:
        err(f"Erreur réseau {path}: {e}")
        return None


# ── Affichage statuts ──────────────────────────────────────────────────────────

def print_bulk_status(data: dict) -> None:
    """Affiche le statut d'un pipeline bulk (cv ou scoring)."""
    if not data:
        warn("Aucun statut disponible.")
        return
    status = data.get("status", "?")
    icon = status_icon(status)
    print(f"\n  {icon} Status : {BOLD}{status}{RESET}")

    for key in ["total_cvs", "total_users", "processed", "applied", "errors", "percent"]:
        if key in data:
            print_kv(key, data[key])

    if data.get("completion_stats"):
        cs = data["completion_stats"]
        pct = cs.get("percent", 0)
        print(f"\n  Vertex AI: {progress_bar(pct)}")
        print_kv("  completed", cs.get("completed", "?"))
        print_kv("  failed", cs.get("failed", "?"))

    if data.get("vertex_state"):
        print_kv("vertex_state", data["vertex_state"])
    if data.get("batch_job_id"):
        print_kv("batch_job_id", data["batch_job_id"][-20:] + "…")
    if data.get("dest_uri"):
        print_kv("dest_uri (GCS)", data.get("dest_uri", "")[-40:] + "…")
    if data.get("error"):
        err(f"Erreur: {data['error'][:150]}")
    logs = data.get("logs", [])
    if logs:
        section("Derniers logs")
        for line in logs[-5:]:
            print(f"  {GREY}• {line[:120]}{RESET}")


def print_drive_status(data: dict) -> None:
    if not data:
        return
    total = data.get("total_files_scanned", 0)
    imp = data.get("imported", 0)
    errs = data.get("errors", 0)
    pend = data.get("pending", 0)
    proc = data.get("processing", 0)
    ign = data.get("ignored", 0)
    queued = data.get("queued", 0)

    pct = round(imp / total * 100, 1) if total else 0
    print(f"\n  {progress_bar(int(pct))}  ({imp}/{total} importés)")
    print()
    print_kv("Total scannés", total)
    print_kv("Importés", f"{GREEN}{imp}{RESET}")
    print_kv("En attente", f"{YELLOW}{pend}{RESET}")
    print_kv("En queue", f"{YELLOW}{queued}{RESET}")
    print_kv("En traitement", f"{CYAN}{proc}{RESET}")
    print_kv("Ignorés", ign)
    print_kv("Erreurs", f"{RED}{errs}{RESET}" if errs else "0")
    if data.get("last_processed_time"):
        print_kv("Dernière activité", data["last_processed_time"])


def print_data_quality(data: dict) -> None:
    if not data:
        warn("Data quality non disponible.")
        return
    score = data.get("score", 0)
    grade = data.get("grade", "?")
    print(f"\n  Score global : {BOLD}{score}/100{RESET}  {grade_color(grade)}")
    print(f"  Barre        : {progress_bar(score)}\n")

    for metric_name, metric in data.get("metrics", {}).items():
        pct = metric.get("pct", 0)
        ok_v = metric.get("ok", 0)
        total = metric.get("total", 0)
        icon = "✅" if pct >= 80 else "⚠️" if pct >= 50 else "❌"
        print(f"  {icon} {metric_name:<28}: {pct:.1f}%  ({ok_v}/{total})")

    issues = data.get("issues", [])
    if issues:
        print()
        for issue in issues:
            warn(issue)
