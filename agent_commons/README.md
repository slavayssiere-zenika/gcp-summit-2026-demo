# agent_commons

## Rôle
Bibliothèque partagée Python installée dans les 4 agents (`agent_router_api`, `agent_hr_api`, `agent_ops_api`, `agent_missions_api`). Centralise les abstractions communes pour éviter la duplication : sécurité JWT, client MCP, session ADK, guardrails, FinOps.

## Type
📦 Bibliothèque partagée (pas de service déployé)

## Migration 2026-04-29 — Centralisation du boilerplate

Les ~320 lignes de code dupliqué ont été supprimées des 4 agents et centralisées ici.

| Module migré | Était dans | Impact |
|---|---|---|
| `schemas.py` → `QueryRequest` | Chaque `main.py` agent | Modèle Pydantic unifié |
| `jwt_middleware.py` → `verify_jwt_bearer` / `verify_jwt_request` | Chaque `main.py` agent | Validation JWT HS256 + claim `sub` |
| `exception_handler.py` → `make_global_exception_handler` | Chaque `main.py` agent | Reporting async vers `prompts_api` |
| `metadata.py` → `get_tool_metadata` | `agent_router_api/main.py` | Introspection tools |

## Fichiers clés

| Fichier | Lignes | État |
|---|---|---|
| `agent_commons/guardrails.py` | 419 | ⚠️ Zone alerte — découpage prévu |
| `agent_commons/mcp_client.py` | 269 | ✅ OK |
| `agent_commons/mcp_proxy.py` | 190 | ✅ OK |
| `agent_commons/runner.py` | 180 | ✅ OK |
| `agent_commons/taxonomy_utils.py` | 173 | ✅ OK |
| `agent_commons/session.py` | 150 | ✅ OK |
| `agent_commons/schemas.py` | 134 | ✅ OK — `QueryRequest` centralisé |
| `agent_commons/jwt_middleware.py` | ~80 | ✅ NEW — `verify_jwt_bearer` + `verify_jwt_request` |
| `agent_commons/exception_handler.py` | ~70 | ✅ NEW — `make_global_exception_handler` |
| `agent_commons/finops.py` | ~80 | ✅ OK |
| `agent_commons/metadata.py` | ~60 | ✅ OK |

## Version actuelle
`1.0.1` — référencée dans les `requirements.txt` de chaque agent

## Modules clés

### `jwt_middleware.py`
Deux variantes selon le type de route FastAPI :
- **`verify_jwt_bearer`** : pour `HTTPAuthorizationCredentials` (standard, `agent_hr`, `agent_ops`, `agent_router`)
- **`verify_jwt_request`** : pour `Request` direct (`agent_missions_api`)

Valide : signature HS256 + expiration + claim `sub`. Interdit : fallback dev `{"sub": "dev-user"}`.

### `exception_handler.py`
Factory `make_global_exception_handler(service_name)` :
- Rapport async (non-bloquant) vers `prompts_api/errors/report`
- Obtention automatique du service token si JWT absent
- Retourne `JSONResponse(500)` sans propager l'exception

### `mcp_client.py`
Client HTTP MCP avec propagation JWT via `auth_header_var` (contextvars).  
Alimenter `auth_header_var` AVANT tout appel MCP sortant.

### `finops.py`
Wrapper `log_ai_consumption()` vers `analytics_mcp` — OBLIGATOIRE après chaque inférence LLM.

### `taxonomy_utils.py`
`_clean_llm_json()` — corrige trailing commas et commentaires JSON malformés.  
À utiliser **systématiquement** avant `json.loads()` sur output LLM.

## Usage dans les agents

```python
# main.py d'un agent
from agent_commons.schemas import QueryRequest
from agent_commons.jwt_middleware import verify_jwt_bearer
from agent_commons.exception_handler import make_global_exception_handler

protected_router = APIRouter(dependencies=[Depends(verify_jwt_bearer)])
app.add_exception_handler(Exception, make_global_exception_handler("agent_hr_api"))
```

## Gotchas connus
- **CRITIQUE** : toute modification impacte les **4 agents simultanément** — tester sur tous avant déploiement.
- `agent_commons` doit avoir un fichier `VERSION` indépendant.
- `auth_header_var` (contextvars) DOIT être alimenté avant tout appel MCP sortant.
- Ne jamais créer de `mcp_server.py` dans un dossier `agent_*` — les agents sont des consommateurs MCP, pas des producteurs.

## Dernière modification
`2026-04-29` — Migration boilerplate : centralisation de `QueryRequest`, `verify_jwt_bearer/request`, `make_global_exception_handler` — suppression de ~320L de code dupliqué dans les 4 agents.
