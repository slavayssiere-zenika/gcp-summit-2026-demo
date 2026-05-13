# Rapport SRE — 2026-05-12 17:30

**Source** : `prompts_api` prd | **Erreurs analysées** : 1

## Erreurs détectées

### [1] `error_correction:cv_api:24fc7dd3aac2`

**Service** : `cv_api`

**Message d'erreur** :
```
{"rule": "NEVER call tools that modify CV data, such as `cv_api.update_cv` or `cv_api.create_cv`.\nThese tools trigger a known background task failure (`TypeError: reindex_embeddings_bg() missing 'genai_client'`).\nInstead, inform the user that CV updates are temporarily unavailable due to a service issue.\n\u274c `print(cv_api.update_cv(cv_id='cv-abc-123', content='New experience...'))`\n\u2705 \"I am unable to process CV updates at this time due to a known technical issue. The operations team has been notified.\"\nIf this error pattern recurs after a fix, use `get_service_logs` to query `cv_api` for the `TypeError` to aid debugging.\n\n[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'cv_api' sur le projet GCP 'prod-ia-staffing'.", "original_error": "reindex_embeddings_bg() missing 1 required positional argument: 'genai_client'", "service": "cv_api", "context": "tions.py\", line 63, in __call__\n    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)\n  File \"/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py\", line 53, in wrapped_app\n    raise exc\n  File \"/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py\", line 42, in wrapped_app\n    await app(scope, receive, sender)\n  File \"/usr/local/lib/python3.13/site-packages/fastapi/middleware/asyncexitstack.py\", line 18, in __call__\n    await self.app(scope, receive, send)\n  File \"/usr/local/lib/python3.13/site-packages/starlette/routing.py\", line 716, in __call__\n    await self.middleware_stack(scope, receive, send)\n  File \"/usr/local/lib/python3.13/site-packages/starlette/routing.py\", line 736, in app\n    await route.handle(scope, receive, send)\n  File \"/usr/local/lib/python3.13/site-packages/starlette/routing.py\", line 290, in handle\n    await self.app(scope, receive, send)\n  File \"/usr/local/lib/python3.13/site-packages/fastapi/routing.py\", line 134, in app\n    a
```

## Plan de remédiation

> Analyse des erreurs ci-dessus et propositions de correction.

#### `error_correction:cv_api:24fc7dd3aac2` — Erreur générique

**Actions** : Analyser manuellement le message d'erreur dans `cv_api/`.
