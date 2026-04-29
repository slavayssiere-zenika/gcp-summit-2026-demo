# agent_router_api

## Rôle
Routeur intelligent : point d'entrée unique du frontend, gestion des sessions ADK, cache sémantique Redis, et délégation aux sous-agents HR/Ops/Missions via le protocole A2A (HTTP).

## Type
🟣 Agent IA (consommateur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 808 | 🚨 Zone bloquante (> 600) — refactoring requis |
| `agent.py` | 579 | ⚠️ Zone alerte |
| `semantic_cache.py` | 360 | ⚠️ Zone alerte |
| `session.py` | ~150 | ✅ OK |
| `mcp_client.py` | ~120 | ✅ OK |
| `metrics.py` | ~50 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `REDIS_URL` | Infra | `redis://redis:6379/2` (docker-compose) |
| `GEMINI_MODEL` | Comportement | `gemini-2.5-flash` |
| `ROOT_PATH` | Comportement | `/api` |
| `AGENT_HR_URL` | Infra | URL agent HR |
| `AGENT_OPS_URL` | Infra | URL agent Ops |
| `AGENT_MISSIONS_URL` | Infra | URL agent Missions |

## Redis
**DB 2** — namespace `session:*` (historique) + `semantic:*` (cache sémantique)

## Endpoints clés
- `POST /query` — point d'entrée principal (frontend → agent)
- `GET /health`, `GET /metrics`, `GET /version`

## Sous-agents consommés (A2A)
- `agent_hr_api` — RH, CVs, compétences
- `agent_ops_api` — missions, items, opérationnel
- `agent_missions_api` — gestion documentaire missions

## Cache sémantique
- `SemanticCache` dans `semantic_cache.py` : index HNSW Redis
- **Attention** : Redis Memorystore GCP ne supporte pas les types TEXT pour les index vectoriels — utiliser TAG
- Reset automatique si le context window déborde (INVALID_ARGUMENT 400)

## Gotchas connus
- **`main.py` en zone bloquante (808L)** — ne pas ajouter de logique métier directement
- Le cache sémantique HNSW nécessite un index Redis de type TAG (pas TEXT) pour la compatibilité GCP Memorystore
- Les appels A2A vers les sous-agents doivent tous utiliser le pattern httpx timeout/retry standard (30s, 3 retries, backoff exponentiel)
- Les erreurs non-critiques (FinOps, monitoring) doivent être en mode dégradé (`asyncio.create_task`) pour ne pas bloquer la réponse

## Dernière modification
2026-04-28 — v0.1.23 — fix SemanticCache HNSW TAG + session reset overflow
