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
| `SECRET_KEY` | Secret | via `.env` |
| `DATABASE_URL` | Infra | injecté Cloud Run |
| `REDIS_URL` | Infra | `redis://redis:6379/3` |
| `GEMINI_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
| `MCP_SIDECAR_URL` | Comportement | `http://competencies_mcp:8000` |
| `ROOT_PATH` | Comportement | `/comp-api` |
| `GCP_PROJECT_ID` | Infra | injecté Cloud Run |
| `VERTEX_LOCATION` | Comportement | `europe-west1` |
| `BATCH_GCS_BUCKET` | Infra | bucket `cv_batch` partagé avec `cv_api` |
| `CV_API_URL` | Infra | URL de `cv_api` (missions) |
| `USERS_API_URL` | Infra | URL de `users_api` (service tokens) |
| `COMPETENCY_DECAY_LAMBDA` | Comportement | `0.1` (decay temporel scoring v2) |

## Redis
**DB 3** — namespace `competencies:*`
- `competencies:bulk_scoring:status` — état du pipeline Vertex Batch scoring

## Endpoints clés

| Endpoint | Description |
|---|---|
| `GET /` | Arbre complet des compétences (hiérarchique) |
| `GET /search` | Recherche fulltext nom + aliases |
| `POST /bulk_tree` | Import atomique taxonomie (Admin) |
| `POST /user/{id}/assign/bulk` | Affectation massive (appelé par `cv_api`) |
| `GET /evaluations/user/{id}` | Évaluations d'un consultant (feuilles) |
| `POST /evaluations/user/{id}/ai-score-all` | Scoring Gemini v2 individuel (BackgroundTask) |
| `POST /evaluations/bulk-scoring-all` | Scoring IA global avec Semaphore |
| `GET /bulk-scoring-all/status` | État du pipeline global |
| `GET /evaluations/scoring-stats` | Statistiques couverture IA (Data Quality) |
| `GET /stats/coverage` | Métriques Data Quality (consultants avec compétences) |
| `GET /analytics/agency-coverage` | Heatmap compétences × agences |
| `GET /analytics/skill-gaps` | Gaps de compétences dans un pool |
| `GET /analytics/similar-consultants/{id}` | Similarité Jaccard entre consultants |

## MCP tools exposés
- `get_competency_tree`, `create_competency`, `list_evaluations`, `assign_competencies_bulk`
- `trigger_bulk_scoring`, `get_bulk_scoring_status`

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
