# SRE Report — 2026-05-04 12:04

## Résumé exécutif

**5 erreurs de production** trouvées dans `prompts_api`. **4 résolues** (code corrigé + prompts supprimés). **1 en monitoring**.

---

## ✅ Erreurs résolues

### 1. `cv_api` — `NameError: name 'tempfile' is not defined`
- **Clé** : `error_correction:cv_api:2a06e2cd18df`
- **Statut** : ✅ Déjà corrigé dans le code source (`import tempfile` présent dans `taxonomy_router.py:9`)
- **Action** : Prompt supprimé de production.

---

### 2. `cv_api` — `NameError: name '_CV_CACHE' is not defined`
- **Clé** : `error_correction:cv_api:ad6f85bbc3bc`
- **Endpoint** : `POST /cache/invalidate-taxonomy`
- **Cause** : `_CV_CACHE` défini dans `src/services/config.py` mais non importé explicitement dans `profile_router.py`. Le module était importé comme `_svc_config` mais le dictionnaire lui-même n'était pas accessible.
- **Fix appliqué** :
  ```python
  # cv_api/src/cvs/routers/profile_router.py
  from src.services.config import _CV_CACHE  # ← ajouté
  ```
- **Action** : Prompt supprimé de production.

---

### 3. `drive_api` — `NameError: name '_compute_kpi_metric' is not defined`
- **Clé** : `error_correction:drive_api:b67443bd3dee`
- **Fichier** : `ingestion_router.py`
- **Cause** : `_compute_kpi_metric` est définie dans `files_router.py` (ligne 394) mais `ingestion_router.py` l'utilisait sans l'importer.
- **Fix appliqué** :
  ```python
  # drive_api/src/routers/ingestion_router.py
  from src.routers.files_router import _compute_kpi_metric  # ← ajouté
  ```
- **Action** : Prompt supprimé de production.

---

### 4. `agent_router_api` — `400 INVALID_ARGUMENT` (context window overflow)
- **Clé** : `error_correction:agent_router_api:8597819c7b7a`
- **Statut** : ✅ Déjà corrigé — handler OPS-003 présent dans `agent.py:320-334` avec session reset automatique.
- **Action** : Prompt supprimé de production.

---

## ⚠️ En monitoring — Intervention opérateur requise

### 5. `competencies_api` — `QueuePool limit of size 10 overflow 20 reached`
- **Clé** : `error_correction:competencies_api:a0d033652b85`
- **Statut** : ⚠️ **Conservé** en production comme garde-fou
- **Cause** : Saturation du pool de connexions SQLAlchemy lors de bulk operations concurrentes.
- **État actuel** : Pool configuré via env vars `DB_POOL_SIZE=10` / `DB_MAX_OVERFLOW=20` dans `database.py`. Commentaire doc indique que le dimensionnement est cohérent avec les semaphores batch (max ~9 conns simultanées).
- **Recommandation** : Augmenter `DB_POOL_SIZE=15` / `DB_MAX_OVERFLOW=30` dans Cloud Run si les bulk scoring jobs s'exécutent en parallèle. Surveiller via Grafana les métriques `pool_checked_out`.

---

## Fichiers modifiés

| Service | Fichier | Type de fix |
|---------|---------|-------------|
| `cv_api` | `src/cvs/routers/profile_router.py` | Import manquant `_CV_CACHE` |
| `drive_api` | `src/routers/ingestion_router.py` | Import manquant `_compute_kpi_metric` |

## Actions à faire (opérateur)

1. **Rebuilder et déployer** `cv_api` et `drive_api` avec `deploy.sh`
2. **Monitorer** `competencies_api` pool metrics et ajuster `DB_POOL_SIZE` si nécessaire