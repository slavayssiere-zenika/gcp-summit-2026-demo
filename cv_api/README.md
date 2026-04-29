# cv_api

## Rôle
Analyse multimodale des CVs via Gemini/Vertex AI, extraction d'informations structurées (compétences, missions, formations), embedding vectoriel (pgvector), et orchestration des pipelines batch Vertex AI. Expose l'endpoint `/user/{id}/missions` consommé par `competencies_api` pour le scoring IA.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `src/cvs/router.py` | ~2380 | 🚨 GOD ROUTER — remédiation en cours (service layer créé) |
| `src/services/cv_import_service.py` | ~650 | ⚠️ Zone alerte |
| `src/services/bulk_service.py` | ~601 | ⚠️ Zone alerte |
| `src/services/taxonomy_service.py` | ~570 | ⚠️ Zone alerte |
| `src/services/config.py` | ~78 | ✅ OK |
| `src/cvs/schemas.py` | ~200 | ✅ OK |
| `src/cvs/models.py` | ~100 | ✅ OK |
| `src/cvs/bulk_task_state.py` | ~80 | ✅ OK |
| `src/gemini_retry.py` | ~75 | ✅ OK |
| `src/auth.py` | ~40 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `DATABASE_URL` | Infra | injecté Cloud Run |
| `REDIS_URL` | Infra | `redis://redis:6379/4` |
| `GEMINI_MODEL` | Comportement | `gemini-2.5-flash` |
| `GEMINI_PRO_MODEL` | Comportement | `gemini-3.1-pro-preview` |
| `GEMINI_CV_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
| `GEMINI_EMBEDDING_MODEL` | Comportement | `gemini-embedding-001` |
| `MCP_SIDECAR_URL` | Comportement | `http://cv_mcp:8000` |
| `ROOT_PATH` | Comportement | `/cv-api` |
| `PROMPTS_API_URL` | Infra | URL de `prompts_api` |
| `COMPETENCIES_API_URL` | Infra | URL de `competencies_api` |
| `GCP_PROJECT_ID` | Infra | injecté Cloud Run |
| `VERTEX_LOCATION` | Comportement | `europe-west1` |
| `BATCH_GCS_BUCKET` | Infra | injecté Cloud Run (bucket `cv_batch`, **partagé** avec `competencies_api`) |
| `BULK_APPLY_SEMAPHORE` | Comportement | `5` |
| `BULK_EMBED_SEMAPHORE` | Comportement | `10` |
| `CLOUDRUN_WORKSPACE` | Comportement | injecté Cloud Run |
| `BULK_SCALE_MIN_INSTANCES` | Comportement | `1` |

## Redis
**DB 4** — namespace `cv:*`

## Endpoints clés
- `POST /cvs/upload` — upload et analyse d'un CV (Gemini multimodal)
- `POST /cvs/bulk/start` — lancement analyse batch Vertex AI
- `GET /cvs/bulk/status` — état du pipeline batch
- `GET /cvs/search` — recherche vectorielle sémantique
- `GET /cvs/{user_id}` — profil complet d'un consultant
- `POST /cvs/reanalyze/{user_id}` — réanalyse individuelle
- `GET /user/{user_id}/missions` — ⚠️ **endpoint critique** — missions d'un consultant, consommé par `competencies_api/scoring_service.py`
- `GET /bulk-reanalyse/data-quality` — KPIs Data Quality (missions, embeddings, compétences, summary)

## Architecture Service Layer
```
src/cvs/router.py          → HTTP in/out + délégation (2380L — en remédiation)
src/services/
  cv_import_service.py     → pipeline d'import/analyse CV
  bulk_service.py          → orchestration Vertex AI Batch (préfixe GCS: bulk-reanalyse/)
  taxonomy_service.py      → classification taxonomique
  config.py                → configuration centralisée (vertex_batch_client, client genai)
```

## GCS Bucket partagé (`cv_batch`)
Le bucket Terraform `google_storage_bucket.cv_batch` est **partagé** entre :
- `cv_api` → préfixe `bulk-reanalyse/` (extraction CV)
- `competencies_api` → préfixe `bulk-scoring/` (scoring compétences)

Les deux services ont `roles/storage.objectAdmin` sur ce bucket via leurs service accounts respectifs.

**Règle** : Tout nouveau pipeline batch doit utiliser un préfixe GCS distinct. Ne jamais écrire à la racine du bucket.

## MCP tools exposés
- `get_cv_profile`, `search_cvs_semantic`, `list_cvs`, `get_cv_bulk_status`

## Gotchas connus
- **RÈGLE CRITIQUE** : `router.py` était 5039L (God Router) — refactorisé en service layer. NE PAS réajouter de logique métier dans `router.py`
- **Bucket GCS partagé** : `cv_batch` est partagé avec `competencies_api`. Les préfixes `bulk-reanalyse/` (cv) et `bulk-scoring/` (competencies) sont obligatoires pour l'isolation.
- **`GET /user/{id}/missions`** : endpoint critique consommé par `competencies_api/scoring_service.py` — toute modification du format de réponse (`missions[]`) brise le scoring IA Vertex Batch de competencies_api.
- Le prompt `extract_cv_info` est fetché depuis `prompts_api` via `GET /prompts/cv_api.extract_cv_info` — une URL incorrecte retourne une string vide, cassant l'extraction LLM
- Les `educations` doivent être inclus dans le schéma JSON du prompt (champ explicite)
- La séniorité est un champ **calculé** depuis `years_of_experience` — pas un champ BDD persisté
- Vertex AI Batch : les résultats arrivent asynchrones dans GCS — le polling status est dans `bulk_task_state.py`
- `POST /assign/bulk` dans `competencies_api` DOIT être appelé après chaque analyse batch réussie

## Dernière modification
2026-04-29 — Documentation mise à jour — `GET /user/{id}/missions` documenté comme dépendance critique du scoring Vertex AI Batch de `competencies_api`
