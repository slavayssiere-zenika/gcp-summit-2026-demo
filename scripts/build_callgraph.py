#!/usr/bin/env python3
"""
build_callgraph.py — Analyse statique AST Python → Neo4j

Construit le graphe d'appel de tous les services applicatifs
(hors platform-engineering et terraform) et l'injecte dans Neo4j.

Usage:
    python3 scripts/build_callgraph.py [--clear] [--dry-run]

Options:
    --clear     Vide le graphe Neo4j avant ingestion (défaut: True)
    --no-clear  Ne vide pas le graphe avant ingestion
    --dry-run   Analyse uniquement, sans écriture Neo4j
    --no-tests  Exclut les fichiers de tests (tests/, conftest.py)

Env vars:
    NEO4J_URI       (défaut: bolt://localhost:7687)
    NEO4J_USER      (défaut: neo4j)
    NEO4J_PASSWORD  (défaut: password)
"""

import argparse
import ast
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# ───────────────────────────── Configuration ─────────────────────────────

ROOT = Path(__file__).parent.parent  # racine du projet

SERVICES = [
    "users_api",
    "items_api",
    "competencies_api",
    "cv_api",
    "missions_api",
    "drive_api",
    "prompts_api",
    "analytics_mcp",
    "monitoring_mcp",
    "agent_commons",
    "agent_hr_api",
    "agent_ops_api",
    "agent_router_api",
    "agent_missions_api",
    "shared",
    "platform-engineering",
]

EXCLUDE_DIRS = {
    ".venv", "venv", "__pycache__", ".pytest_cache", ".hypothesis",
    "node_modules", ".git", ".tox", "dist", "build", "site-packages",
}

# Chaînes à chercher dans le chemin absolu pour exclusion rapide
EXCLUDE_PATH_SUBSTRINGS = [
    "/.venv/", "/venv/", "/__pycache__/", "/.pytest_cache/",
    "/site-packages/", "/dist-packages/",
]

# Mapping variable d'env d'URL → nom du service cible
URL_ENV_TO_SERVICE = {
    "USERS_API_URL": "users_api",
    "USERS_MCP_URL": "users_api",
    "ITEMS_MCP_URL": "items_api",
    "ITEMS_API_URL": "items_api",
    "COMPETENCIES_MCP_URL": "competencies_api",
    "COMPETENCIES_API_URL": "competencies_api",
    "CV_MCP_URL": "cv_api",
    "CV_API_URL": "cv_api",
    "DRIVE_MCP_URL": "drive_api",
    "DRIVE_API_URL": "drive_api",
    "MISSIONS_MCP_URL": "missions_api",
    "MISSIONS_API_URL": "missions_api",
    "ANALYTICS_MCP_URL": "analytics_mcp",
    "MONITORING_MCP_URL": "monitoring_mcp",
    "AGENT_HR_API_URL": "agent_hr_api",
    "AGENT_OPS_API_URL": "agent_ops_api",
    "AGENT_MISSIONS_API_URL": "agent_missions_api",
    "PROMPTS_API_URL": "prompts_api",
}

# Patterns de décorateurs MCP (avec ou sans parenthèses d'appel)
# ast.unparse retourne "server.call_tool()" avec les parenthèses
MCP_TOOL_DECORATOR_PATTERNS = [
    "server.call_tool",
    "server.list_tools",
    "mcp.tool",
    ".tool(",          # @mcp.tool() → "mcp.tool()"
    "@tool",           # @tool
]

# Patterns de décorateurs FastAPI indiquant un endpoint HTTP
FASTAPI_DECORATORS = {
    "router.get", "router.post", "router.put", "router.delete", "router.patch",
    "app.get", "app.post", "app.put", "app.delete", "app.patch",
    "protected_router.get", "protected_router.post", "protected_router.put",
    "protected_router.delete", "protected_router.patch",
    "public_router.get", "public_router.post",
}

# Patterns de noms de fonctions/calls HTTP à détecter
HTTP_CALL_PATTERNS = {
    "httpx.get", "httpx.post", "httpx.put", "httpx.delete", "httpx.patch", "httpx.request",
    "client.get", "client.post", "client.put", "client.delete", "client.patch", "client.request",
}

# Builtins et helpers à ignorer pour les arêtes CALLS
IGNORE_CALL_NAMES = {
    "get", "post", "put", "delete", "patch", "append", "run", "execute",
    "format", "encode", "decode", "items", "keys", "values", "split", "join",
    "model_validate", "model_dump", "json", "close", "open", "read", "write",
    "print", "isinstance", "hasattr", "getattr", "setattr", "len", "str",
    "int", "list", "dict", "set", "tuple", "bool", "Exception", "ValueError",
    "TypeError", "KeyError", "AttributeError", "RuntimeError", "HTTPException",
    "raise_for_status", "status_code", "text", "content", "headers",
    "logger", "info", "warning", "error", "debug", "critical",
    "next", "iter", "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "any", "all", "sum", "min", "max", "abs", "round",
}

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


# ───────────────────────────── AST Helpers ─────────────────────────────

def get_decorator_names(node: ast.FunctionDef) -> list:
    """
    Extrait les noms unparsés des décorateurs d'un FunctionDef.
    Retourne le nom de la fonction (sans arguments) pour les Call decorators.

    Ex: @router.get("/users") → "router.get"
        @mcp.tool()           → "mcp.tool"
        @server.call_tool()   → "server.call_tool"
        @Depends(verify_jwt)  → "Depends"
    """
    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            # @router.get("/users") → extraire "router.get" (sans les args)
            try:
                decorators.append(ast.unparse(dec.func))
            except Exception:
                pass
        else:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                pass
    return decorators


def classify_function(decorators: list) -> tuple:
    """Retourne (is_endpoint, is_mcp_tool) selon les décorateurs."""
    is_ep = any(d in FASTAPI_DECORATORS for d in decorators)
    is_mcp = any(
        any(pat in d for pat in MCP_TOOL_DECORATOR_PATTERNS)
        for d in decorators
    )
    return is_ep, is_mcp


def extract_calls_from_body(body: list) -> list:
    """
    Extrait tous les noms de fonctions appelées dans un bloc de code.
    Retourne des noms simples ('verify_jwt') ou qualifiés ('httpx.get').
    """
    calls = []
    wrapper = ast.Module(body=body, type_ignores=[])
    for node in ast.walk(wrapper):
        if isinstance(node, ast.Call):
            try:
                func_str = ast.unparse(node.func)
                calls.append(func_str)
            except Exception:
                pass
    return calls


def extract_calls_from_signature(args: ast.arguments) -> list:
    """
    Extrait les appels présents dans les valeurs par défaut de la signature de fonction.
    Ex: payload: dict = Depends(verify_jwt) -> ajoute 'Depends' et 'verify_jwt'
    """
    calls = []
    defaults = args.defaults + [d for d in args.kw_defaults if d is not None]
    for expr in defaults:
        for node in ast.walk(expr):
            if isinstance(node, ast.Call):
                try:
                    func_str = ast.unparse(node.func)
                    calls.append(func_str)
                    if func_str == "Depends" and node.args:
                        calls.append(ast.unparse(node.args[0]))
                except Exception:
                    pass
    return calls


def detect_http_calls(body: list) -> list:
    """
    Détecte les appels HTTP (httpx/requests) et résout le service cible
    via les variables d'env d'URL référencées dans l'appel.

    Retourne: liste de (method, target_service_name)
    """
    results = []
    wrapper = ast.Module(body=body, type_ignores=[])

    # Traçage des assignations de variables d'environnement locales
    # Ex: hr_url = os.getenv("AGENT_HR_API_URL")
    env_to_local = {}
    for subnode in ast.walk(wrapper):
        if isinstance(subnode, ast.Assign) and len(subnode.targets) == 1:
            target = subnode.targets[0]
            if isinstance(target, ast.Name):
                var_name = target.id
                try:
                    val_str = ast.unparse(subnode.value)
                except Exception:
                    continue
                for env_var in URL_ENV_TO_SERVICE.keys():
                    if env_var in val_str:
                        env_to_local[var_name] = env_var

    for node in ast.walk(wrapper):
        if not isinstance(node, ast.Call):
            continue

        try:
            func_str = ast.unparse(node.func)
            call_str = ast.unparse(node)
        except Exception:
            continue

        # Vérifier si c'est un appel HTTP connu
        is_http = any(pat in func_str for pat in HTTP_CALL_PATTERNS)
        if not is_http:
            for m in ("get", "post", "put", "delete", "patch", "request"):
                has_env = any(k in call_str for k in URL_ENV_TO_SERVICE)
                has_local = any(v in call_str for v in env_to_local.keys())
                if f".{m}(" in call_str and (has_env or has_local):
                    is_http = True
                    break

        if not is_http:
            continue

        # Déterminer la méthode HTTP
        method = "UNKNOWN"
        for m in ("get", "post", "put", "delete", "patch", "request"):
            if f".{m}" in func_str:
                method = m.upper()
                break

        # Chercher une variable d'env d'URL dans l'appel complet (direct ou via variable locale)
        resolved = False
        for env_var, service_name in URL_ENV_TO_SERVICE.items():
            if env_var in call_str:
                results.append((method, service_name))
                resolved = True
                break

        if not resolved:
            import re  # noqa: PLC0415
            for var_name, env_var in env_to_local.items():
                if re.search(r'\b' + re.escape(var_name) + r'\b', call_str):
                    results.append((method, URL_ENV_TO_SERVICE[env_var]))
                    break

    return results


def extract_imports(tree: ast.AST) -> dict:
    """
    Extrait tous les imports: alias → module complet.
    Ex: 'from shared.auth.jwt import verify_jwt'
        → {'verify_jwt': 'shared.auth.jwt.verify_jwt'}
    """
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                key = alias.asname or alias.name
                imports[key] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                key = alias.asname or alias.name
                imports[key] = f"{module}.{alias.name}" if module else alias.name
    return imports


def detect_external_calls(tree: ast.AST, imports: dict) -> tuple[list[str], list[str]]:
    """
    Analyse l'arbre AST d'un module et ses imports pour détecter
    les dépendances aux bases de données et services Google externes.
    """
    has_alloydb = False
    has_redis = False
    has_bq = False
    has_gemini = False
    has_drive = False
    has_oauth = False

    # 1. Analyse des modules importés
    for val in imports.values():
        val_lower = val.lower()
        if any(kw in val_lower for kw in ["sqlalchemy", "psycopg2", "asyncpg", "shared.db"]):
            has_alloydb = True
        if any(kw in val_lower for kw in ["redis", "shared.redis_state"]):
            has_redis = True
        if "bigquery" in val_lower:
            has_bq = True
        if any(kw in val_lower for kw in ["google.genai", "google.generativeai", "genai", "litellm"]):
            has_gemini = True
        if "drive_api" in val_lower:
            has_drive = True
        if any(kw in val_lower for kw in ["oauth2", "google.oauth2"]):
            has_oauth = True

    # 2. Analyse des noms de variables, fonctions et appels
    for node in ast.walk(tree):
        # Noms de symboles / variables
        if isinstance(node, ast.Name):
            nid = node.id
            if nid in ["SessionLocal", "get_db", "engine", "Base"]:
                has_alloydb = True
            if nid in ["Redis", "get_state_redis_client", "redis_client", "RedisInstrumentor"]:
                has_redis = True
            if nid in ["GenerativeModel", "Gemini", "genai"]:
                has_gemini = True
        # Appels explicites
        elif isinstance(node, ast.Call):
            try:
                func_str = ast.unparse(node.func)
            except Exception:
                continue

            # build("drive", ...)
            if func_str == "build" and node.args:
                try:
                    first_arg = ast.unparse(node.args[0])
                    if "drive" in first_arg:
                        has_drive = True
                except Exception:
                    pass

    db_calls = []
    if has_alloydb:
        db_calls.append("AlloyDB")
    if has_redis:
        db_calls.append("Redis")
    if has_bq:
        db_calls.append("BigQuery")

    google_calls = []
    if has_gemini:
        google_calls.append("Gemini API")
    if has_drive:
        google_calls.append("Google Drive API")
    if has_oauth:
        google_calls.append("Google OAuth")

    return db_calls, google_calls


# ───────────────────────────── File Parser ─────────────────────────────

def module_name_from_path(filepath: Path, service: str) -> str:
    """
    Calcule le nom de module Python à partir du chemin relatif au service.
    Ex: users_api/src/users/auth_router.py → src.users.auth_router
    """
    service_root = ROOT / service
    try:
        rel = filepath.relative_to(service_root)
        return str(rel).replace(os.sep, ".").removesuffix(".py")
    except ValueError:
        return filepath.stem


def parse_file(filepath: Path, service: str) -> Optional[dict]:
    """
    Parse un fichier Python et extrait les fonctions, appels et appels HTTP.
    Retourne None en cas d'erreur de parsing.
    """
    rel_path = str(filepath.relative_to(ROOT))
    module = module_name_from_path(filepath, service)

    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError) as exc:
        print(f"  ⚠️  Parse error dans {rel_path}: {exc}")
        return None

    imports = extract_imports(tree)
    db_calls, google_calls = detect_external_calls(tree, imports)
    functions = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        decorators = get_decorator_names(node)
        is_ep, is_mcp = classify_function(decorators)
        raw_calls = extract_calls_from_body(node.body)
        raw_calls.extend(extract_calls_from_signature(node.args))
        http_calls = detect_http_calls(node.body)

        functions.append({
            "name": node.name,
            "module": module,
            "service": service,
            "filepath": rel_path,
            "line": node.lineno,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "is_endpoint": is_ep,
            "is_mcp_tool": is_mcp,
            "decorators": decorators,
            "raw_calls": raw_calls,
            "http_calls": http_calls,
            "imports": imports,
        })

    return {
        "filepath": rel_path,
        "module": module,
        "service": service,
        "functions": functions,
        "db_calls": db_calls,
        "google_calls": google_calls,
    }


def collect_files(service: str, include_tests: bool = True) -> list:
    """Collecte tous les fichiers .py d'un service."""
    service_dir = ROOT / service
    if not service_dir.exists():
        return []

    exclude_names = EXCLUDE_DIRS.copy()
    if not include_tests:
        exclude_names.add("tests")

    files = []
    for py_file in service_dir.rglob("*.py"):
        # Vérification 1 : extension explicite (évite les symlinks .db etc.)
        if py_file.suffix != ".py":
            continue

        # Vérification 2 : composants du chemin (directory names)
        parts = set(py_file.parts)
        if parts & exclude_names:
            continue

        # Vérification 3 : substring du chemin absolu (catch les cas bords)
        abs_str = str(py_file)
        if any(sub in abs_str for sub in EXCLUDE_PATH_SUBSTRINGS):
            continue

        if not include_tests and py_file.name == "conftest.py":
            continue

        files.append(py_file)

    return sorted(files)


# ───────────────────────────── Identifiant ─────────────────────────────

def func_id(service: str, module: str, name: str) -> str:
    """Identifiant unique d'une fonction dans Neo4j."""
    return f"{service}::{module}::{name}"


# ───────────────────────────── Neo4j Ingestion ─────────────────────────────

CYPHER_CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Module) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (f:Function) REQUIRE f.id IS UNIQUE",
]

CYPHER_INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (f:Function) ON (f.name)",
    "CREATE INDEX IF NOT EXISTS FOR (f:Function) ON (f.is_endpoint)",
    "CREATE INDEX IF NOT EXISTS FOR (f:Function) ON (f.is_mcp_tool)",
    "CREATE INDEX IF NOT EXISTS FOR (f:Function) ON (f.service)",
]


def ingest(driver, all_modules: list, clear: bool = True) -> None:
    """Ingère tous les modules parsés dans Neo4j."""

    with driver.session() as session:

        if clear:
            print("🗑️  Suppression du graphe existant...")
            session.run("MATCH (n) DETACH DELETE n")

        print("🔧 Création des contraintes et index...")
        for cypher in CYPHER_CONSTRAINTS + CYPHER_INDEXES:
            session.run(cypher)

        # ── Phase 1 : Créer tous les nœuds ────────────────────────────────
        print("📦 Création des nœuds Service / Module / Function...")

        name_to_fids: dict = defaultdict(list)  # nom_fonction → [func_id, ...]
        all_fids: dict = {}  # func_id → func_data

        for module_data in all_modules:
            svc = module_data["service"]
            mod = module_data["module"]
            fp = module_data["filepath"]

            session.run("MERGE (s:Service {name: $name})", name=svc)

            mid = f"{svc}::{mod}"
            session.run(
                """
                MERGE (m:Module {id: $id})
                SET m.name = $name, m.service = $svc, m.filepath = $fp
                """,
                id=mid, name=mod, svc=svc, fp=fp,
            )
            session.run(
                """
                MATCH (s:Service {name: $svc}), (m:Module {id: $mid})
                MERGE (s)-[:CONTAINS]->(m)
                """,
                svc=svc, mid=mid,
            )

            for func in module_data["functions"]:
                fid = func_id(svc, mod, func["name"])
                session.run(
                    """
                    MERGE (f:Function {id: $id})
                    SET f.name        = $name,
                        f.module      = $mod,
                        f.service     = $svc,
                        f.filepath    = $fp,
                        f.line        = $line,
                        f.is_async    = $is_async,
                        f.is_endpoint = $is_ep,
                        f.is_mcp_tool = $is_mcp,
                        f.decorators  = $decs
                    """,
                    id=fid, name=func["name"], mod=mod, svc=svc,
                    fp=func["filepath"], line=func["line"],
                    is_async=func["is_async"], is_ep=func["is_endpoint"],
                    is_mcp=func["is_mcp_tool"], decs=func["decorators"],
                )
                session.run(
                    """
                    MATCH (m:Module {id: $mid}), (f:Function {id: $fid})
                    MERGE (m)-[:DEFINES]->(f)
                    """,
                    mid=mid, fid=fid,
                )
                name_to_fids[func["name"]].append(fid)
                all_fids[fid] = func

        # ── Phase 2 : Arêtes CALLS (appels de fonctions) ──────────────────
        print("🔗 Création des arêtes CALLS (appels de fonctions)...")

        calls_created = 0
        calls_skipped = 0

        for module_data in all_modules:
            svc = module_data["service"]
            mod = module_data["module"]

            for func in module_data["functions"]:
                caller_fid = func_id(svc, mod, func["name"])

                for called in set(func["raw_calls"]):
                    # Extraire le nom simple (dernière partie pour les attributs)
                    simple_name = called.split(".")[-1]

                    # Ignorer les builtins et patterns non pertinents
                    if simple_name in IGNORE_CALL_NAMES:
                        calls_skipped += 1
                        continue

                    candidates = name_to_fids.get(simple_name, [])
                    if not candidates:
                        calls_skipped += 1
                        continue

                    # Préférer même module, puis même service
                    same_mod = [c for c in candidates if c.startswith(f"{svc}::{mod}::")]
                    same_svc = [c for c in candidates if c.startswith(f"{svc}::")]
                    targets = same_mod or same_svc or candidates

                    for target_fid in targets[:5]:  # limiter pour éviter explosion
                        if target_fid == caller_fid:
                            continue  # pas d'auto-appel
                        session.run(
                            """
                            MATCH (a:Function {id: $from_id}), (b:Function {id: $to_id})
                            MERGE (a)-[:CALLS]->(b)
                            """,
                            from_id=caller_fid, to_id=target_fid,
                        )
                        calls_created += 1

        print(f"   ✅ {calls_created} arêtes CALLS, {calls_skipped} ignorées")

        # ── Phase 3 : Arêtes HTTP_CALLS (inter-services) ──────────────────
        print("🌐 Création des arêtes HTTP_CALLS (inter-services)...")

        http_created = 0
        for module_data in all_modules:
            svc = module_data["service"]
            mod = module_data["module"]

            for func in module_data["functions"]:
                caller_fid = func_id(svc, mod, func["name"])

                for method, target_svc in set(func["http_calls"]):
                    if target_svc == svc:
                        continue  # ignorer les auto-appels
                    session.run("MERGE (s:Service {name: $name})", name=target_svc)
                    session.run(
                        """
                        MATCH (f:Function {id: $fid}), (s:Service {name: $svc})
                        MERGE (f)-[r:HTTP_CALLS]->(s)
                        SET r.method = $method
                        """,
                        fid=caller_fid, svc=target_svc, method=method,
                    )
                    http_created += 1

        print(f"   ✅ {http_created} arêtes HTTP_CALLS")

        # ── Phase 4 : Vue macro SERVICE_CALLS ─────────────────────────────
        print("📊 Création des arêtes SERVICE_CALLS (niveau macro)...")
        session.run("""
            MATCH (src:Service)-[:CONTAINS]->(:Module)-[:DEFINES]->(f:Function)
                  -[:HTTP_CALLS]->(tgt:Service)
            WHERE src.name <> tgt.name
            MERGE (src)-[:SERVICE_CALLS]->(tgt)
        """)

        # ── Ingestion Pub/Sub, Databases & Google Services (Statiques) ─────
        print("🔌 Création des topics Pub/Sub et des flux asynchrones...")
        session.run("""
            MERGE (t1:PubSubTopic {name: 'cv-import-events'})
            MERGE (t2:PubSubTopic {name: 'user-events'})
            MERGE (t3:PubSubTopic {name: 'data-quality-snapshot'})

            MERGE (s_drive:Service {name: 'drive_api'})
            MERGE (s_drive)-[:PUBLISHES_TO]->(t1)

            MERGE (s_cv:Service {name: 'cv_api'})
            MERGE (s_cv)-[:SUBSCRIBES_TO {endpoint: '/pubsub/import-cv'}]->(t1)

            MERGE (s_users:Service {name: 'users_api'})
            MERGE (s_users)-[:PUBLISHES_TO]->(t2)

            MERGE (s_comp:Service {name: 'competencies_api'})
            MERGE (s_cv)-[:SUBSCRIBES_TO {endpoint: '/pubsub/user-events'}]->(t2)
            MERGE (s_comp)-[:SUBSCRIBES_TO {endpoint: '/pubsub/user-events'}]->(t2)

            MERGE (s_cv)-[:SUBSCRIBES_TO {endpoint: '/pubsub/data-quality-snapshot'}]->(t3)
        """)

        print("🗄️ Création des bases de données et services Google de base...")
        session.run("""
            MERGE (db_alloy:Database {name: 'AlloyDB'})
            MERGE (db_redis:Database {name: 'Redis'})
            MERGE (db_bq:Database {name: 'BigQuery'})
            MERGE (g_gemini:GoogleService {name: 'Gemini API'})
            MERGE (g_drive:GoogleService {name: 'Google Drive API'})
            MERGE (g_oauth:GoogleService {name: 'Google OAuth'})
        """)

        # Création des liaisons statiques détectées par AST
        print("📊 Liaison dynamique des bases de données et services Google via AST...")
        for module_data in all_modules:
            svc = module_data["service"]
            for db in module_data.get("db_calls", []):
                session.run("""
                    MATCH (s:Service {name: $svc})
                    MATCH (db:Database {name: $db})
                    MERGE (s)-[:USES_DB]->(db)
                """, svc=svc, db=db)
            for gsvc in module_data.get("google_calls", []):
                session.run("""
                    MATCH (s:Service {name: $svc})
                    MATCH (g:GoogleService {name: $gsvc})
                    MERGE (s)-[:CALLS_GOOGLE]->(g)
                """, svc=svc, gsvc=gsvc)

        # ── Stats ──────────────────────────────────────────────────────────
        print()
        print("📈 Statistiques du graphe :")
        result = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC"
        )
        for rec in result:
            print(f"   {rec['label']}: {rec['cnt']} nœuds")

        result = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt ORDER BY cnt DESC"
        )
        for rec in result:
            print(f"   [{rec['rel']}]: {rec['cnt']} relations")


# ───────────────────────────── Dry Run ─────────────────────────────

def dry_run_report(all_modules: list) -> None:
    """Affiche un rapport sans écrire dans Neo4j."""
    total_funcs = sum(len(m["functions"]) for m in all_modules)
    total_http = sum(
        len(f["http_calls"])
        for m in all_modules
        for f in m["functions"]
    )
    endpoints = [f for m in all_modules for f in m["functions"] if f["is_endpoint"]]
    mcp_tools = [f for m in all_modules for f in m["functions"] if f["is_mcp_tool"]]

    print("\n📊 Rapport (dry-run)")
    print(f"   Modules parsés       : {len(all_modules)}")
    print(f"   Fonctions totales    : {total_funcs}")
    print(f"   Endpoints HTTP       : {len(endpoints)}")
    print(f"   Tools MCP            : {len(mcp_tools)}")
    print(f"   Appels HTTP sortants : {total_http}")
    print()

    print("   Endpoints par service :")
    by_svc: dict = defaultdict(int)
    for f in endpoints:
        by_svc[f["service"]] += 1
    for svc, cnt in sorted(by_svc.items(), key=lambda x: -x[1]):
        print(f"     {svc}: {cnt}")

    print()
    print("   Appels HTTP inter-services détectés :")
    http_edges: set = set()
    for m in all_modules:
        for f in m["functions"]:
            for method, target in f["http_calls"]:
                http_edges.add((m["service"], method, target))
    for src, method, tgt in sorted(http_edges):
        print(f"     {src} --[{method}]--> {tgt}")


# ───────────────────────────── Main ─────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build Python call graph → Neo4j")
    parser.add_argument("--clear", action="store_true", default=True,
                        help="Vide le graphe avant ingestion (défaut)")
    parser.add_argument("--no-clear", dest="clear", action="store_false",
                        help="Ne vide pas le graphe")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyse uniquement, sans écriture Neo4j")
    parser.add_argument("--no-tests", action="store_true",
                        help="Exclut les fichiers de tests")
    args = parser.parse_args()

    print("🚀 Zenika Call Graph Builder")
    print(f"   Racine    : {ROOT}")
    print(f"   Services  : {', '.join(SERVICES)}")
    if not args.dry_run:
        print(f"   Neo4j     : {NEO4J_URI}")
    print(f"   Tests     : {'exclus' if args.no_tests else 'inclus'}")
    print()

    # ── Parsing ───────────────────────────────────────────────────────────
    all_modules = []
    include_tests = not args.no_tests

    for service in SERVICES:
        service_dir = ROOT / service
        if not service_dir.exists():
            print(f"  ⏭️  {service} : répertoire introuvable, ignoré")
            continue

        files = collect_files(service, include_tests=include_tests)
        if not files:
            print(f"  ⏭️  {service} : aucun fichier Python")
            continue

        print(f"  📂 {service} : {len(files)} fichiers")
        for filepath in files:
            module_data = parse_file(filepath, service)
            if module_data:
                all_modules.append(module_data)

    total_funcs = sum(len(m["functions"]) for m in all_modules)
    print(f"\n✅ Parsé : {len(all_modules)} modules, {total_funcs} fonctions\n")

    if args.dry_run:
        dry_run_report(all_modules)
        return

    # ── Neo4j ─────────────────────────────────────────────────────────────
    try:
        from neo4j import GraphDatabase  # noqa: PLC0415
    except ImportError:
        print("❌ Le package 'neo4j' n'est pas installé.")
        print("   Installez-le avec: pip install neo4j")
        sys.exit(1)

    print("🔌 Connexion à Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print("✅ Connecté !\n")
        ingest(driver, all_modules, clear=args.clear)
        # Ingestion de l'infrastructure Terraform
        ingest_terraform_infrastructure(driver)
        # Ingestion des traces dynamiques
        traces_cache = ROOT / "scripts" / "traces_cache.json"
        ingest_dynamic_traces(driver, traces_cache)
    except Exception as exc:
        print(f"❌ Erreur Neo4j : {exc}")
        print("   Assurez-vous que Neo4j est démarré :")
        print("   docker compose up neo4j -d")
        sys.exit(1)
    finally:
        driver.close()

    print()
    print("🎉 Graphe construit avec succès !")
    print()
    print("── Requêtes Cypher utiles ────────────────────────────────────────")
    print()
    print("# Vue macro : quels services s'appellent ?")
    print("  MATCH (s1:Service)-[:SERVICE_CALLS]->(s2:Service)")
    print("  RETURN s1.name AS source, s2.name AS cible")
    print()
    print("# Tous les endpoints HTTP")
    print("  MATCH (f:Function {is_endpoint:true})")
    print("  RETURN f.service, f.name, f.filepath, f.line ORDER BY f.service")
    print()
    print("# Tous les tools MCP")
    print("  MATCH (f:Function {is_mcp_tool:true})")
    print("  RETURN f.service, f.name ORDER BY f.service")
    print()
    print("# Qui appelle verify_jwt ?")
    print("  MATCH (g:Function)-[:CALLS]->(f:Function {name:'verify_jwt'})")
    print("  RETURN g.service, g.name, g.filepath")
    print()
    print("# Fonctions les plus appelées (hotspots)")
    print("  MATCH (f:Function)<-[:CALLS]-(g)")
    print("  RETURN f.service, f.name, count(g) AS nb_appelants")
    print("  ORDER BY nb_appelants DESC LIMIT 20")
    print()
    print("Ouvrir Neo4j Browser : http://localhost:7474")


def ingest_dynamic_traces(driver, cache_file_path: Path):
    """
    Lit les traces en cache, extrait les appels dynamiques et les écrit dans Neo4j.
    """
    if not cache_file_path.exists():
        print("ℹ️ Aucun cache de traces dynamique trouvé. Ingestion dynamique ignorée.")
        return

    print("🔌 Ingestion des données dynamiques Cloud Trace...")
    try:
        with open(cache_file_path, "r", encoding="utf-8") as f:
            traces = json.load(f)
    except Exception as exc:
        print(f"⚠️ Impossible de lire le cache de traces : {exc}")
        return

    service_calls = defaultdict(lambda: {"count": 0, "total_latency": 0.0})
    func_calls = defaultdict(lambda: {"count": 0, "total_latency": 0.0})
    db_calls = defaultdict(lambda: {"count": 0, "total_latency": 0.0})
    google_calls = defaultdict(lambda: {"count": 0, "total_latency": 0.0})
    pubsub_calls = defaultdict(lambda: {"count": 0, "total_latency": 0.0})

    for trace in traces:
        spans = trace.get("spans", [])
        if not spans:
            continue

        spans_by_id = {}
        for span in spans:
            span_id = span.get("spanId")
            if span_id:
                spans_by_id[span_id] = span

        for span in spans:
            labels = span.get("labels", {})
            svc_name = None
            for svc in SERVICES:
                svc_dash = svc.replace("_", "-")
                fields_to_check = [
                    labels.get("g.co/runtimes/cloudrun/service_name"),
                    labels.get("service.name"),
                    labels.get("http.server_name"),
                    labels.get("/http/host"),
                    labels.get("cloud.resource_id")
                ]
                for val in fields_to_check:
                    if val and svc_dash in val:
                        svc_name = svc
                        break
                if svc_name:
                    break
            if svc_name:
                span["_service"] = svc_name

        def resolve_service(span):
            if "_service" in span:
                return span["_service"]
            parent_id = span.get("parentSpanId")
            if parent_id and parent_id in spans_by_id:
                svc = resolve_service(spans_by_id[parent_id])
                if svc:
                    span["_service"] = svc
                    return svc
            return None

        for span in spans:
            resolve_service(span)

        for span in spans:
            name = span.get("name", "")
            func_name = None
            labels = span.get("labels", {})
            route = labels.get("/http/route") or labels.get("/http/path")
            if route:
                segments = [s for s in route.split("/") if s and not s.startswith("{")]
                if segments:
                    func_name = segments[-1]
            if not func_name:
                if " " in name:
                    parts = name.split(" ")
                    if len(parts) > 1:
                        segments = [s for s in parts[1].split("/") if s]
                        if segments:
                            func_name = segments[-1]
                else:
                    func_name = name
            span["_func_name"] = func_name

        for span in spans:
            parent_id = span.get("parentSpanId")
            if not parent_id or parent_id not in spans_by_id:
                continue
            parent = spans_by_id[parent_id]
            svc_src = parent.get("_service")
            svc_tgt = span.get("_service")

            try:
                start_str = span.get("startTime", "").replace("Z", "+00:00")
                end_str = span.get("endTime", "").replace("Z", "+00:00")
                if start_str and end_str:
                    start_dt = datetime.fromisoformat(start_str)
                    end_dt = datetime.fromisoformat(end_str)
                    latency = (end_dt - start_dt).total_seconds() * 1000.0
                else:
                    latency = 0.0
            except Exception:
                latency = 0.0

            # Détection des bases de données et APIs Google
            labels = span.get("labels", {})
            db_system = labels.get("db.system")
            http_url = labels.get("/http/url", "")
            route = labels.get("/http/route") or labels.get("/http/path", "")
            span_name = span.get("name", "")

            # 1. Bases de données et BigQuery
            if db_system in ["postgresql", "redis", "BigQuery"] and svc_src:
                db_name = "AlloyDB" if db_system == "postgresql" else ("Redis" if db_system == "redis" else "BigQuery")
                key = (svc_src, db_name)
                db_calls[key]["count"] += 1
                db_calls[key]["total_latency"] += latency
                continue

            # 2. Pub/Sub (livraison par push)
            is_pubsub = False
            topic_name = None
            if route and "/pubsub/" in route:
                is_pubsub = True
                if "import-cv" in route:
                    topic_name = "cv-import-events"
                elif "user-events" in route:
                    topic_name = "user-events"
                elif "data-quality-snapshot" in route:
                    topic_name = "data-quality-snapshot"
            elif span_name and "/pubsub/" in span_name:
                is_pubsub = True
                if "import-cv" in span_name:
                    topic_name = "cv-import-events"
                elif "user-events" in span_name:
                    topic_name = "user-events"
                elif "data-quality-snapshot" in span_name:
                    topic_name = "data-quality-snapshot"

            if is_pubsub and topic_name and svc_tgt:
                key = (topic_name, svc_tgt)
                pubsub_calls[key]["count"] += 1
                pubsub_calls[key]["total_latency"] += latency
                continue

            # 3. Google Services
            if svc_src and ("googleapis.com" in http_url or "generativelanguage" in http_url):
                google_name = None
                if "generativelanguage" in http_url or "aiplatform" in http_url:
                    google_name = "Gemini API"
                elif "drive" in http_url:
                    google_name = "Google Drive API"
                elif "oauth2" in http_url:
                    google_name = "Google OAuth"

                if google_name:
                    key = (svc_src, google_name)
                    google_calls[key]["count"] += 1
                    google_calls[key]["total_latency"] += latency
                    continue

            # Appels inter-services classiques ou internes
            if not svc_src or not svc_tgt:
                continue

            if svc_src != svc_tgt:
                pair = (svc_src, svc_tgt)
                service_calls[pair]["count"] += 1
                service_calls[pair]["total_latency"] += latency
            else:
                func_src = parent.get("_func_name")
                func_tgt = span.get("_func_name")
                if func_src and func_tgt and func_src != func_tgt:
                    key = (svc_src, func_src, func_tgt)
                    func_calls[key]["count"] += 1
                    func_calls[key]["total_latency"] += latency

    with driver.session() as session:
        print(f"   ↳ Ingestion de {len(service_calls)} flux d'appels inter-services réels...")
        q_service = """
        MERGE (s1:Service {name: $src})
        MERGE (s2:Service {name: $tgt})
        MERGE (s1)-[r:DYNAMIC_SERVICE_CALLS]->(s2)
        SET r.count = toInteger($count),
            r.avg_latency_ms = toFloat($avg_latency)
        """
        for (src, tgt), stats in service_calls.items():
            avg_lat = stats["total_latency"] / stats["count"] if stats["count"] > 0 else 0.0
            session.run(q_service, src=src, tgt=tgt, count=stats["count"], avg_latency=avg_lat)

        print(f"   ↳ Ingestion de {len(db_calls)} flux d'appels de bases de données réels...")
        q_db = """
        MERGE (s:Service {name: $src})
        MERGE (d:Database {name: $tgt})
        MERGE (s)-[r:DYNAMIC_DB_CALL]->(d)
        SET r.count = toInteger($count),
            r.avg_latency_ms = toFloat($avg_latency)
        """
        for (src, tgt), stats in db_calls.items():
            avg_lat = stats["total_latency"] / stats["count"] if stats["count"] > 0 else 0.0
            session.run(q_db, src=src, tgt=tgt, count=stats["count"], avg_latency=avg_lat)

        print(f"   ↳ Ingestion de {len(google_calls)} flux d'appels de services Google réels...")
        q_google = """
        MERGE (s:Service {name: $src})
        MERGE (g:GoogleService {name: $tgt})
        MERGE (s)-[r:DYNAMIC_GOOGLE_CALL]->(g)
        SET r.count = toInteger($count),
            r.avg_latency_ms = toFloat($avg_latency)
        """
        for (src, tgt), stats in google_calls.items():
            avg_lat = stats["total_latency"] / stats["count"] if stats["count"] > 0 else 0.0
            session.run(q_google, src=src, tgt=tgt, count=stats["count"], avg_latency=avg_lat)

        print(f"   ↳ Ingestion de {len(pubsub_calls)} flux de messages Pub/Sub réels...")
        q_pubsub = """
        MERGE (t:PubSubTopic {name: $src})
        MERGE (s:Service {name: $tgt})
        MERGE (t)-[r:DYNAMIC_PUBSUB_CALL]->(s)
        SET r.count = toInteger($count),
            r.avg_latency_ms = toFloat($avg_latency)
        """
        for (src, tgt), stats in pubsub_calls.items():
            avg_lat = stats["total_latency"] / stats["count"] if stats["count"] > 0 else 0.0
            session.run(q_pubsub, src=src, tgt=tgt, count=stats["count"], avg_latency=avg_lat)

        print("   ↳ Ingestion des flux d'appels de fonctions réels...")
        q_func = """
        MATCH (f1:Function {service: $svc, name: $src_func})
        MATCH (f2:Function {service: $svc, name: $tgt_func})
        MERGE (f1)-[r:DYNAMIC_CALLS]->(f2)
        SET r.count = toInteger($count),
            r.avg_latency_ms = toFloat($avg_latency)
        """
        created_func_rels = 0
        for (svc, src_func, tgt_func), stats in func_calls.items():
            avg_lat = stats["total_latency"] / stats["count"] if stats["count"] > 0 else 0.0
            res = session.run(
                q_func,
                svc=svc,
                src_func=src_func,
                tgt_func=tgt_func,
                count=stats["count"],
                avg_latency=avg_lat
            )
            summary = res.consume()
            if summary.counters.relationships_created > 0 or summary.counters.properties_set > 0:
                created_func_rels += 1
        print(f"   ↳ {created_func_rels} relations de fonctions dynamiques insérées.")


def ingest_terraform_infrastructure(driver):
    """
    Parcourt le répertoire platform-engineering/terraform/ pour extraire
    les dépendances réelles déclarées par Terraform (fichiers HCL).
    """
    tf_dir = ROOT / "platform-engineering" / "terraform"
    if not tf_dir.exists():
        print("ℹ️ Répertoire Terraform introuvable. Ingestion Terraform ignorée.")
        return

    print("🏗️ Ingestion des liens d'infrastructure Terraform...")

    service_db_links = []       # (service_name, db_name)
    service_google_links = []   # (service_name, google_name)
    service_service_links = []  # (src_service, tgt_service)

    import re  # noqa: PLC0415
    for tf_file in tf_dir.glob("cr_*.tf"):
        service_name = tf_file.stem.replace("cr_", "") + "_api"
        if service_name == "analytics_api":
            service_name = "analytics_mcp"
        elif service_name == "monitoring_api":
            service_name = "monitoring_mcp"

        try:
            content = tf_file.read_text(encoding="utf-8")
        except Exception:
            continue

        env_blocks = re.findall(r'env\s*\{([^}]+)\}', content)
        for env in env_blocks:
            env_name_match = re.search(r'name\s*=\s*"([^"]+)"', env)
            if not env_name_match:
                continue
            env_name = env_name_match.group(1)

            env_val = ""
            val_match = re.search(r'value\s*=\s*"([^"]+)"', env)
            if val_match:
                env_val = val_match.group(1)
            else:
                val_source_match = re.search(r'secret\s*=\s*data\.google_secret_manager_secret\.([^.\s]+)', env)
                if val_source_match:
                    env_val = val_source_match.group(1)

            if env_name in ["DATABASE_URL", "ALLOYDB_INSTANCE_URI"] or "alloydb" in env_val.lower():
                service_db_links.append((service_name, "AlloyDB"))
            if env_name == "REDIS_URL" or "redis" in env_val.lower():
                service_db_links.append((service_name, "Redis"))

            if "gemini" in env_val.lower():
                service_google_links.append((service_name, "Gemini API"))
            if "drive" in env_val.lower() and service_name != "drive_api":
                service_google_links.append((service_name, "Google Drive API"))

            for env_var, tgt_service in URL_ENV_TO_SERVICE.items():
                if env_name == env_var or env_var in env:
                    service_service_links.append((service_name, tgt_service))

    pubsub_file = tf_dir / "pubsub.tf"
    topic_publisher_links = []  # (service_name, topic_name)
    topic_subscriber_links = []  # (topic_name, service_name, endpoint)

    if pubsub_file.exists():
        try:
            pubsub_content = pubsub_file.read_text(encoding="utf-8")

            publisher_blocks = re.findall(
                r'resource\s+"google_pubsub_topic_iam_member"\s+"[^"]+"[^}]+}',
                pubsub_content
            )
            for block in publisher_blocks:
                topic_match = re.search(r'topic\s*=\s*google_pubsub_topic\.([^.\s]+)', block)
                member_match = re.search(
                    r'member\s*=\s*"serviceAccount:\${(?:data\.)?google_service_account\.([^.\s]+)',
                    block
                )
                if topic_match and member_match:
                    topic_res = topic_match.group(1).replace("_", "-")
                    member_res = member_match.group(1).replace("_sa", "_api")
                    if member_res == "analytics_api":
                        member_res = "analytics_mcp"
                    elif member_res == "monitoring_api":
                        member_res = "monitoring_mcp"
                    topic_publisher_links.append((member_res, topic_res))

            sub_blocks = re.findall(
                r'resource\s+"google_pubsub_subscription"\s+"[^"]+"[^}]+push_config[^}]+}',
                pubsub_content
            )
            for block in sub_blocks:
                topic_match = re.search(r'topic\s*=\s*google_pubsub_topic\.([^.\s]+)', block)
                endpoint_match = re.search(r'push_endpoint\s*=\s*"([^"]+)"', block)
                if topic_match and endpoint_match:
                    topic_res = topic_match.group(1).replace("_", "-")
                    endpoint = endpoint_match.group(1)
                    tgt_service = None
                    if "cv-api" in endpoint:
                        tgt_service = "cv_api"
                    elif "competencies-api" in endpoint:
                        tgt_service = "competencies_api"
                    elif "users-api" in endpoint:
                        tgt_service = "users_api"
                    elif "drive-api" in endpoint:
                        tgt_service = "drive_api"

                    if tgt_service:
                        route_path = endpoint.split(".${var.base_domain}")[-1]
                        topic_subscriber_links.append((topic_res, tgt_service, route_path))
        except Exception as exc:
            print(f"⚠️ Erreur lors du parsing de pubsub.tf : {exc}")

    with driver.session() as session:
        session.run("MATCH ()-[r:TERRAFORM_LINK]->() DELETE r")

        q_db = """
        MERGE (s:Service {name: $src})
        MERGE (d:Database {name: $tgt})
        MERGE (s)-[r:TERRAFORM_LINK {type: "USES_DB"}]->(d)
        """
        for src, tgt in set(service_db_links):
            session.run(q_db, src=src, tgt=tgt)

        q_google = """
        MERGE (s:Service {name: $src})
        MERGE (g:GoogleService {name: $tgt})
        MERGE (s)-[r:TERRAFORM_LINK {type: "CALLS_GOOGLE"}]->(g)
        """
        for src, tgt in set(service_google_links):
            session.run(q_google, src=src, tgt=tgt)

        q_service = """
        MERGE (s1:Service {name: $src})
        MERGE (s2:Service {name: $tgt})
        MERGE (s1)-[r:TERRAFORM_LINK {type: "SERVICE_CALLS"}]->(s2)
        """
        for src, tgt in set(service_service_links):
            session.run(q_service, src=src, tgt=tgt)

        q_pub = """
        MERGE (s:Service {name: $src})
        MERGE (t:PubSubTopic {name: $tgt})
        MERGE (s)-[r:TERRAFORM_LINK {type: "PUBLISHES_TO"}]->(t)
        """
        for src, tgt in set(topic_publisher_links):
            session.run(q_pub, src=src, tgt=tgt)

        q_sub = """
        MERGE (t:PubSubTopic {name: $src})
        MERGE (s:Service {name: $tgt})
        MERGE (t)-[r:TERRAFORM_LINK {type: "SUBSCRIBES_TO", endpoint: $endpoint}]->(s)
        """
        for src, tgt, endpoint in set(topic_subscriber_links):
            session.run(q_sub, src=src, tgt=tgt, endpoint=endpoint)

    total_links = (
        len(service_db_links) + len(service_google_links) + len(service_service_links)
        + len(topic_publisher_links) + len(topic_subscriber_links)
    )
    print(f"   ↳ {total_links} relations d'infrastructure Terraform insérées.")


if __name__ == "__main__":
    main()
