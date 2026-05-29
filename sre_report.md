# Rapport SRE — 2026-05-29 14:01

**Source** : `prompts_api` prd | **Erreurs analysées** : 2

## Erreurs détectées

### [1] `error_correction:agent_hr_api:7da2d05e2cd5`

**Service** : `agent_hr_api`

**Message d'erreur** :
```
{"rule": "NEVER use `type='error'` when constructing an Agent-to-Agent (A2A) response step. The A2A protocol only allows step types: 'call', 'result', 'warning', or 'cache'. To communicate a non-critical failure or issue to the calling agent, you MUST use the 'warning' type.\n\u274c `A2AResponse(steps=[{'type': 'error', 'message': 'Tool execution failed'}])`\n\u2705 `A2AResponse(steps=[{'type': 'warning', 'message': 'Tool execution failed'}])`\nIf a downstream agent reports a validation error on your response, use `get_service_logs` on `agent_hr_api` to debug your response structure.\n\n[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'agent_hr_api' sur le projet GCP 'prod-ia-staffing'.", "original_error": "1 validation error for A2AResponse\nsteps.0.type\n  Input should be 'call', 'result', 'warning' or 'cache' [type=literal_error, input_value='error', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.13/v/literal_error", "service": "agent_hr_api", "context": "  + Exception Group Traceback (most recent call last):\n  |   File \"/app/.venv/lib/python3.13/site-packages/starlette/_utils.py\", line 81, in collapse_excgroups\n  |     yield\n  |   File \"/app/.venv/lib/python3.13/site-packages/starlette/middleware/base.py\", line 192, in __call__\n  |     async with anyio.create_task_group() as task_group:\n  |                ~~~~~~~~~~~~~~~~~~~~~~~^^\n  |   File \"/app/.venv/lib/python3.13/site-packages/anyio/_backends/_asyncio.py\", line 799, in __aexit__\n  |     raise BaseExceptionGroup(\n  |         \"unhandled errors in a TaskGroup\", self._exceptions\n  |     ) from None\n  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)\n  +-+---------------- 1 ----------------\n    | Traceback (most recent call last):\n    |   File \"/app/.venv/lib/python3.13/site-packages/starlette/middleware/errors.py\", line 164, in __call__\n    |     await self.app(scope, r
```

### [2] `error_correction:drive-api:12b916d66e4a`

**Service** : `drive-api`

**Message d'erreur** :
```
{"rule": "NEVER call `drive-api` ingestion tools if the background processing seems to fail. The `run_sync_after_retry` task can crash with a `TypeError: 'NoneType' object is not callable` due to a database session initialization failure. Do not retry the ingestion.\n\u274c Calling `drive_api.ingest_document(...)` a second time.\n\u2705 Use `ops_api.get_service_logs(service_name='drive-api', query=\"'NoneType' object is not callable\")` to confirm the internal error.\nIf this error recurs, report that the `drive-api` ingestion service is degraded.\n\n[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'drive-api' sur le projet GCP 'prod-ia-staffing'.", "original_error": "'NoneType' object is not callable", "service": "drive-api", "context": "exceptions(self.app, conn)(scope, receive, send)\n  File \"/app/.venv/lib/python3.13/site-packages/starlette/_exception_handler.py\", line 53, in wrapped_app\n    raise exc\n  File \"/app/.venv/lib/python3.13/site-packages/starlette/_exception_handler.py\", line 42, in wrapped_app\n    await app(scope, receive, sender)\n  File \"/app/.venv/lib/python3.13/site-packages/fastapi/middleware/asyncexitstack.py\", line 18, in __call__\n    await self.app(scope, receive, send)\n  File \"/app/.venv/lib/python3.13/site-packages/starlette/routing.py\", line 716, in __call__\n    await self.middleware_stack(scope, receive, send)\n  File \"/app/.venv/lib/python3.13/site-packages/starlette/routing.py\", line 736, in app\n    await route.handle(scope, receive, send)\n  File \"/app/.venv/lib/python3.13/site-packages/starlette/routing.py\", line 290, in handle\n    await self.app(scope, receive, send)\n  File \"/app/.venv/lib/python3.13/site-packages/fastapi/routing.py\", line 134, in app\n    await wrap_app_handling_exceptions(app, request)(scope, receive, send)\n  File \"/app/.venv/lib/python3.13/site-packages/starlette/_exception_handler.py\", line 53, in wrapped_app\n    raise 
```

## Plan de remédiation

> Analyse des erreurs ci-dessus et propositions de correction.

#### `error_correction:agent_hr_api:7da2d05e2cd5` — Erreur générique

**Actions** : Analyser manuellement le message d'erreur dans `agent_hr_api/`.

#### `error_correction:drive-api:12b916d66e4a` — Erreur générique

**Actions** : Analyser manuellement le message d'erreur dans `drive-api/`.
