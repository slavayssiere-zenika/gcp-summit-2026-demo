# SRE Report — 2026-05-05 19:23

## Résumé exécutif

**3 erreurs** en production. **2 adressées** (code fixé + prompts supprimés). **1 conservée** (QueuePool monitoring).

---

## ✅ `cv_api` — `UndefinedColumnError: cv_profiles.is_archived` (×2)
- **Clés** : `d86c930abb86`, `2b7e4f88dfde`
- **Cause** : Liquibase changeset 10 (`addColumn is_archived`) présent dans `db_migrations` mais **image v0.0.30 pas encore exécutée** — la migration a été déclenchée dans le dernier `prd.yaml` (v0.0.30) mais le job Cloud Run est probablement encore en cours ou n'a pas tourné sur la bonne révision.
- **Action requise** : Aucune correction de code — juste s'assurer que `deploy.sh` a bien exécuté `db_migrations:v0.0.30` en prod.
- **Prompts** : Supprimés.

---

## ✅ `competencies_api` + `cv_api` — Contrat cassé `MissionsResponse` (`id: int` required)
- **Cause** : `shared/schemas/missions.py` définissait `MissionItem.id: int` (required). Or `cv_api/get_user_missions` retourne des `ExtractedMission` (extractions LLM) **sans champ `id`** — la validation `MissionsResponse.model_validate()` dans `competencies_api` échouerait à chaque appel scoring.

- **Fix dans `shared/schemas/missions.py`** :
  ```python
  # AVANT
  id: int                 # required → ValidationError garantie sur missions LLM
  # APRÈS
  id: Optional[int] = None   # LLM-extracted missions have no DB id
  company: Optional[str] = None      # ajouté
  duration: Optional[str] = None     # ajouté
  competencies: List[str] = []       # ajouté
  is_sensitive: Optional[bool] = False  # ajouté
  mission_type: Optional[str] = None    # ajouté
  ```

  **Impact** : `competencies_api/scoring_pipeline.py` et `ai_scoring.py` — les deux utilisent `MissionsResponse.model_validate()`.

---

## ⚠️ Conservé — `competencies_api` QueuePool timeout
- `error_correction:competencies_api:a0d033652b85`
- Recommandation : `DB_POOL_SIZE=15 / DB_MAX_OVERFLOW=30` si récurrent en prod.

---

## Fichiers modifiés

| Fichier | Fix |
|---------|-----|
| `shared/schemas/missions.py` | `id: int` → `Optional[int] = None` + champs LLM manquants |

## Action opérateur

```bash
cd platform-engineering && python3 manage_env.py deploy --env prd
```

S'assurer que le job `db_migrations:v0.0.30` s'est bien exécuté (check Cloud Logging `db-migrations-prd`).