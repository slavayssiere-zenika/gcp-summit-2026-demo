# competencies_api

## Rôle
Gestion de l'arbre de compétences (taxonomie), évaluation IA des consultants, et orchestration des pipelines batch Map/Dedup/Reduce/Sweep.

## Type
🔵 API data (producteur MCP)

## Architecture modulaire (refactoring 2026-04-29)

Le monolithe `router.py` (~2490L) a été décomposé en modules spécialisés.  
**Chaque fichier respecte la limite de 400 lignes.**

| Fichier | Lignes | Rôle |
|---|---|---|
| `src/competencies/router.py` | ~40 | ✅ Dispatcher léger — assemble les sous-routers |
| `src/competencies/competencies_router.py` | ~280 | CRUD compétences, suggestions, bulk_tree, stats |
| `src/competencies/assignments_router.py` | ~180 | Assignation user↔compétences, merge, Pub/Sub |
| `src/competencies/evaluations_router.py` | ~170 | Scoring (batch, user-score, ai-score, ai-score-all) |
| `src/competencies/analytics_router.py` | ~230 | Bulk-scoring global, coverage, analytics avancés |
| `src/competencies/ai_scoring.py` | ~210 | Moteur Gemini v2 (scoring pondéré + background tasks) |
| `src/competencies/helpers.py` | ~180 | Utilitaires partagés (scoring v2, sérialisation, cache) |
| `src/competencies/schemas.py` | ~252 | ✅ Schémas Pydantic |
| `src/competencies/bulk_task_state.py` | ~115 | ✅ BulkScoringTaskManager (Redis) |
| `src/competencies/models.py` | 96 | ✅ Modèles SQLAlchemy |
| `src/auth.py` | ~40 | ✅ verify_jwt |

### Ordre d'enregistrement FastAPI (CRITIQUE)

> ⚠️ Les routes statiques DOIVENT être enregistrées avant les routes wildcard `/{id}`.

```
1. competencies_router  →  /search, /suggestions, /stats, /bulk_tree  (avant /{competency_id})
2. evaluations_router   →  /evaluations/...                            (avant /user/{user_id})
3. analytics_router     →  /bulk-scoring-all/..., /analytics/...
4. assignments_router   →  /user/{user_id}/...                         (wildcards en dernier)
5. public_router        →  /pubsub/user-events                         (sans auth JWT)
```

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHON_AR_REPO` | Comportement | `${PYTHON_AR_REPO}` |
| `SHARED_VERSION` | Comportement | `${SHARED_VERSION}` |
| `PATH` | Comportement | `"/app/.venv/bin:$PATH"` |
| `PYTHONPATH` | Comportement | `/app` |
| `PORT` | Infra | `8003` |
| `MCP_SIDECAR_URL` | Infra | `http://competencies_mcp:8000` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/comp-api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `competencies-api` |
| `USE_IAM_AUTH` | Comportement | `false` |
| `USERS_API_URL` | Infra | `http://users_api:8000` |
| `CV_API_URL` | Infra | `http://cv_api:8004` |
| `GEMINI_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |

## Redis
**DB 3** — namespace `competencies:*`
- `competencies:bulk_scoring:status` — état du pipeline Vertex Batch scoring

## Endpoints clés
- `GET /stats/coverage`
- `GET /evaluations/scoring-stats`
- `GET /analytics/agency-coverage`
- `GET /analytics/skill-gaps`
- `GET /analytics/taxonomy-quality`
- `POST /user/{user_id}/assign/bulk`
- `POST /user/{user_id}/assign/{competency_id}`
- `DELETE /user/{user_id}/evaluations`
- `DELETE /user/{user_id}/remove/{competency_id}`
- `GET /user/{user_id}`
- `POST /internal/users/merge`
- `DELETE /user/{user_id}/clear`
- `GET /`
- `GET /search`
- `GET /{competency_id}`
- `GET /{competency_id}/users`
- `POST /`
- `PUT /{competency_id}`
- `DELETE /{competency_id}`
- `POST /stats/counts`

## MCP tools exposés
- `assign_competencies_bulk`, `assign_competency_to_user`, `batch_evaluate_competencies_search`, `batch_evaluate_competencies_users`, `bulk_import_tree`, `bulk_scoring_all`, `clear_user_competencies`, `clear_user_evaluations`, `create_competency`, `create_competency_suggestion`, `delete_competency`, `find_similar_consultants`, `find_skill_gaps`, `get_agency_competency_coverage`, `get_competency`, `get_competency_stats`, `get_user_competency_evaluations`, `list_competencies`, `list_competency_suggestions`, `list_competency_users`, `list_user_competencies`, `remove_competency_from_user`, `review_competency_suggestion`, `search_competencies`, `set_user_competency_score`, `trigger_ai_scoring`, `update_competency`

## IAM Cloud Run requis
- `roles/aiplatform.user` → Vertex AI Batch Prediction
- `roles/storage.objectAdmin` sur `cv_batch` → JSONL input/output

## Scoring v2 — Algorithme de pondération

```
score_final = Gemini(missions, poids_récence, multiplicateur_durée, bonus_type_mission)

Récence    : e^(-0.1 × années_écoulées)   [1.0 = en cours, 0.22 = 15 ans]
Durée      : min(1.5, 0.5 + mois/24)      [0.75 = 6 mois, 1.5 = 24 mois+]
Bonus type : audit/conseil +0.5, formation/accompagnement +0.3-0.4, build +0
```

## Gotchas connus
- **Scoping des feuilles** : utiliser `user_competency` (scope user), PAS la hiérarchie globale.
- **Bucket GCS partagé** : préfixe `bulk-scoring/` (competencies) vs `bulk-reanalyse/` (cv).
- **Désormais interdit** d'ajouter du code dans `router.py` — c'est un dispatcher pur.
- **Service token obligatoire** avant tout ai-score-all/bulk-scoring-all (AGENTS.md §4).

## Dernière modification
`2026-04-29` — Refactoring complet : décomposition du God Router (~2490L) en 6 modules spécialisés + dispatcher léger (~40L).
