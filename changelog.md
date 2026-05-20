## Mise à jour automatique - 2026-05-20 08:46:45

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 2187  | 591  |  73% |
| agent_hr_api     | 1477  | 180  |  88% |
| agent_missions_api | 1747  | 203  |  88% |
| agent_ops_api    | 1342  | 185  |  86% |
| agent_router_api | 3054  | 492  |  84% |
| analytics_mcp    | 932   | 141  |  85% |
| competencies_api | 4531  | 1052 |  77% |
| cv_api           | 9506  | 1565 |  84% |
| drive_api        | 3502  | 418  |  88% |
| items_api        | 2183  | 136  |  94% |
| missions_api     | 2166  | 231  |  89% |
| monitoring_mcp   | 1165  | 134  |  88% |
| platform-engineering | 1497  | 1212 |  19% |
| prompts_api      | 1172  | 280  |  76% |
| shared           | 2783  | 275  |  90% |
| tests            | 78    | 3    |  96% |
| users_api        | 2013  | 356  |  82% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `.agents/workflows/analyse-code-api.md` (M)
- `.agents/workflows/analyse-performance.md` (A)
- `agent_commons/agent_commons.egg-info/SOURCES.txt` (M)
- `agent_hr_api/.dockerignore` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/FILE_HASHES` (MM)
- `agent_hr_api/HASH` (MM)
- `agent_hr_api/VERSION` (MM)
- `agent_hr_api/agent.py` (MM)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/debug_jwt.py` (D)
- `agent_hr_api/main.py` (MM)
- `agent_hr_api/requirements.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/tests/test_create_agent_jwt.py` (M)
- `agent_hr_api/tests/test_functional_contract.py` (AM)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/FILE_HASHES` (MM)
- `agent_missions_api/HASH` (MM)
- `agent_missions_api/VERSION` (MM)
- `agent_missions_api/agent.py` (M)
- `agent_missions_api/agent_missions_api.system_instruction.txt` (M)
- `agent_missions_api/main.py` (MM)
- `agent_missions_api/requirements.txt` (M)
- `agent_missions_api/spec.md` (M)
- `agent_missions_api/tests/conftest.py` (A)
- `agent_missions_api/tests/test_create_agent_jwt.py` (M)
- `agent_missions_api/tests/test_functional_contract.py` (AM)
- `agent_missions_api/tests/test_guardrail.py` (M)
- `agent_missions_api/tests/test_history.py` (M)
- `agent_missions_api/tests/test_main.py` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/FILE_HASHES` (MM)
- `agent_ops_api/HASH` (MM)
- `agent_ops_api/VERSION` (MM)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `agent_ops_api/main.py` (MM)
- `agent_ops_api/requirements.txt` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/tests/test_create_agent_jwt.py` (M)
- `agent_ops_api/tests/test_functional_contract.py` (AM)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/FILE_HASHES` (MM)
- `agent_router_api/HASH` (MM)
- `agent_router_api/VERSION` (MM)
- `agent_router_api/a2a_tools.py` (M)
- `agent_router_api/agent.py` (MM)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/requirements.txt` (M)
- `agent_router_api/session.py` (D)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/conftest.py` (M)
- `agent_router_api/tests/test_circuit_breaker.py` (D)
- `agent_router_api/tests/test_functional_contract.py` (AM)
- `agent_router_api/tests/test_session.py` (D)
- `agent_router_api/workflow_agent.py` (A)
- `analytics_mcp/FILE_HASHES` (MM)
- `analytics_mcp/HASH` (MM)
- `analytics_mcp/VERSION` (MM)
- `analytics_mcp/conftest.py` (MM)
- `analytics_mcp/init_pricing.py` (M)
- `analytics_mcp/mcp_server.py` (M)
- `analytics_mcp/tests/test_main.py` (M)
- `clean_errors.py` (AM)
- `competencies_api/FILE_HASHES` (MM)
- `competencies_api/HASH` (MM)
- `competencies_api/VERSION` (MM)
- `competencies_api/cache.py` (D)
- `competencies_api/conftest.py` (MM)
- `competencies_api/main.py` (M)
- `competencies_api/src/competencies/ai_scoring.py` (M)
- `competencies_api/src/competencies/analytics_router.py` (M)
- `competencies_api/src/competencies/assignments_router.py` (M)
- `competencies_api/src/competencies/bulk_task_state.py` (M)
- `competencies_api/src/competencies/competencies_router.py` (M)
- `competencies_api/src/competencies/evaluations_router.py` (M)
- `competencies_api/src/competencies/gemini_cache.py` (M)
- `competencies_api/src/competencies/suggestions_router.py` (M)
- `competencies_api/src/competencies/tree_router.py` (M)
- `competencies_api/tests/integration/conftest.py` (MM)
- `competencies_api/tests/integration/test_pg_integration.py` (M)
- `competencies_api/tests/test_competencies_crud.py` (MM)
- `competencies_api/tests/test_competencies_extra.py` (MM)
- `cv_api/FILE_HASHES` (MM)
- `cv_api/HASH` (MM)
- `cv_api/VERSION` (MM)
- `cv_api/eval/rag_quality_eval.py` (M)
- `cv_api/main.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/bulk_task_state.py` (M)
- `cv_api/src/cvs/routers/admin_router.py` (M)
- `cv_api/src/cvs/routers/analytics_router.py` (M)
- `cv_api/src/cvs/routers/bulk_router.py` (MM)
- `cv_api/src/cvs/routers/profile_router.py` (MM)
- `cv_api/src/cvs/routers/search_router.py` (MM)
- `cv_api/src/cvs/schemas.py` (M)
- `cv_api/src/cvs/task_state.py` (M)
- `cv_api/src/gemini_cache.py` (M)
- `cv_api/src/services/bulk_helpers.py` (M)
- `cv_api/src/services/bulk_service.py` (M)
- `cv_api/src/services/config.py` (MM)
- `cv_api/src/services/cv_extraction_service.py` (MM)
- `cv_api/src/services/cv_import_service.py` (M)
- `cv_api/src/services/retry_service.py` (MM)
- `cv_api/src/services/search_service.py` (M)
- `cv_api/src/services/semaphores.py` (M)
- `cv_api/tests/test_bulk_reanalyse.py` (M)
- `cv_api/tests/test_bulk_service_extended.py` (MM)
- `cv_api/tests/test_cv_extraction_service.py` (MM)
- `cv_api/tests/test_import_router.py` (MM)
- `cv_api/tests/test_mock_gemini_config.py` (A)
- `cv_api/tests/test_perf_pipeline.py` (AM)
- `cv_api/tests/test_task_state.py` (MM)
- `db_init/VERSION` (M)
- `db_init/pyproject.toml` (M)
- `db_init/uv.lock` (M)
- `db_migrations/FILE_HASHES` (AM)
- `db_migrations/HASH` (AM)
- `db_migrations/VERSION` (MM)
- `db_migrations/changelogs/missions/changelog.yaml` (M)
- `db_migrations/changelogs/users/changelog.yaml` (M)
- `debug_test_keys.py` (AM)
- `docker-compose.yml` (MM)
- `drive_api/FILE_HASHES` (MM)
- `drive_api/HASH` (MM)
- `drive_api/VERSION` (MM)
- `drive_api/main.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/discovery_service.py` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/redis_client.py` (M)
- `drive_api/src/routers/files_router.py` (M)
- `drive_api/src/routers/folders_router.py` (M)
- `drive_api/src/services/folder_service.py` (MM)
- `drive_api/src/services/ingestion_kpi_service.py` (MM)
- `drive_api/src/services/tree_resolution.py` (M)
- `drive_api/tests/test_discovery_service.py` (MM)
- `drive_api/tests/test_drive_service_offboarding.py` (MM)
- `drive_api/tests/test_files_router.py` (MM)
- `drive_api/tests/test_folder_service.py` (MM)
- `drive_api/tests/test_folders.py` (MM)
- `drive_api/tests/test_folders_router.py` (MM)
- `drive_api/tests/test_ingestion_kpi_service.py` (MM)
- `drive_api/tests/test_mcp_tools.py` (MM)
- `drive_api/tests/test_tree_resolution.py` (MM)
- `frontend/FILE_HASHES` (MM)
- `frontend/HASH` (MM)
- `frontend/VERSION` (MM)
- `frontend/src/components/CompetencyEvaluationPanel.vue` (M)
- `frontend/src/services/agentApi.ts` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/types/index.ts` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/FILE_HASHES` (MM)
- `items_api/HASH` (MM)
- `items_api/VERSION` (MM)
- `items_api/cache.py` (D)
- `items_api/conftest.py` (MM)
- `items_api/src/items/admin_router.py` (M)
- `items_api/src/items/crud_router.py` (M)
- `items_api/src/items/routers/categories_router.py` (M)
- `items_api/src/items/routers/search_router.py` (M)
- `items_api/tests/integration/conftest.py` (M)
- `items_api/tests/integration/test_pg_integration.py` (MM)
- `items_api/tests/test_categories_router.py` (M)
- `items_api/tests/test_crud_router_basic.py` (M)
- `items_api/tests/test_edge_cases.py` (M)
- `items_api/tests/test_integration.py` (MM)
- `locust/data/mock_cv_pool.json` (A)
- `locust/data/seeded_ids.json` (M)
- `locust/locustfile.py` (M)
- `missions_api/FILE_HASHES` (MM)
- `missions_api/HASH` (MM)
- `missions_api/VERSION` (MM)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/analysis_router.py` (MM)
- `missions_api/src/missions/analysis_service.py` (MM)
- `missions_api/src/missions/cache.py` (D)
- `missions_api/src/missions/crud_router.py` (M)
- `missions_api/src/missions/task_state.py` (M)
- `missions_api/src/missions/user_router.py` (M)
- `missions_api/tests/test_cache.py` (D)
- `missions_api/tests/test_crud.py` (MM)
- `missions_api/tests/test_task_state.py` (MM)
- `mock_gemini/Dockerfile` (A)
- `mock_gemini/main.py` (A)
- `monitoring_mcp/FILE_HASHES` (MM)
- `monitoring_mcp/HASH` (MM)
- `monitoring_mcp/VERSION` (MM)
- `monitoring_mcp/mcp_app.py` (M)
- `monitoring_mcp/tests/test_main.py` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (MM)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (MM)
- `platform-engineering/terraform/cr_agent_hr.tf` (MM)
- `platform-engineering/terraform/cr_agent_missions.tf` (MM)
- `platform-engineering/terraform/cr_agent_ops.tf` (MM)
- `platform-engineering/terraform/cr_agent_router.tf` (MM)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (MM)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_monitoring.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/FILE_HASHES` (MM)
- `prompts_api/HASH` (MM)
- `prompts_api/VERSION` (MM)
- `prompts_api/cache.py` (D)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/router.py` (M)
- `prompts_api/tests/test_edge_cases.py` (M)
- `scratch.py` (D)
- `scripts/async_manage_env.sh` (M)
- `scripts/compare_runs.py` (A)
- `scripts/deploy.sh` (MM)
- `scripts/local_up.py` (M)
- `scripts/sync_prompts.py` (M)
- `scripts/test_requirements.txt` (M)
- `shared/FILE_HASHES` (MM)
- `shared/HASH` (MM)
- `shared/VERSION` (MM)
- `shared/bulk_task_state.py` (A)
- `shared/cache.py` (A)
- `shared/database.py` (M)
- `shared/fastapi_utils.py` (MM)
- `shared/mcp_server_utils.py` (M)
- `shared/pyproject.toml` (MM)
- `shared/redis_state.py` (A)
- `shared/schemas/staffing.py` (AM)
- `shared/semaphore_utils.py` (A)
- `shared/tests/test_boundaries.py` (MM)
- `shared/tests/test_cache.py` (A)
- `shared/tests/test_database.py` (M)
- `shared/tests/test_fastapi_utils.py` (MM)
- `shared/tests/test_mcp_server_utils.py` (MM)
- `sre_report.md` (M)
- `sre_report_runner.py` (M)
- `tempo/tempo.yaml` (M)
- `test_jwt.py` (AM)
- `test_load.py` (AM)
- `test_mod.py` (AM)
- `test_pytest_sim.py` (AM)
- `users_api/FILE_HASHES` (MM)
- `users_api/HASH` (MM)
- `users_api/VERSION` (MM)
- `users_api/cache.py` (D)
- `users_api/conftest.py` (MM)
- `users_api/main.py` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/mcp_tools/tools_handlers.py` (M)
- `users_api/src/users/auth_router.py` (M)
- `users_api/src/users/crud_router.py` (MM)
- `users_api/src/users/system_router.py` (MM)
- `users_api/tests/integration/conftest.py` (M)
- `users_api/tests/integration/test_pg_integration.py` (M)
- `users_api/tests/test_edge_cases.py` (M)
- `agent_commons/agent_commons/prompt_loader.py` (??)
- `agent_commons/build/lib/agent_commons/prompt_loader.py` (??)
- `agent_missions_api/hitl_router.py` (??)
- `agent_missions_api/session_router.py` (??)
- `agent_missions_api/tests/test_hitl_endpoints.py` (??)
- `agent_missions_api/tests/test_maybe_trigger_hitl.py` (??)
- `agent_router_api/prompt_loader.py` (??)
- `agent_router_api/tests/test_workflow_agent.py` (??)
- `agent_router_api/tests/test_workflow_agent_perf.py` (??)
- `db_init/FILE_HASHES` (??)
- `db_init/HASH` (??)
- `db_migrations/.dockerignore` (??)
- `frontend/src/components/agent/HitlApproval.vue` (??)
- `locust/.dockerignore` (??)
- `mock_gemini/.dockerignore` (??)
- `test_dir/` (??)

---

## Mise à jour automatique - 2026-05-18 11:07:12

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 2136  | 540  |  75% |
| agent_hr_api     | 1408  | 195  |  86% |
| agent_missions_api | 1267  | 191  |  85% |
| agent_ops_api    | 1260  | 187  |  85% |
| agent_router_api | 2989  | 544  |  82% |
| analytics_mcp    | 924   | 140  |  85% |
| competencies_api | 4626  | 1085 |  77% |
| cv_api           | 9143  | 1546 |  83% |
| drive_api        | 3536  | 416  |  88% |
| items_api        | 2251  | 137  |  94% |
| missions_api     | 2146  | 201  |  91% |
| monitoring_mcp   | 1162  | 134  |  88% |
| platform-engineering | 1497  | 1212 |  19% |
| prompts_api      | 1223  | 276  |  77% |
| shared           | 2206  | 114  |  95% |
| tests            | 78    | 3    |  96% |
| users_api        | 2119  | 353  |  83% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/spec.md` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `changelog.md` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/src/competencies/analytics_router.py` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/eval/test_rag_quality.py` (D)
- `cv_api/pyproject.toml` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/services/data_quality_service.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/items/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `docs/pipelines.md` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `frontend/FILE_HASHES` (M)
- `frontend/HASH` (M)
- `frontend/VERSION` (M)
- `frontend/vitest.log` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/README.md` (M)
- `items_api/VERSION` (M)
- `items_api/src/items/crud_router.py` (M)
- `items_api/src/items/routers/search_router.py` (M)
- `items_api/tests/test_admin_router.py` (M)
- `items_api/tests/test_categories_router.py` (M)
- `items_api/tests/test_crud_router_basic.py` (M)
- `items_api/tests/test_crud_router_bulk.py` (M)
- `items_api/tests/test_delete_user_items.py` (M)
- `items_api/tests/test_edge_cases.py` (M)
- `items_api/tests/test_integration.py` (M)
- `items_api/tests/test_main.py` (M)
- `items_api/tests/test_mcp_tools.py` (M)
- `items_api/tests/test_search_router.py` (M)
- `locust/locustfile.py` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/spec.md` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/spec.md` (M)
- `scripts/deploy.sh` (M)
- `scripts/local_up.py` (M)
- `scripts/seed_data.py` (M)
- `shared/FILE_HASHES` (M)
- `shared/HASH` (M)
- `shared/VERSION` (M)
- `shared/database.py` (M)
- `shared/pyproject.toml` (M)
- `shared/tests/test_boundaries.py` (M)
- `shared/tests/test_database.py` (M)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/README.md` (M)
- `users_api/VERSION` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/users/auth_router.py` (M)
- `cv_api/eval/rag_quality_eval.py` (??)
- `locust/Dockerfile` (??)
- `locust/data/` (??)

---

## Mise à jour automatique - 2026-05-18 10:56:34

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 2136  | 540  |  75% |
| agent_hr_api     | 1408  | 195  |  86% |
| agent_missions_api | 1267  | 191  |  85% |
| agent_ops_api    | 1260  | 187  |  85% |
| agent_router_api | 2989  | 544  |  82% |
| analytics_mcp    | 924   | 140  |  85% |
| competencies_api | 4626  | 1085 |  77% |
| cv_api           | 9143  | 1546 |  83% |
| drive_api        | 3536  | 416  |  88% |
| items_api        | 2141  | 132  |  94% |
| missions_api     | 2146  | 201  |  91% |
| monitoring_mcp   | 1162  | 134  |  88% |
| platform-engineering | 1497  | 1212 |  19% |
| prompts_api      | 1223  | 276  |  77% |
| shared           | 2206  | 115  |  95% |
| tests            | 78    | 3    |  96% |
| users_api        | 2119  | 353  |  83% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/spec.md` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/src/competencies/analytics_router.py` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/eval/test_rag_quality.py` (D)
- `cv_api/pyproject.toml` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/services/data_quality_service.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/items/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `frontend/FILE_HASHES` (M)
- `frontend/HASH` (M)
- `frontend/VERSION` (M)
- `frontend/vitest.log` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/src/items/crud_router.py` (M)
- `items_api/src/items/routers/search_router.py` (M)
- `items_api/tests/test_admin_router.py` (M)
- `items_api/tests/test_categories_router.py` (M)
- `items_api/tests/test_crud_router_basic.py` (M)
- `items_api/tests/test_crud_router_bulk.py` (M)
- `items_api/tests/test_delete_user_items.py` (M)
- `items_api/tests/test_integration.py` (M)
- `items_api/tests/test_main.py` (M)
- `items_api/tests/test_mcp_tools.py` (M)
- `items_api/tests/test_search_router.py` (M)
- `locust/locustfile.py` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/spec.md` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/spec.md` (M)
- `scripts/deploy.sh` (M)
- `scripts/local_up.py` (M)
- `scripts/seed_data.py` (M)
- `shared/FILE_HASHES` (M)
- `shared/HASH` (M)
- `shared/VERSION` (M)
- `shared/database.py` (M)
- `shared/pyproject.toml` (M)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/users/auth_router.py` (M)
- `cv_api/eval/rag_quality_eval.py` (??)
- `locust/Dockerfile` (??)
- `locust/data/` (??)

---

## Mise à jour automatique - 2026-05-16 14:28:34

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 2136  | 540  |  75% |
| agent_hr_api     | 1409  | 195  |  86% |
| agent_missions_api | 1268  | 191  |  85% |
| agent_ops_api    | 1261  | 187  |  85% |
| agent_router_api | 2989  | 544  |  82% |
| analytics_mcp    | 924   | 140  |  85% |
| competencies_api | 4624  | 1081 |  77% |
| cv_api           | 9144  | 1546 |  83% |
| drive_api        | 3536  | 416  |  88% |
| items_api        | 2141  | 132  |  94% |
| missions_api     | 2146  | 201  |  91% |
| monitoring_mcp   | 1162  | 134  |  88% |
| platform-engineering | 1497  | 1212 |  19% |
| prompts_api      | 1223  | 276  |  77% |
| shared           | 2208  | 114  |  95% |
| tests            | 78    | 3    |  96% |
| users_api        | 2113  | 365  |  83% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gitignore` (M)
- `agent_commons/agent_commons.egg-info/PKG-INFO` (M)
- `agent_commons/agent_commons.egg-info/SOURCES.txt` (M)
- `agent_commons/agent_commons.egg-info/requires.txt` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/tests/test_history_routes.py` (M)
- `agent_hr_api/tests/test_main.py` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/tests/test_history.py` (M)
- `agent_missions_api/tests/test_jwt_propagation.py` (M)
- `agent_missions_api/tests/test_main.py` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/tests/test_jwt_propagation.py` (M)
- `agent_ops_api/tests/test_main.py` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/test_main.py` (M)
- `analytics_mcp/Dockerfile` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/src/competencies/tree_router.py` (M)
- `competencies_api/tests/integration/test_pg_integration.py` (M)
- `competencies_api/tests/test_competencies_extra.py` (M)
- `competencies_api/tests/test_integration.py` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/scripts/audit_taxonomy_drops.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/tests/test_analytics_router.py` (M)
- `data_ingestion/requirements.txt` (D)
- `db_init/Dockerfile` (M)
- `db_init/requirements.txt` (D)
- `db_migrations/VERSION` (M)
- `docker-compose.yml` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `frontend/FILE_HASHES` (M)
- `frontend/HASH` (M)
- `frontend/VERSION` (M)
- `frontend/vitest.log` (M)
- `items_api/Dockerfile` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/requirements.txt` (D)
- `missions_api/spec.md` (M)
- `monitoring_mcp/Dockerfile` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/requirements.txt` (D)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/requirements.txt` (D)
- `prompts_api/Dockerfile` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/requirements.txt` (D)
- `prompts_api/spec.md` (M)
- `prompts_api/tests/test_prompts.py` (M)
- `scripts/calibrate_rag.sh` (M)
- `scripts/deploy.sh` (M)
- `scripts/reindex_cv.py` (M)
- `scripts/requirements.txt` (D)
- `scripts/run_rag_eval.sh` (M)
- `scripts/test_requirements.txt` (AM)
- `seed_data.py` (D)
- `shared/FILE_HASHES` (M)
- `shared/HASH` (M)
- `shared/VERSION` (M)
- `shared/pyproject.toml` (M)
- `shared/tests/zero_trust.py` (M)
- `talk/requirements.txt` (D)
- `users_api/Dockerfile` (M)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/requirements.txt` (D)
- `users_api/src/auth.py` (M)
- `users_api/src/users/schemas.py` (M)
- `users_api/tests/test_jwt.py` (D)
- `agent_commons/build/` (??)
- `agent_hr_api/pyproject.toml` (??)
- `agent_hr_api/uv.lock` (??)
- `agent_missions_api/pyproject.toml` (??)
- `agent_missions_api/tests/debug_auth.py` (??)
- `agent_missions_api/tests/debug_test_history.py` (??)
- `agent_missions_api/uv.lock` (??)
- `agent_ops_api/pyproject.toml` (??)
- `agent_ops_api/uv.lock` (??)
- `agent_router_api/pyproject.toml` (??)
- `agent_router_api/uv.lock` (??)
- `analytics_mcp/pyproject.toml` (??)
- `analytics_mcp/uv.lock` (??)
- `competencies_api/pyproject.toml` (??)
- `competencies_api/uv.lock` (??)
- `cv_api/pyproject.toml` (??)
- `cv_api/uv.lock` (??)
- `data_ingestion/pyproject.toml` (??)
- `data_ingestion/uv.lock` (??)
- `db_init/pyproject.toml` (??)
- `db_init/uv.lock` (??)
- `drive_api/pyproject.toml` (??)
- `drive_api/uv.lock` (??)
- `init.sql` (??)
- `items_api/pyproject.toml` (??)
- `items_api/uv.lock` (??)
- `locust/` (??)
- `missions_api/pyproject.toml` (??)
- `missions_api/uv.lock` (??)
- `monitoring_mcp/pyproject.toml` (??)
- `monitoring_mcp/uv.lock` (??)
- `platform-engineering/pyproject.toml` (??)
- `platform-engineering/uv.lock` (??)
- `prompts_api/pyproject.toml` (??)
- `prompts_api/uv.lock` (??)
- `scripts/local_up.py` (??)
- `scripts/migrate_dockerfiles_uv.py` (??)
- `scripts/pyproject.toml` (??)
- `scripts/run_perf_test.sh` (??)
- `scripts/seed_data.py` (??)
- `scripts/uv.lock` (??)
- `talk/pyproject.toml` (??)
- `talk/uv.lock` (??)
- `test_script.sh` (??)
- `users_api/pyproject.toml` (??)
- `users_api/tests/debug_jwt.py` (??)
- `users_api/uv.lock` (??)

---

## Mise à jour automatique - 2026-05-16 11:13:42

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 2167  | 571  |  74% |
| agent_hr_api     | 1546  | 222  |  86% |
| agent_missions_api | 1380  | 252  |  82% |
| agent_ops_api    | 1386  | 212  |  85% |
| agent_router_api | 2644  | 477  |  82% |
| analytics_mcp    | 1126  | 283  |  75% |
| competencies_api | 4876  | 1259 |  74% |
| cv_api           | 9444  | 1768 |  81% |
| drive_api        | 3819  | 624  |  84% |
| items_api        | 2318  | 308  |  87% |
| missions_api     | 2261  | 382  |  83% |
| monitoring_mcp   | 1368  | 248  |  82% |
| platform-engineering | 1497  | 1212 |  19% |
| prompts_api      | 1358  | 421  |  69% |
| shared           | 378   | 165  |  56% |
| tests            | 78    | 3    |  96% |
| users_api        | N/A   | N/A  | N/A  |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `.agents/workflows/analyse-resilience-security-fiability.md` (M)
- `.agents/workflows/analyse-security.md` (M)
- `.agents/workflows/deploy-sh.md` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/debug_jwt.py` (M)
- `agent_hr_api/history_routes.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/mcp_client.py` (M)
- `agent_hr_api/requirements.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/tests/test_history_routes.py` (M)
- `agent_hr_api/tests/test_jwt_propagation.py` (M)
- `agent_hr_api/tests/test_main.py` (M)
- `agent_hr_api/tests/test_zero_trust.py` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/main.py` (M)
- `agent_missions_api/requirements.txt` (M)
- `agent_missions_api/tests/test_zero_trust.py` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/history_routes.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/mcp_client.py` (M)
- `agent_ops_api/requirements.txt` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/tests/test_main.py` (M)
- `agent_ops_api/tests/test_zero_trust.py` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/a2a_tools.py` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/requirements.txt` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/test_guardrail.py` (M)
- `agent_router_api/tests/test_jwt_propagation.py` (M)
- `agent_router_api/tests/test_main.py` (M)
- `agent_router_api/tests/test_zero_trust.py` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/mcp_server.py` (M)
- `analytics_mcp/requirements.txt` (M)
- `analytics_mcp/tests/test_finops_tools.py` (M)
- `analytics_mcp/tools/finops_tools.py` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_app.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/ai_scoring.py` (M)
- `competencies_api/src/competencies/scoring_router.py` (M)
- `competencies_api/tests/test_outbound_propagation.py` (M)
- `competencies_api/tests/test_scoring_pipeline.py` (M)
- `competencies_api/tests/test_scoring_router.py` (M)
- `competencies_api/tests/test_scoring_utils.py` (M)
- `competencies_api/tests/test_zero_trust.py` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_app.py` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/routers/data_quality_router.py` (M)
- `cv_api/src/cvs/routers/taxonomy_router.py` (M)
- `cv_api/src/services/pubsub_service.py` (M)
- `cv_api/src/services/taxonomy_batch_service.py` (M)
- `cv_api/src/services/taxonomy_service.py` (M)
- `cv_api/tests/test_bulk_reanalyse.py` (M)
- `cv_api/tests/test_main.py` (M)
- `cv_api/tests/test_mcp_tools.py` (M)
- `cv_api/tests/test_outbound_propagation.py` (M)
- `cv_api/tests/test_pubsub_handler.py` (M)
- `cv_api/tests/test_zero_trust.py` (M)
- `db_migrations/VERSION` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/main.py` (M)
- `drive_api/mcp_app.py` (M)
- `drive_api/mcp_server.py` (M)
- `drive_api/requirements.txt` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/discovery_service.py` (M)
- `drive_api/src/services/ingestion_kpi_service.py` (M)
- `drive_api/tests/test_discovery_service.py` (M)
- `drive_api/tests/test_google_api_client.py` (M)
- `drive_api/tests/test_main.py` (M)
- `drive_api/tests/test_mcp_tools.py` (M)
- `drive_api/tests/test_zero_trust.py` (M)
- `frontend/FILE_HASHES` (M)
- `frontend/HASH` (M)
- `frontend/VERSION` (M)
- `frontend/package-lock.json` (M)
- `frontend/package.json` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/components/onboarding/OnboardingStep.vue` (M)
- `frontend/src/i18n/index.ts` (M)
- `frontend/src/i18n/locales/en.ts` (M)
- `frontend/src/i18n/locales/fr.ts` (M)
- `frontend/src/services/__tests__/agentApi.spec.ts` (M)
- `frontend/src/services/agentApi.ts` (M)
- `frontend/src/stores/__tests__/chatStore.spec.ts` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/types/index.ts` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/vite.config.ts` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/main.py` (M)
- `items_api/mcp_app.py` (M)
- `items_api/requirements.txt` (M)
- `items_api/tests/test_outbound_propagation.py` (M)
- `items_api/tests/test_zero_trust.py` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/mcp_app.py` (M)
- `missions_api/requirements.txt` (M)
- `missions_api/spec.md` (M)
- `missions_api/tests/test_crud.py` (M)
- `missions_api/tests/test_mcp_tools.py` (M)
- `missions_api/tests/test_outbound_propagation.py` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/README.md` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/context.py` (D)
- `monitoring_mcp/mcp_app.py` (M)
- `monitoring_mcp/mcp_server.py` (M)
- `monitoring_mcp/requirements.txt` (M)
- `monitoring_mcp/tests/test_auth.py` (M)
- `monitoring_mcp/tests/test_logs_tools.py` (M)
- `monitoring_mcp/tests/test_mcp_app.py` (M)
- `monitoring_mcp/tools/logs_tools.py` (M)
- `monitoring_mcp/tools/pipeline_tools.py` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/main.py` (M)
- `prompts_api/mcp_app.py` (M)
- `prompts_api/mcp_server.py` (M)
- `prompts_api/requirements.txt` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/auth.py` (M)
- `prompts_api/tests/test_main.py` (M)
- `prompts_api/tests/test_mcp_tools.py` (M)
- `prompts_api/tests/test_prompts.py` (M)
- `scripts/deploy.sh` (M)
- `scripts/requirements.txt` (M)
- `shared/FILE_HASHES` (M)
- `shared/HASH` (M)
- `shared/VERSION` (M)
- `shared/auth/jwt.py` (M)
- `shared/pyproject.toml` (M)
- `shared/tests/test_auth.py` (M)
- `shared/tests/test_boundaries.py` (M)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/mcp_app.py` (M)
- `users_api/requirements.txt` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/users/auth_router.py` (M)
- `users_api/tests/test_auth_service_account.py` (M)
- `users_api/tests/test_jwt.py` (M)
- `users_api/tests/test_outbound_propagation.py` (M)
- `agent_router_api/tests/test_sessions.py` (??)
- `competencies_api/src/competencies/gemini_cache.py` (??)
- `cv_api/src/gemini_cache.py` (??)
- `frontend/src/components/agent/SessionPanel.vue` (??)
- `frontend/src/test-utils/` (??)
- `items_api/tests/test_edge_cases.py` (??)
- `migrate_mcp_tracer.py` (??)
- `missions_api/tests/test_edge_cases.py` (??)
- `prompts_api/tests/test_edge_cases.py` (??)
- `shared/tests/test_edge_cases.py` (??)
- `test_debug.py` (??)
- `test_overrides.py` (??)
- `users_api/tests/test_edge_cases.py` (??)

---

## Mise à jour automatique - 2026-05-15 17:55:30

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 2167  | 571  |  74% |
| agent_hr_api     | 1546  | 222  |  86% |
| agent_missions_api | 1380  | 252  |  82% |
| agent_ops_api    | 1386  | 212  |  85% |
| agent_router_api | 2644  | 477  |  82% |
| analytics_mcp    | 1138  | 198  |  83% |
| competencies_api | 4890  | 1165 |  76% |
| cv_api           | 9458  | 1677 |  82% |
| drive_api        | 3833  | 530  |  86% |
| items_api        | 2332  | 238  |  90% |
| missions_api     | 2275  | 311  |  86% |
| monitoring_mcp   | 1377  | 175  |  87% |
| platform-engineering | 1497  | 1212 |  19% |
| prompts_api      | 1378  | 330  |  76% |
| shared           | 214   | 1    |  99% |
| tests            | 78    | 3    |  96% |
| users_api        | 2220  | 419  |  81% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/git-push.md` (M)
- `.gitignore` (M)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/__init__.py` (M)
- `agent_commons/agent_commons/mcp_client.py` (M)
- `agent_commons/agent_commons/schemas.py` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/requirements.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/requirements.txt` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/requirements.txt` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/a2a_tools.py` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/requirements.txt` (M)
- `agent_router_api/router.py` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/test_jwt_propagation.py` (M)
- `analytics_mcp/Dockerfile` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/requirements.txt` (M)
- `bootstrap/main.tf` (M)
- `bootstrap/outputs.tf` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/main.py` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/ai_scoring.py` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/scoring_utils.py` (M)
- `competencies_api/tests/test_competencies_crud.py` (M)
- `competencies_api/tests/test_competencies_extra.py` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/main.py` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/services/bulk_service.py` (M)
- `cv_api/src/services/retry_service.py` (M)
- `cv_api/src/services/taxonomy_batch_service.py.bak` (D)
- `cv_api/tests/test_bulk_reanalyse.py` (M)
- `cv_api/tests/test_bulk_service_extended.py` (M)
- `cv_api/tests/test_bulk_service_more.py` (M)
- `docker-compose.yml` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/requirements.txt` (M)
- `drive_api/spec.md` (M)
- `drive_api/tests/test_files_router.py` (M)
- `frontend/VERSION` (M)
- `frontend/package-lock.json` (M)
- `frontend/package.json` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/main.ts` (M)
- `frontend/src/services/agentApi.ts` (M)
- `frontend/src/types/index.ts` (M)
- `frontend/src/views/Admin.vue` (M)
- `frontend/src/views/AdminAvailability.vue` (M)
- `frontend/src/views/AdminBulkImport.vue` (M)
- `frontend/src/views/AdminDeduplication.vue` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/AdminUsers.vue` (M)
- `frontend/src/views/AiOps.vue` (M)
- `frontend/src/views/Competencies.vue` (M)
- `frontend/src/views/DataQuality.vue` (M)
- `frontend/src/views/ExtractionQualityList.vue` (M)
- `frontend/src/views/FinopsAdmin.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/ImportCV.vue` (M)
- `frontend/src/views/InfraMap.vue` (M)
- `frontend/src/views/Login.vue` (M)
- `frontend/src/views/MissionDetail.vue` (M)
- `frontend/src/views/MissionsList.vue` (M)
- `frontend/src/views/Profile.vue` (M)
- `frontend/src/views/PromptsAdmin.vue` (M)
- `frontend/src/views/UserDetail.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/Dockerfile` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/requirements.txt` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/requirements.txt` (M)
- `missions_api/spec.md` (M)
- `monitoring_mcp/Dockerfile` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/requirements.txt` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/scratch_check_env.py` (D)
- `platform-engineering/terraform/scratch_check_tf_env.py` (D)
- `platform-engineering/terraform/scratch_clean_db.py` (D)
- `platform-engineering/terraform/scratch_clean_external_bg.py` (D)
- `platform-engineering/terraform/scratch_cleanup.py` (D)
- `platform-engineering/terraform/scratch_fix_agents.py` (D)
- `platform-engineering/terraform/scratch_fix_names.py` (D)
- `platform-engineering/terraform/scratch_fix_refs.py` (D)
- `platform-engineering/terraform/scratch_gen.py` (D)
- `platform-engineering/terraform/scratch_unroll.py` (D)
- `prompts_api/Dockerfile` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/requirements.txt` (M)
- `prompts_api/spec.md` (M)
- `scripts/deploy.sh` (M)
- `scripts/requirements.txt` (M)
- `users_api/Dockerfile` (M)
- `users_api/requirements.txt` (M)
- `.agents/workflows/deploy-sh.md` (??)
- `agent_commons/agent_commons/circuit_breaker.py` (??)
- `agent_commons/agent_commons/http_resilience.py` (??)
- `agent_commons/tests/test_schemas_agent_response.py` (??)
- `cv_api/src/services/semaphores.py` (??)
- `frontend/src/components/onboarding/` (??)
- `frontend/src/components/ui/LanguageSwitcher.vue` (??)
- `frontend/src/i18n/` (??)
- `frontend/src/stores/__tests__/onboardingStore.spec.ts` (??)
- `frontend/src/stores/onboardingStore.ts` (??)
- `frontend/src/types/__tests__/agentQueryResponse.spec.ts` (??)
- `scripts/terraform_gen.py` (??)
- `scripts/terraform_unroll.py` (??)
- `shared/VERSION` (??)
- `shared/pyproject.toml` (??)
- `shared/tests/test_middleware.py` (??)

---

## Mise à jour automatique - 2026-05-15 15:48:36

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1895  | 458  |  76% |
| agent_hr_api     | 1546  | 222  |  86% |
| agent_missions_api | 1380  | 252  |  82% |
| agent_ops_api    | 1386  | 212  |  85% |
| agent_router_api | 2628  | 464  |  82% |
| analytics_mcp    | 1138  | 198  |  83% |
| competencies_api | 4899  | 1258 |  74% |
| cv_api           | 9417  | 1680 |  82% |
| drive_api        | 3833  | 538  |  86% |
| items_api        | 2332  | 238  |  90% |
| missions_api     | 2275  | 311  |  86% |
| monitoring_mcp   | 1377  | 175  |  87% |
| platform-engineering | 1452  | 1177 |  19% |
| prompts_api      | 1378  | 330  |  76% |
| shared           | 149   | 10   |  93% |
| tests            | 78    | 3    |  96% |
| users_api        | 2220  | 419  |  81% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/mcp_client.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/tests/test_history_routes.py` (M)
- `agent_missions_api/mcp_client.py` (M)
- `agent_ops_api/mcp_client.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/mcp_client.py` (M)
- `agent_router_api/spec.md` (M)
- `analytics_mcp/conftest.py` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_app.py` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/analytics_router.py` (M)
- `competencies_api/src/competencies/competencies_router.py` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/scoring_pipeline.py` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_app.py` (M)
- `cv_api/src/services/bulk_service.py` (M)
- `drive_api/main.py` (M)
- `drive_api/mcp_server.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/google_auth.py` (M)
- `drive_api/src/router.py` (M)
- `drive_api/src/routers/files_router.py` (M)
- `frontend/FILE_HASHES` (M)
- `frontend/HASH` (M)
- `frontend/VERSION` (M)
- `frontend/src/App.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/main.py` (M)
- `items_api/src/items/crud_router.py` (M)
- `missions_api/mcp_server.py` (M)
- `missions_api/spec.md` (M)
- `monitoring_mcp/conftest.py` (M)
- `monitoring_mcp/tools/pipeline_tools.py` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `prompts_api/mcp_server.py` (M)
- `prompts_api/spec.md` (M)
- `competencies_api/src/competencies/analytics_queries.py` (??)
- `competencies_api/src/competencies/suggestions_router.py` (??)
- `competencies_api/src/competencies/tree_router.py` (??)
- `cv_api/src/services/bulk_helpers.py` (??)
- `cv_api/src/services/retry_service.py` (??)
- `drive_api/src/routers/sync_router.py` (??)

---

## Mise à jour automatique - 2026-05-14 08:15:38

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1895  | 458  |  76% |
| agent_hr_api     | 1547  | 222  |  86% |
| agent_missions_api | 1380  | 252  |  82% |
| agent_ops_api    | 1386  | 212  |  85% |
| agent_router_api | 2628  | 464  |  82% |
| analytics_mcp    | 1138  | 198  |  83% |
| competencies_api | 4855  | 1168 |  76% |
| cv_api           | 9417  | 1680 |  82% |
| drive_api        | 3821  | 529  |  86% |
| items_api        | 2320  | 239  |  90% |
| missions_api     | 2275  | 311  |  86% |
| monitoring_mcp   | 1377  | 175  |  87% |
| platform-engineering | 1452  | 1177 |  19% |
| prompts_api      | 1378  | 330  |  76% |
| shared           | 149   | 10   |  93% |
| tests            | 78    | 3    |  96% |
| users_api        | 2220  | 419  |  81% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/conftest.py` (M)
- `agent_hr_api/mcp_client.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/tests/test_create_agent_jwt.py` (M)
- `agent_hr_api/tests/test_history_routes.py` (M)
- `agent_hr_api/tests/test_zero_trust.py` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/tests/test_create_agent_jwt.py` (M)
- `agent_missions_api/tests/test_guardrail.py` (M)
- `agent_missions_api/tests/test_runner_propagation.py` (M)
- `agent_missions_api/tests/test_zero_trust.py` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/conftest.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/tests/test_create_agent_jwt.py` (M)
- `agent_ops_api/tests/test_runner_propagation.py` (M)
- `agent_ops_api/tests/test_zero_trust.py` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/conftest.py` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/conftest.py` (M)
- `agent_router_api/tests/test_guardrail.py` (M)
- `agent_router_api/tests/test_mcp.py` (M)
- `agent_router_api/tests/test_zero_trust.py` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/routers/analytics_router.py` (M)
- `cv_api/src/services/cv_import_service.py` (M)
- `cv_api/src/services/data_quality_service.py` (M)
- `cv_api/tests/test_bulk_reanalyse.py` (M)
- `cv_api/tests/test_data_quality_service.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/discovery_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/routers/files_router.py` (M)
- `drive_api/tests/integration/test_pubsub_integration.py` (M)
- `frontend/FILE_HASHES` (M)
- `frontend/HASH` (M)
- `frontend/VERSION` (M)
- `frontend/vitest.log` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/spec.md` (M)
- `scripts/admin.py` (M)
- `scripts/admin_helpers.py` (M)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)

---

## Mise à jour automatique - 2026-05-13 16:55:02

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1896  | 458  |  76% |
| agent_hr_api     | 1548  | 222  |  86% |
| agent_missions_api | 1379  | 252  |  82% |
| agent_ops_api    | 1385  | 212  |  85% |
| agent_router_api | 2630  | 464  |  82% |
| analytics_mcp    | 1138  | 198  |  83% |
| competencies_api | 4855  | 1168 |  76% |
| cv_api           | 9410  | 1661 |  82% |
| drive_api        | 3776  | 494  |  87% |
| items_api        | 2321  | 238  |  90% |
| missions_api     | 2275  | 310  |  86% |
| monitoring_mcp   | 1377  | 175  |  87% |
| platform-engineering | 1452  | 1177 |  19% |
| prompts_api      | 1378  | 330  |  76% |
| shared           | 149   | 10   |  93% |
| tests            | 78    | 3    |  96% |
| users_api        | 2220  | 418  |  81% |

### Modifications depuis le dernier push

#### Commits non pushés
- [rag-calibrate] prd: golden dataset mis à jour (manual)
- [rag-calibrate] prd: golden dataset mis à jour (manual)
- [rag-calibrate] prd: golden dataset mis à jour (manual)
- [rag-calibrate] prd: golden dataset mis à jour (manual)
- [rag-calibrate] prd: golden dataset mis à jour (manual)
- [rag-calibrate] prd: golden dataset mis à jour (manual)
- fix(cv_api): filter llm hallucinations in taxonomy batch sweep and ensure stable auth token
- fix(competencies): mock IA tests and bulk tree format

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `.gitignore` (M)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/mcp_proxy.py` (M)
- `agent_commons/tests/test_mcp_proxy.py` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/logger.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/tests/test_guardrail.py` (M)
- `agent_hr_api/tests/test_main.py` (M)
- `agent_hr_api/tests/test_runner_propagation.py` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/conftest.py` (M)
- `agent_missions_api/logger.py` (M)
- `agent_missions_api/main.py` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/logger.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/tests/test_main.py` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/logger.py` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/mcp_client.py` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/telemetry.py` (M)
- `agent_router_api/tools_registry.py` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/mcp_server.py` (M)
- `analytics_mcp/tests/test_mcp_app.py` (M)
- `analyze_schemas_coverage.py` (D)
- `audit.sh` (D)
- `audit_script.sh` (D)
- `audit_static.txt` (D)
- `audit_tests.txt` (D)
- `build_extraction_service.py` (D)
- `check_redis_index.py` (D)
- `clean.py` (D)
- `clean_error_prompts.py` (D)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_app.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/auth.py` (M)
- `competencies_api/src/competencies/ai_scoring.py` (M)
- `competencies_api/src/competencies/analytics_router.py` (M)
- `competencies_api/src/competencies/assignments_router.py` (M)
- `competencies_api/src/competencies/evaluations_router.py` (M)
- `competencies_api/src/competencies/finops.py` (M)
- `competencies_api/src/competencies/helpers.py` (M)
- `competencies_api/src/competencies/scoring_pipeline.py` (M)
- `competencies_api/src/competencies/scoring_router.py` (M)
- `competencies_api/src/competencies/scoring_utils.py` (M)
- `competencies_api/tests/test_scoring_pipeline.py` (M)
- `competencies_api/tests/test_scoring_router.py` (M)
- `competencies_api/tools/batch_tools.py` (M)
- `cov_summary.txt` (D)
- `cv_api/Dockerfile` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/logger.py` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_app.py` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/metrics.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/auth.py` (M)
- `cv_api/src/cvs/models.py` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/routers/analytics_router.py` (M)
- `cv_api/src/cvs/routers/bulk_router.py` (M)
- `cv_api/src/cvs/routers/search_router.py` (M)
- `cv_api/src/cvs/schemas.py` (M)
- `cv_api/src/services/bulk_service.py` (M)
- `cv_api/src/services/config.py` (M)
- `cv_api/src/services/cv_extraction_service.py` (M)
- `cv_api/src/services/cv_import_service.py` (M)
- `cv_api/src/services/cv_storage_service.py` (M)
- `cv_api/src/services/data_quality_publisher.py` (M)
- `cv_api/src/services/data_quality_service.py` (M)
- `cv_api/src/services/embedding_service.py` (M)
- `cv_api/src/services/finops.py` (M)
- `cv_api/src/services/profile_service.py` (M)
- `cv_api/src/services/pubsub_service.py` (M)
- `cv_api/src/services/search_service.py` (M)
- `cv_api/src/services/taxonomy_batch_service.py` (M)
- `cv_api/src/services/taxonomy_service.py` (M)
- `cv_api/src/services/utils.py` (M)
- `cv_api/tests/test_bulk_service.py` (M)
- `cv_api/tests/test_cv_extraction_service.py` (M)
- `cv_api/tests/test_data_quality_publisher.py` (M)
- `cv_api/tests/test_data_quality_service.py` (M)
- `cv_api/tests/test_jwt_propagation.py` (M)
- `cv_api/tests/test_pubsub_handler.py` (M)
- `cv_api/tests/test_search_router.py` (M)
- `cv_api/tests/test_search_service.py` (M)
- `cv_api/tests/test_taxonomy_batch_service_succeeded.py` (M)
- `cv_api/tests/test_utils.py` (M)
- `cv_api/tools/taxonomy_tools.py` (M)
- `cv_pytest_out.txt` (D)
- `cv_storage_service_refactored.py` (D)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/cv/changelog.yaml` (M)
- `db_migrations/changelogs/missions/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `docs/looker_studio_setup.md` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/logger.py` (M)
- `drive_api/main.py` (M)
- `drive_api/mcp_app.py` (M)
- `drive_api/mcp_server.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/ingestion_service.py` (M)
- `fix.py` (D)
- `frontend/FILE_HASHES` (M)
- `frontend/HASH` (M)
- `frontend/VERSION` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/components/CVReanalysisPanel.vue` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/components/agent/ConsultantCard.vue` (M)
- `frontend/src/views/Admin.vue` (M)
- `frontend/src/views/DataQuality.vue` (M)
- `frontend/src/views/Help.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/vitest.log` (M)
- `get_coverage.sh` (D)
- `get_fast_coverage.sh` (D)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/main.py` (M)
- `items_api/mcp_app.py` (M)
- `items_api/mcp_server.py` (M)
- `items_api/src/items/admin_router.py` (M)
- `items_api/src/items/crud_router.py` (M)
- `items_api/src/items/routers/search_router.py` (M)
- `items_api/tests/test_admin_router.py` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/logger.py` (M)
- `missions_api/main.py` (M)
- `missions_api/mcp_app.py` (M)
- `missions_api/mcp_server.py` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/analysis_service.py` (M)
- `missions_api/src/missions/models.py` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/logger.py` (M)
- `monitoring_mcp/mcp_app.py` (M)
- `monitoring_mcp/requirements.txt` (M)
- `parse_log.py` (D)
- `platform-engineering/antigravity_sanity_error.md` (D)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/.terraform.lock.hcl` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/lb-internal.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `platform-engineering/test.py` (D)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/logger.py` (M)
- `prompts_api/main.py` (M)
- `prompts_api/mcp_app.py` (M)
- `prompts_api/mcp_server.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/router.py` (M)
- `prompts_api/tests/test_prompts.py` (M)
- `pytest_output.txt` (D)
- `pytest_output_2.txt` (D)
- `pytest_output_3.txt` (D)
- `pytest_output_4.txt` (D)
- `rapport_audit_apis.md` (D)
- `roi.md` (D)
- `run_tests.sh` (D)
- `scratch/replace_filter.py` (D)
- `scratch/steps.json` (D)
- `scratch/test_filter.py` (D)
- `scratch/test_uvicorn_filter.py` (D)
- `scratch/test_uvicorn_log.py` (D)
- `scratch2.py` (D)
- `scripts/a.txt` (D)
- `scripts/analytics_mcp_proxy.py` (D)
- `scripts/b.txt` (D)
- `scripts/deploy.sh` (M)
- `scripts/force_flush_queued.sh` (D)
- `scripts/force_requeue_processing.sh` (D)
- `scripts/test_diff.sh` (D)
- `split_mcp.py` (D)
- `split_tests.py` (D)
- `sre_report.md` (M)
- `sre_report_runner.py` (M)
- `temp_cv_import.py` (D)
- `template_analysis.json` (D)
- `test_leeway.py` (D)
- `tools_extracted.json` (D)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/main.py` (M)
- `users_api/mcp_app.py` (M)
- `users_api/mcp_server.py` (M)
- `users_api/src/users/pubsub.py` (M)
- `analytics_mcp/tools/rag_quality_tools.py` (??)
- `competencies_api/tests/test_assign_bulk_contract.py` (??)
- `cv_api/eval/test_rag_quality.py` (??)
- `cv_api/scripts/` (??)
- `cv_api/src/cvs/routers/admin_router.py` (??)
- `cv_api/tests/integration/test_bulk_pipeline_integration.py` (??)
- `cv_api/tests/test_bulk_contract.py` (??)
- `cv_api/tests/test_taxonomy_pipeline_oidc.py` (??)
- `docs/cv_ingestion_pipeline.md` (??)
- `docs/cv_pipeline_analysis.md` (??)
- `docs/rag_architecture.md` (??)
- `docs/roi.md` (??)
- `frontend/src/components/DriveErrorsPanel.vue` (??)
- `logs/` (??)
- `prompts_api/src/prompts/auth.py` (??)
- `scratch.py` (??)
- `scripts/README.md` (??)
- `scripts/admin.py` (??)
- `scripts/admin_helpers.py` (??)
- `scripts/calibrate_rag.sh` (??)
- `scripts/mark_legacy_errors.py` (??)
- `scripts/reindex_cv.py` (??)
- `scripts/run_rag_eval.sh` (??)
- `trace.log` (??)
- `trace_error.json` (??)
- `trace_full.log` (??)

---

## Mise à jour automatique - 2026-05-11 16:55:11

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1868  | 458  |  75% |
| agent_hr_api     | 1614  | 216  |  87% |
| agent_missions_api | 1375  | 252  |  82% |
| agent_ops_api    | 1458  | 214  |  85% |
| agent_router_api | 2609  | 447  |  83% |
| analytics_mcp    | 1095  | 167  |  85% |
| competencies_api | 4654  | 1090 |  77% |
| cv_api           | 8399  | 1374 |  84% |
| drive_api        | 3767  | 492  |  87% |
| items_api        | 2313  | 238  |  90% |
| missions_api     | 2279  | 319  |  86% |
| monitoring_mcp   | 1371  | 169  |  88% |
| platform-engineering | 1181  | 912  |  23% |
| prompts_api      | 1352  | 338  |  75% |
| scratch          | 58    | 20   |  66% |
| shared           | 149   | 10   |  93% |
| tests            | 78    | 3    |  96% |
| users_api        | 2225  | 418  |  81% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/tests/integration/conftest.py` (M)
- `competencies_api/tests/integration/test_pg_integration.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/tests/integration/test_profile_router_extended.py` (M)
- `drive_api/spec.md` (M)
- `frontend/vitest.log` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/antigravity_sanity_error.md` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `prompts_api/spec.md` (M)
- `cv_pytest_out.txt` (??)
- `pytest_output_2.txt` (??)
- `pytest_output_3.txt` (??)
- `pytest_output_4.txt` (??)

---

## Mise à jour automatique - 2026-05-11 16:33:20

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1868  | 458  |  75% |
| agent_hr_api     | 1610  | 212  |  87% |
| agent_missions_api | 1371  | 248  |  82% |
| agent_ops_api    | 1454  | 210  |  86% |
| agent_router_api | 2605  | 443  |  83% |
| analytics_mcp    | 1091  | 163  |  85% |
| competencies_api | 4591  | 1093 |  76% |
| cv_api           | 8404  | 1391 |  83% |
| drive_api        | 3763  | 488  |  87% |
| items_api        | 2311  | 234  |  90% |
| missions_api     | 2275  | 315  |  86% |
| monitoring_mcp   | 1367  | 165  |  88% |
| platform-engineering | 1161  | 892  |  23% |
| prompts_api      | 1348  | 334  |  75% |
| scratch          | N/A   | N/A  | N/A  |
| shared           | 149   | 10   |  93% |
| tests            | 78    | 3    |  96% |
| users_api        | 2221  | 414  |  81% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `.agents/workflows/go-to-prod.md` (M)
- `agent_commons/agent_commons/runner.py` (M)
- `agent_commons/tests/test_runner_null_safety.py` (M)
- `agent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/logger.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/logger.py` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/logger.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/logger.py` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/test_main.py` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/logger.py` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/logger.py` (M)
- `competencies_api/src/competencies/competencies_router.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `competencies_api/tests/integration/test_pg_integration.py` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/cv_api.generate_taxonomy_tree_sweep.txt` (M)
- `cv_api/logger.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/routers/profile_router.py` (M)
- `cv_api/src/services/config.py` (M)
- `cv_api/src/services/cv_storage_service.py` (M)
- `cv_api/src/services/data_quality_publisher.py` (M)
- `cv_api/src/services/taxonomy_batch_service.py` (M)
- `cv_api/tests/test_taxonomy_service.py` (M)
- `db_migrations/VERSION` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/logger.py` (M)
- `drive_api/spec.md` (M)
- `frontend/FILE_HASHES` (M)
- `frontend/HASH` (M)
- `frontend/VERSION` (M)
- `frontend/src/views/Competencies.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/logger.py` (M)
- `items_api/src/items/routers/categories_router.py` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/logger.py` (M)
- `missions_api/spec.md` (M)
- `missions_api/tests/test_analysis.py` (M)
- `missions_api/tests/test_crud.py` (M)
- `missions_api/tests/test_mcp_tools.py` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/logger.py` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/logger.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/tests/test_prompts.py` (M)
- `scripts/deploy.sh` (M)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/logger.py` (M)
- `users_api/src/users/auth_router.py` (M)
- `agent_missions_api/tests/test_agent_fallback.py` (??)
- `agent_missions_api/tests/test_history.py` (??)
- `audit_static.txt` (??)
- `audit_tests.txt` (??)
- `competencies_api/tests/test_scheduler_control.py` (??)
- `competencies_api/tests/test_scoring_pipeline.py` (??)
- `competencies_api/tests/test_scoring_router.py` (??)
- `cv_api/src/services/profile_service.py` (??)
- `cv_api/src/services/taxonomy_batch_service.py.bak` (??)
- `cv_storage_service_refactored.py` (??)
- `docs/architecture.mmd` (??)
- `frontend/src/views/__tests__/Competencies.spec.ts` (??)
- `items_api/tests/test_admin_router.py` (??)
- `items_api/tests/test_categories_router.py` (??)
- `items_api/tests/test_crud_router_basic.py` (??)
- `items_api/tests/test_crud_router_bulk.py` (??)
- `items_api/tests/test_search_router.py` (??)
- `missions_api/tests/test_cache.py` (??)
- `missions_api/tests/test_document_extractor.py` (??)
- `missions_api/tests/test_helpers.py` (??)
- `missions_api/tests/test_task_state.py` (??)
- `platform-engineering/antigravity_sanity_error.md` (??)
- `pytest_output.txt` (??)
- `scratch/replace_filter.py` (??)
- `scratch/test_filter.py` (??)
- `scratch/test_uvicorn_filter.py` (??)
- `scratch/test_uvicorn_log.py` (??)
- `users_api/tests/test_auth_service_account.py` (??)

---

## Mise à jour automatique - 2026-05-11 09:36:23

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1848  | 456  |  75% |
| agent_hr_api     | 1610  | 212  |  87% |
| agent_missions_api | 1263  | 307  |  76% |
| agent_ops_api    | 1454  | 210  |  86% |
| agent_router_api | 2583  | 443  |  83% |
| analytics_mcp    | 1091  | 163  |  85% |
| competencies_api | 4293  | 1327 |  69% |
| cv_api           | 8384  | 1417 |  83% |
| drive_api        | 3758  | 481  |  87% |
| items_api        | 1775  | 420  |  76% |
| missions_api     | 2071  | 516  |  75% |
| monitoring_mcp   | 1367  | 165  |  88% |
| platform-engineering | 1155  | 886  |  23% |
| prompts_api      | 1294  | 373  |  71% |
| shared           | 149   | 10   |  93% |
| tests            | 78    | 3    |  96% |
| users_api        | 2183  | 422  |  81% |

### Modifications depuis le dernier push

#### Commits non pushés
- fix(mcp): align error responses format

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `.agents/workflows/go-to-prod.md` (M)
- `.gitignore` (M)
- `agent_commons/agent_commons/exception_handler.py` (M)
- `agent_commons/agent_commons/jwt_middleware.py` (M)
- `agent_commons/agent_commons/runner.py` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/conftest.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/pytest.ini` (M)
- `agent_hr_api/setup.cfg` (D)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/agent.py` (M)
- `agent_missions_api/agent_missions_api.system_instruction.txt` (M)
- `agent_missions_api/main.py` (M)
- `agent_missions_api/pytest.ini` (M)
- `agent_missions_api/setup.cfg` (D)
- `agent_missions_api/tests/test_guardrail.py` (M)
- `agent_missions_api/tests/test_main.py` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `agent_ops_api/conftest.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/pytest.ini` (M)
- `agent_ops_api/setup.cfg` (D)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/a2a_tools.py` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/conftest.py` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/pytest.ini` (M)
- `agent_router_api/semantic_cache.py` (M)
- `agent_router_api/session.py` (M)
- `agent_router_api/setup.cfg` (D)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/test_semantic_cache.py` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/auth.py` (M)
- `analytics_mcp/logger.py` (M)
- `analytics_mcp/pytest.ini` (M)
- `analytics_mcp/setup.cfg` (D)
- `analytics_mcp/tests/test_auth.py` (M)
- `audit_script.sh` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/logger.py` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/pytest.ini` (M)
- `competencies_api/setup.cfg` (D)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/ai_scoring.py` (M)
- `competencies_api/src/competencies/analytics_router.py` (M)
- `competencies_api/src/competencies/assignments_router.py` (M)
- `competencies_api/src/competencies/bulk_task_state.py` (M)
- `competencies_api/src/competencies/competencies_router.py` (M)
- `competencies_api/src/competencies/evaluations_router.py` (M)
- `competencies_api/src/competencies/finops.py` (M)
- `competencies_api/src/competencies/helpers.py` (M)
- `competencies_api/src/competencies/models.py` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/scheduler_control.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `competencies_api/src/competencies/scoring_pipeline.py` (M)
- `competencies_api/src/competencies/scoring_router.py` (M)
- `competencies_api/src/competencies/scoring_service.py` (M)
- `competencies_api/src/competencies/scoring_utils.py` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/main.py` (M)
- `cv_api/pytest.ini` (M)
- `cv_api/scratch.py` (D)
- `cv_api/setup.cfg` (D)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/models.py` (M)
- `cv_api/src/cvs/routers/analytics_router.py` (M)
- `cv_api/src/cvs/routers/data_quality_router.py` (M)
- `cv_api/src/cvs/routers/profile_router.py` (M)
- `cv_api/src/cvs/routers/search_router.py` (M)
- `cv_api/src/services/bulk_service.py` (M)
- `cv_api/src/services/cv_import_service.py` (M)
- `cv_api/src/services/cv_storage_service.py` (M)
- `cv_api/src/services/data_quality_service.py` (M)
- `cv_api/src/services/embedding_service.py` (M)
- `cv_api/src/services/taxonomy_batch_service.py` (M)
- `cv_api/src/services/taxonomy_service.py` (M)
- `cv_api/tests/integration/conftest.py` (M)
- `cv_api/tests/test_data_quality_service.py` (M)
- `cv_api/tests/test_main.py` (M)
- `cv_api/tests/test_profile_router.py` (M)
- `cv_api/tests/test_pubsub_handler.py` (M)
- `cv_api/tests/test_taxonomy_service.py` (M)
- `db_migrations/Dockerfile` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/cv/changelog.yaml` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/main.py` (M)
- `drive_api/pytest.ini` (M)
- `drive_api/query_db.py` (M)
- `drive_api/setup.cfg` (D)
- `drive_api/spec.md` (M)
- `drive_api/src/ingestion_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/routers/files_router.py` (M)
- `drive_api/src/schemas.py` (M)
- `drive_api/tests/integration/test_pubsub_integration.py` (M)
- `frontend/VERSION` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/router/index.ts` (M)
- `frontend/src/views/AdminDeduplication.vue` (M)
- `frontend/src/views/DataQuality.vue` (M)
- `frontend/src/views/PromptsAdmin.vue` (M)
- `frontend/src/views/UserDetail.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/conftest.py` (M)
- `items_api/logger.py` (M)
- `items_api/main.py` (M)
- `items_api/pytest.ini` (M)
- `items_api/setup.cfg` (D)
- `items_api/spec.md` (M)
- `items_api/src/items/admin_router.py` (M)
- `items_api/src/items/crud_router.py` (M)
- `items_api/src/items/routers/categories_router.py` (M)
- `items_api/src/items/routers/search_router.py` (M)
- `items_api/src/items/schemas.py` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/pytest.ini` (M)
- `missions_api/setup.cfg` (D)
- `missions_api/spec.md` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/pytest.ini` (M)
- `monitoring_mcp/setup.cfg` (D)
- `platform-engineering/bundled_prompts/agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_missions_api/agent_missions_api.system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/agent_router_api.system_instruction.txt` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/main.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/router.py` (M)
- `prompts_api/src/prompts/schemas.py` (M)
- `prompts_api/tests/test_prompts.py` (M)
- `scratch.py` (D)
- `scripts/agent_prompt_tests.py` (M)
- `scripts/deploy.sh` (M)
- `scripts/requirements.txt` (M)
- `sre_report.md` (M)
- `todo.md` (M)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/logger.py` (M)
- `users_api/main.py` (M)
- `users_api/pytest.ini` (M)
- `users_api/spec.md` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/users/auth_router.py` (M)
- `users_api/src/users/crud_router.py` (M)
- `users_api/src/users/models.py` (M)
- `users_api/src/users/schemas.py` (M)
- `users_api/tests/integration/test_pg_integration.py` (M)
- `users_api/tests/test_integration.py` (M)
- `.agents/workflows/analyse-resilience-security-fiability.md` (??)
- `agent_commons/agent_commons/ui_tools.py` (??)
- `agent_commons/tests/test_exception_handler.py` (??)
- `agent_commons/tests/test_mcp_client_propagation.py` (??)
- `agent_commons/tests/test_runner_display_type.py` (??)
- `agent_commons/tests/test_runner_null_safety.py` (??)
- `agent_hr_api/tests/test_runner_propagation.py` (??)
- `agent_missions_api/tests/test_runner_propagation.py` (??)
- `agent_ops_api/tests/test_runner_propagation.py` (??)
- `agent_router_api/tests/test_a2a_propagation.py` (??)
- `check_redis_index.py` (??)
- `clean.py` (??)
- `clean_error_prompts.py` (??)
- `competencies_api/tests/test_outbound_propagation.py` (??)
- `cov_summary.txt` (??)
- `cv_api/tests/integration/test_profile_router_extended.py` (??)
- `cv_api/tests/integration/test_search_router_extended.py` (??)
- `cv_api/tests/test_analytics_router.py` (??)
- `cv_api/tests/test_bulk_service_extended.py` (??)
- `cv_api/tests/test_bulk_service_more.py` (??)
- `cv_api/tests/test_cv_extraction_service.py` (??)
- `cv_api/tests/test_cv_storage_service.py` (??)
- `cv_api/tests/test_embedding_service.py` (??)
- `cv_api/tests/test_import_router.py` (??)
- `cv_api/tests/test_outbound_propagation.py` (??)
- `cv_api/tests/test_search_router.py` (??)
- `cv_api/tests/test_search_service.py` (??)
- `cv_api/tests/test_task_state.py` (??)
- `cv_api/tests/test_taxonomy_batch_service_extended.py` (??)
- `cv_api/tests/test_taxonomy_batch_service_succeeded.py` (??)
- `cv_api/tests/test_utils.py` (??)
- `frontend/FILE_HASHES` (??)
- `frontend/HASH` (??)
- `frontend/src/views/ExtractionQualityList.vue` (??)
- `get_coverage.sh` (??)
- `get_fast_coverage.sh` (??)
- `items_api/tests/test_contract.py` (??)
- `items_api/tests/test_outbound_propagation.py` (??)
- `missions_api/tests/test_outbound_propagation.py` (??)
- `parse_log.py` (??)
- `rapport_audit_apis.md` (??)
- `scratch/` (??)
- `shared/FILE_HASHES` (??)
- `shared/HASH` (??)
- `shared/middlewares.py` (??)
- `split_tests.py` (??)
- `sre_report_runner.py` (??)
- `test_leeway.py` (??)
- `users_api/tests/test_contract.py` (??)
- `users_api/tests/test_crud_extended.py` (??)
- `users_api/tests/test_extended_coverage.py` (??)
- `users_api/tests/test_jwt.py` (??)
- `users_api/tests/test_main_extended.py` (??)
- `users_api/tests/test_mcp_extended.py` (??)
- `users_api/tests/test_outbound_propagation.py` (??)

---

## Mise à jour automatique - 2026-05-06 12:50:09

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1606  | 502  |  69% |
| agent_hr_api     | 1582  | 220  |  86% |
| agent_missions_api | 1236  | 316  |  74% |
| agent_ops_api    | 1425  | 215  |  85% |
| agent_router_api | 2496  | 417  |  83% |
| analytics_mcp    | 1074  | 148  |  86% |
| competencies_api | 4255  | 1321 |  69% |
| cv_api           | 6955  | 2311 |  67% |
| drive_api        | 3745  | 476  |  87% |
| items_api        | 1719  | 454  |  74% |
| missions_api     | 2031  | 508  |  75% |
| monitoring_mcp   | 1367  | 165  |  88% |
| platform-engineering | 1155  | 886  |  23% |
| prompts_api      | 1288  | 390  |  70% |
| shared           | 139   | 0    | 100% |
| tests            | 78    | 3    |  96% |
| users_api        | 1821  | 587  |  68% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_commons/agent_commons/runner.py` (M)
- `agent_commons/agent_commons/schemas.py` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/FILE_HASHES` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/pytest.ini` (M)
- `agent_hr_api/requirements.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/FILE_HASHES` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/pytest.ini` (M)
- `agent_missions_api/requirements.txt` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/FILE_HASHES` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/pytest.ini` (M)
- `agent_ops_api/requirements.txt` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/FILE_HASHES` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/a2a_tools.py` (M)
- `agent_router_api/pytest.ini` (M)
- `agent_router_api/requirements.txt` (M)
- `agent_router_api/spec.md` (M)
- `analytics_mcp/Dockerfile` (M)
- `analytics_mcp/FILE_HASHES` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/pytest.ini` (M)
- `analytics_mcp/requirements.txt` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/FILE_HASHES` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/pytest.ini` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/tests/test_mcp_tools.py` (M)
- `competencies_api/tools/tree_tools.py` (M)
- `competencies_api/tools/user_tools.py` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/FILE_HASHES` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/conftest.py` (M)
- `cv_api/pytest.ini` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/routers/profile_router.py` (M)
- `cv_api/src/services/cv_storage_service.py` (M)
- `cv_api/src/services/data_quality_publisher.py` (M)
- `cv_api/src/services/taxonomy_batch_service.py` (M)
- `cv_api/test_client.py` (D)
- `cv_api/test_fastapi.py` (D)
- `cv_api/test_validation.py` (D)
- `cv_api/tests/test_data_quality_publisher.py` (M)
- `cv_api/tests/test_mcp_tools.py` (M)
- `db_init/Dockerfile` (M)
- `db_migrations/Dockerfile` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/FILE_HASHES` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/pytest.ini` (M)
- `drive_api/requirements.txt` (M)
- `drive_api/run_test.py` (D)
- `drive_api/spec.md` (M)
- `drive_api/test_debug.py` (D)
- `frontend/Dockerfile` (M)
- `frontend/VERSION` (M)
- `frontend/src/views/AdminDeduplication.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/Dockerfile` (M)
- `items_api/FILE_HASHES` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/pytest.ini` (M)
- `items_api/requirements.txt` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/FILE_HASHES` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/mcp_server.py` (M)
- `missions_api/pytest.ini` (M)
- `missions_api/requirements.txt` (M)
- `missions_api/spec.md` (M)
- `missions_api/tests/test_mcp_tools.py` (M)
- `monitoring_mcp/Dockerfile` (M)
- `monitoring_mcp/FILE_HASHES` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/pytest.ini` (M)
- `monitoring_mcp/requirements.txt` (M)
- `platform-engineering/Dockerfile` (M)
- `platform-engineering/bundled_prompts/agent_hr_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/agent_missions_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/agent_ops_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/cv_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/missions_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/prompts_api/requirements.txt` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/providers.tf` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `platform-engineering/terraform/scratch_unroll.py` (M)
- `prompts_api/Dockerfile` (M)
- `prompts_api/FILE_HASHES` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/requirements.txt` (M)
- `prompts_api/spec.md` (M)
- `run_tests.sh` (M)
- `scripts/deploy.sh` (M)
- `scripts/run_tests.sh` (M)
- `test_auth.py` (D)
- `test_competencies_500.py` (D)
- `test_db.py` (D)
- `test_none.py` (D)
- `test_pyd.py` (D)
- `test_pydantic_generic.py` (D)
- `test_tokens.py` (D)
- `users_api/Dockerfile` (M)
- `users_api/FILE_HASHES` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/pytest.ini` (M)
- `users_api/requirements.txt` (M)
- `users_api/setup.cfg` (D)
- `users_api/spec.md` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/mcp_tools/tools_handlers.py` (M)
- `users_api/src/users/crud_router.py` (M)
- `users_api/tests/test_mcp_tools.py` (M)
- `agent_commons/tests/test_runner_tool_budget.py` (??)
- `agent_router_api/tests/test_confidence_scorer.py` (??)
- `cv_api/src/services/batch_parsers.py` (??)

---

## Mise à jour automatique - 2026-05-06 11:16:57

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1440  | 551  |  62% |
| agent_hr_api     | 1582  | 220  |  86% |
| agent_missions_api | 1236  | 316  |  74% |
| agent_ops_api    | 1425  | 215  |  85% |
| agent_router_api | 2367  | 427  |  82% |
| analytics_mcp    | 1074  | 148  |  86% |
| competencies_api | 4246  | 1321 |  69% |
| cv_api           | 6781  | 2323 |  66% |
| drive_api        | 3798  | 529  |  86% |
| items_api        | 1719  | 454  |  74% |
| missions_api     | 2020  | 508  |  75% |
| monitoring_mcp   | 1367  | 165  |  88% |
| platform-engineering | 1155  | 886  |  23% |
| prompts_api      | 1288  | 390  |  70% |
| shared           | 139   | 0    | 100% |
| tests            | 79    | 4    |  95% |
| users_api        | 1803  | 585  |  68% |

### Modifications depuis le dernier push

#### Commits non pushés
- Add shared/schemas model_validate to integration tests + fix cv_api bugs
- Add psycopg2-binary to test_env requirements
- Add py_compile gate to run_tests and git-push
- Fix ModuleNotFoundError shared in agent_commons

#### Fichiers (non commités)
- `gent_commons/agent_commons/guardrails.py` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/mcp_client.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/agent_missions_api.system_instruction.txt` (M)
- `agent_missions_api/mcp_client.py` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `agent_ops_api/mcp_client.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/a2a_tools.py` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/mcp_client.py` (M)
- `agent_router_api/spec.md` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/scoring_router.py` (M)
- `competencies_api/tests/integration/conftest.py` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/conftest.py` (M)
- `cv_api/pytest.ini` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/services/config.py` (M)
- `cv_api/src/services/cv_extraction_service.py` (M)
- `cv_api/src/services/pubsub_service.py` (M)
- `cv_api/src/services/taxonomy_batch_service.py` (M)
- `cv_api/tests/integration/conftest.py` (M)
- `db_migrations/Dockerfile` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `docs/pipelines.md` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/models.py` (M)
- `frontend/HASH` (D)
- `frontend/VERSION` (M)
- `frontend/vitest.log` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/analysis_service.py` (M)
- `missions_api/tests/integration/conftest.py` (M)
- `missions_api/tests/test_analysis.py` (M)
- `missions_api/tests/test_crud.py` (M)
- `missions_api/tests/test_security_upload.py` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/tests/test_mcp_app.py` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `platform-engineering/terraform/scheduler.tf` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/prompts_api.error_correction.txt` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/tests/integration/conftest.py` (M)
- `scripts/deploy.sh` (M)
- `scripts/run_tests.sh` (M)
- `shared/HASH` (D)
- `temp_pubsub.py` (D)
- `tests/test_mcp_ui_meta.py` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)
- `users_api/tests/integration/conftest.py` (M)
- `agent_commons/tests/test_guardrail_ops_metrics.py` (??)
- `agent_hr_api/FILE_HASHES` (??)
- `agent_missions_api/FILE_HASHES` (??)
- `agent_ops_api/FILE_HASHES` (??)
- `agent_router_api/FILE_HASHES` (??)
- `agent_router_api/tests/test_circuit_breaker.py` (??)
- `analytics_mcp/FILE_HASHES` (??)
- `competencies_api/FILE_HASHES` (??)
- `cv_api/FILE_HASHES` (??)
- `cv_api/src/cvs/routers/data_quality_router.py` (??)
- `cv_api/src/services/data_quality_publisher.py` (??)
- `cv_api/tests/test_data_quality_publisher.py` (??)
- `drive_api/FILE_HASHES` (??)
- `items_api/FILE_HASHES` (??)
- `missions_api/FILE_HASHES` (??)
- `monitoring_mcp/FILE_HASHES` (??)
- `prompts_api/FILE_HASHES` (??)
- `scripts/a.txt` (??)
- `scripts/b.txt` (??)
- `scripts/test_diff.sh` (??)
- `users_api/FILE_HASHES` (??)

---

## Mise à jour automatique - 2026-05-06 00:40:27

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1299  | 551  |  58% |
| agent_hr_api     | 1575  | 217  |  86% |
| agent_missions_api | 1229  | 313  |  75% |
| agent_ops_api    | 1417  | 212  |  85% |
| agent_router_api | N/A   | N/A  | N/A  |
| analytics_mcp    | 1082  | 154  |  86% |
| competencies_api | N/A   | N/A  | N/A  |
| cv_api           | N/A   | N/A  | N/A  |
| drive_api        | N/A   | N/A  | N/A  |
| items_api        | N/A   | N/A  | N/A  |
| missions_api     | N/A   | N/A  | N/A  |
| monitoring_mcp   | 1358  | 152  |  89% |
| platform-engineering | 1155  | 886  |  23% |
| prompts_api      | N/A   | N/A  | N/A  |
| shared           | 139   | 0    | 100% |
| tests            | 79    | 4    |  95% |
| users_api        | N/A   | N/A  | N/A  |

### Modifications depuis le dernier push

#### Commits non pushés
- Fix PEP8 compliance and pipeline test failures

#### Fichiers (non commités)
- `gent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/main.py` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/cache.py` (M)
- `competencies_api/conftest.py` (M)
- `competencies_api/main.py` (M)
- `competencies_api/pytest.ini` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/evaluations_router.py` (M)
- `competencies_api/src/competencies/scoring_router.py` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/main.py` (M)
- `cv_api/pytest.ini` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/routers/analytics_router.py` (M)
- `cv_api/src/cvs/routers/profile_router.py` (M)
- `cv_api/src/cvs/routers/search_router.py` (M)
- `cv_api/src/services/bulk_service.py` (M)
- `cv_api/src/services/cv_extraction_service.py` (M)
- `cv_api/src/services/cv_storage_service.py` (M)
- `cv_api/src/services/pubsub_service.py` (M)
- `cv_api/src/services/taxonomy_batch_service.py` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/main.py` (M)
- `drive_api/pytest.ini` (M)
- `drive_api/requirements.txt` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/discovery_service.py` (M)
- `drive_api/src/routers/files_router.py` (M)
- `drive_api/src/routers/folders_router.py` (M)
- `drive_api/src/routers/ingestion_router.py` (M)
- `drive_api/tests/test_dlq_router.py` (M)
- `drive_api/tests/test_drive_service_offboarding.py` (M)
- `drive_api/tests/test_folders.py` (M)
- `frontend/VERSION` (M)
- `frontend/vitest.log` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/cache.py` (M)
- `items_api/conftest.py` (M)
- `items_api/main.py` (M)
- `items_api/mcp_server.py` (M)
- `items_api/pytest.ini` (M)
- `items_api/requirements.txt` (M)
- `items_api/spec.md` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/pytest.ini` (M)
- `missions_api/requirements.txt` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/crud_router.py` (M)
- `missions_api/tests/test_crud.py` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/main.py` (M)
- `prompts_api/pytest.ini` (M)
- `prompts_api/requirements.txt` (M)
- `run_tests.sh` (M)
- `scripts/deploy.sh` (M)
- `scripts/requirements.txt` (M)
- `scripts/run_tests.sh` (M)
- `shared/schemas/__init__.py` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/cache.py` (M)
- `users_api/conftest.py` (M)
- `users_api/main.py` (M)
- `users_api/pytest.ini` (M)
- `users_api/requirements.txt` (M)
- `users_api/spec.md` (M)
- `users_api/src/users/auth_router.py` (M)
- `users_api/tests/test_integration.py` (M)
- `analytics_mcp/tests/test_auth.py` (??)
- `analytics_mcp/tests/test_finops_tools.py` (??)
- `analytics_mcp/tests/test_market_tools.py` (??)
- `analytics_mcp/tests/test_mcp_app.py` (??)
- `analytics_mcp/tests/test_mcp_server_extra.py` (??)
- `competencies_api/tests/integration/` (??)
- `cv_api/tests/integration/` (??)
- `drive_api/output.txt` (??)
- `drive_api/pytest_output.txt` (??)
- `drive_api/run_test.py` (??)
- `drive_api/src/services/` (??)
- `drive_api/test_debug.py` (??)
- `drive_api/tests/integration/` (??)
- `drive_api/tests/test_discovery_service.py` (??)
- `drive_api/tests/test_discovery_service.py.orig` (??)
- `drive_api/tests/test_files_router.py` (??)
- `drive_api/tests/test_folder_service.py` (??)
- `drive_api/tests/test_folders_router.py` (??)
- `drive_api/tests/test_google_api_client.py` (??)
- `drive_api/tests/test_ingestion_kpi_service.py` (??)
- `drive_api/tests/test_ingestion_router.py` (??)
- `drive_api/tests/test_tree_resolution.py` (??)
- `items_api/tests/integration/` (??)
- `items_api/tools/` (??)
- `missions_api/tests/integration/` (??)
- `monitoring_mcp/tests/test_auth.py` (??)
- `monitoring_mcp/tests/test_data_tools.py` (??)
- `monitoring_mcp/tests/test_infra_tools.py` (??)
- `monitoring_mcp/tests/test_logs_tools.py` (??)
- `monitoring_mcp/tests/test_mcp_app.py` (??)
- `monitoring_mcp/tests/test_pipeline_tools.py` (??)
- `prompts_api/tests/integration/` (??)
- `shared/schemas/auth.py` (??)
- `users_api/tests/integration/` (??)

---

## Mise à jour automatique - 2026-05-05 22:05:10

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1300  | 551  |  58% |
| agent_hr_api     | 133242 | 131890 |   1% |
| agent_missions_api | 1229  | 313  |  75% |
| agent_ops_api    | 1409  | 210  |  85% |
| agent_router_api | 2139  | 427  |  80% |
| analytics_mcp    | 747   | 306  |  59% |
| competencies_api | 4077  | 1296 |  68% |
| cv_api           | 6069  | 2064 |  66% |
| drive_api        | 2650  | 963  |  64% |
| items_api        | 1592  | 460  |  71% |
| missions_api     | 1863  | 523  |  72% |
| monitoring_mcp   | 983   | 388  |  61% |
| platform-engineering | 1225  | 955  |  22% |
| prompts_api      | 1188  | 379  |  68% |
| shared           | 134   | 0    | 100% |
| tests            | 79    | 3    |  96% |
| users_api        | 1658  | 572  |  66% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `.dockerignore` (M)
- `.gitignore` (M)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/mcp_client.py` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/spec.md` (M)
- `analytics_mcp/Dockerfile` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/mcp_server.py` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/conftest.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/ai_scoring.py` (M)
- `competencies_api/src/competencies/analytics_router.py` (M)
- `competencies_api/src/competencies/assignments_router.py` (M)
- `competencies_api/src/competencies/bulk_task_state.py` (M)
- `competencies_api/src/competencies/competencies_router.py` (M)
- `competencies_api/src/competencies/evaluations_router.py` (M)
- `competencies_api/src/competencies/helpers.py` (M)
- `competencies_api/src/competencies/models.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `competencies_api/src/competencies/scoring_pipeline.py` (M)
- `competencies_api/tests/test_mcp_tools.py` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/conftest.py` (M)
- `cv_api/cv_api.generate_taxonomy_tree_sweep.txt` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/models.py` (M)
- `cv_api/src/cvs/routers/profile_router.py` (M)
- `cv_api/src/cvs/routers/taxonomy_router.py` (M)
- `cv_api/src/cvs/schemas.py` (M)
- `cv_api/src/cvs/task_state.py` (M)
- `cv_api/src/services/bulk_service.py` (M)
- `cv_api/src/services/cv_import_service.py` (M)
- `cv_api/src/services/search_service.py` (M)
- `cv_api/src/services/taxonomy_service.py` (M)
- `cv_api/tests/test_main.py` (M)
- `cv_api/tests/test_pubsub_handler.py` (M)
- `cv_api/tests/test_taxonomy_router.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/competencies/003-add-competency-aliases.yaml` (M)
- `db_migrations/changelogs/competencies/changelog.yaml` (M)
- `db_migrations/changelogs/cv/changelog.yaml` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `db_migrations/changelogs/items/changelog.yaml` (M)
- `db_migrations/changelogs/missions/changelog.yaml` (M)
- `db_migrations/changelogs/users/changelog.yaml` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/routers/dlq_router.py` (M)
- `drive_api/src/routers/files_router.py` (M)
- `drive_api/src/routers/ingestion_router.py` (M)
- `frontend/VERSION` (M)
- `frontend/coverage/clover.xml` (M)
- `frontend/coverage/coverage-final.json` (M)
- `frontend/coverage/index.html` (M)
- `frontend/coverage/src/App.vue.html` (M)
- `frontend/coverage/src/components/CVImportMonitor.vue.html` (M)
- `frontend/coverage/src/components/CVReanalysisPanel.vue.html` (M)
- `frontend/coverage/src/components/CompetencyEvaluationPanel.vue.html` (M)
- `frontend/coverage/src/components/CompetencyNode.vue.html` (M)
- `frontend/coverage/src/components/ConsultantProfile.vue.html` (M)
- `frontend/coverage/src/components/DriveAdminPanel.vue.html` (M)
- `frontend/coverage/src/components/DriveTreeGraph.vue.html` (M)
- `frontend/coverage/src/components/StarRating.vue.html` (M)
- `frontend/coverage/src/components/TaxonomySuggestions.vue.html` (M)
- `frontend/coverage/src/components/agent/AgentExpertTerminal.vue.html` (M)
- `frontend/coverage/src/components/agent/CandidateProfileCard.vue.html` (M)
- `frontend/coverage/src/components/agent/CloudRunLogsViewer.vue.html` (M)
- `frontend/coverage/src/components/agent/ConsultantAvailabilityCard.vue.html` (M)
- `frontend/coverage/src/components/agent/ConsultantCard.vue.html` (M)
- `frontend/coverage/src/components/agent/DebugPromptCard.vue.html` (M)
- `frontend/coverage/src/components/agent/FinopsBadge.vue.html` (M)
- `frontend/coverage/src/components/agent/ItemCard.vue.html` (M)
- `frontend/coverage/src/components/agent/MissionCard.vue.html` (M)
- `frontend/coverage/src/components/agent/SystemHealthCard.vue.html` (M)
- `frontend/coverage/src/components/agent/ToolExecutionList.vue.html` (M)
- `frontend/coverage/src/components/agent/index.html` (M)
- `frontend/coverage/src/components/index.html` (M)
- `frontend/coverage/src/components/ui/BaseButton.vue.html` (M)
- `frontend/coverage/src/components/ui/PageHeader.vue.html` (M)
- `frontend/coverage/src/components/ui/ToastNotification.vue.html` (M)
- `frontend/coverage/src/components/ui/index.html` (M)
- `frontend/coverage/src/data/docs.ts.html` (M)
- `frontend/coverage/src/data/index.html` (M)
- `frontend/coverage/src/index.html` (M)
- `frontend/coverage/src/main.ts.html` (M)
- `frontend/coverage/src/router/index.html` (M)
- `frontend/coverage/src/router/index.ts.html` (M)
- `frontend/coverage/src/services/agentApi.ts.html` (M)
- `frontend/coverage/src/services/auth.ts.html` (M)
- `frontend/coverage/src/services/index.html` (M)
- `frontend/coverage/src/stores/chatStore.ts.html` (M)
- `frontend/coverage/src/stores/index.html` (M)
- `frontend/coverage/src/stores/uxStore.ts.html` (M)
- `frontend/coverage/src/types/index.html` (M)
- `frontend/coverage/src/types/index.ts.html` (M)
- `frontend/coverage/src/utils/index.html` (M)
- `frontend/coverage/src/utils/treeify.ts.html` (M)
- `frontend/coverage/src/views/Admin.vue.html` (M)
- `frontend/coverage/src/views/AdminAvailability.vue.html` (M)
- `frontend/coverage/src/views/AdminBulkImport.vue.html` (M)
- `frontend/coverage/src/views/AdminDeduplication.vue.html` (M)
- `frontend/coverage/src/views/AdminReanalysis.vue.html` (M)
- `frontend/coverage/src/views/AdminUsers.vue.html` (M)
- `frontend/coverage/src/views/AgentsDocs.vue.html` (M)
- `frontend/coverage/src/views/AiOps.vue.html` (M)
- `frontend/coverage/src/views/Competencies.vue.html` (M)
- `frontend/coverage/src/views/DataQuality.vue.html` (M)
- `frontend/coverage/src/views/Docs.vue.html` (M)
- `frontend/coverage/src/views/FinopsAdmin.vue.html` (M)
- `frontend/coverage/src/views/Help.vue.html` (M)
- `frontend/coverage/src/views/Home.vue.html` (M)
- `frontend/coverage/src/views/ImportCV.vue.html` (M)
- `frontend/coverage/src/views/InfraMap.vue.html` (M)
- `frontend/coverage/src/views/Login.vue.html` (M)
- `frontend/coverage/src/views/MissionDetail.vue.html` (M)
- `frontend/coverage/src/views/MissionsList.vue.html` (M)
- `frontend/coverage/src/views/Profile.vue.html` (M)
- `frontend/coverage/src/views/PromptsAdmin.vue.html` (M)
- `frontend/coverage/src/views/Registry.vue.html` (M)
- `frontend/coverage/src/views/Specs.vue.html` (M)
- `frontend/coverage/src/views/UserDetail.vue.html` (M)
- `frontend/coverage/src/views/index.html` (M)
- `frontend/src/components/CompetencyNode.vue` (M)
- `frontend/src/components/DriveTreeGraph.vue` (M)
- `frontend/src/components/agent/MissionCard.vue` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/Competencies.vue` (M)
- `frontend/src/views/DataQuality.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/Dockerfile` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/conftest.py` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/analysis_service.py` (M)
- `monitoring_mcp/Dockerfile` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/mcp_app.py` (M)
- `monitoring_mcp/mcp_server.py` (M)
- `monitoring_mcp/tests/test_mcp_server.py` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `prompts_api/Dockerfile` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/cache.py` (M)
- `prompts_api/database.py` (M)
- `prompts_api/main.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/router.py` (M)
- `scripts/deploy.sh` (M)
- `scripts/requirements.txt` (M)
- `sre_report.md` (M)
- `users_api/Dockerfile` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/mcp_tools/tools_handlers.py` (M)
- `agent_hr_api/pytest.ini` (??)
- `agent_hr_api/setup.cfg` (??)
- `agent_missions_api/pytest.ini` (??)
- `agent_missions_api/setup.cfg` (??)
- `agent_ops_api/pytest.ini` (??)
- `agent_ops_api/setup.cfg` (??)
- `agent_router_api/pytest.ini` (??)
- `agent_router_api/setup.cfg` (??)
- `analytics_mcp/pytest.ini` (??)
- `analytics_mcp/setup.cfg` (??)
- `analytics_mcp/tools/` (??)
- `analyze_schemas_coverage.py` (??)
- `audit.sh` (??)
- `build_extraction_service.py` (??)
- `competencies_api/pytest.ini` (??)
- `competencies_api/setup.cfg` (??)
- `competencies_api/tests/test_schemas.py` (??)
- `competencies_api/tools/` (??)
- `cv_api/pytest.ini` (??)
- `cv_api/setup.cfg` (??)
- `cv_api/src/cvs/routers/taxonomy_quality.py` (??)
- `cv_api/src/services/cv_extraction_service.py` (??)
- `cv_api/src/services/cv_storage_service.py` (??)
- `cv_api/src/services/pubsub_service.py` (??)
- `cv_api/src/services/taxonomy_batch_service.py` (??)
- `cv_api/test_client.py` (??)
- `cv_api/test_fastapi.py` (??)
- `cv_api/test_validation.py` (??)
- `cv_api/tests/test_profile_router.py` (??)
- `cv_api/tests/test_schemas.py` (??)
- `cv_api/tools/` (??)
- `docs/adr/0015-contrats-interface-shared-schemas-pydantic-fail-fast.md` (??)
- `drive_api/pytest.ini` (??)
- `drive_api/setup.cfg` (??)
- `drive_api/src/discovery_service.py` (??)
- `drive_api/src/ingestion_service.py` (??)
- `drive_api/tests/test_drive_service_offboarding.py` (??)
- `drive_api/tests/test_schemas.py` (??)
- `fix.py` (??)
- `frontend/coverage/src/components/agent/CompetencyBadge.vue.html` (??)
- `frontend/coverage/src/components/agent/CompetencyList.vue.html` (??)
- `frontend/coverage/src/components/agent/EvaluationCard.vue.html` (??)
- `frontend/coverage/src/components/agent/EvaluationTable.vue.html` (??)
- `frontend/src/utils/__tests__/apiContract.spec.ts` (??)
- `frontend/src/utils/apiContract.ts` (??)
- `items_api/pytest.ini` (??)
- `items_api/setup.cfg` (??)
- `missions_api/pytest.ini` (??)
- `missions_api/setup.cfg` (??)
- `monitoring_mcp/pytest.ini` (??)
- `monitoring_mcp/setup.cfg` (??)
- `prompts_api/pytest.ini` (??)
- `prompts_api/tests/test_schemas.py` (??)
- `scratch.py` (??)
- `scratch2.py` (??)
- `shared/` (??)
- `split_mcp.py` (??)
- `talk/` (??)
- `temp_cv_import.py` (??)
- `temp_pubsub.py` (??)
- `template_analysis.json` (??)
- `test_auth.py` (??)
- `test_competencies_500.py` (??)
- `test_db.py` (??)
- `test_none.py` (??)
- `test_pyd.py` (??)
- `test_pydantic_generic.py` (??)
- `test_tokens.py` (??)
- `tools_extracted.json` (??)
- `users_api/pytest.ini` (??)
- `users_api/setup.cfg` (??)

---

## Mise à jour automatique - 2026-05-04 15:08:55

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1293  | 546  |  58% |
| agent_hr_api     | 1567  | 215  |  86% |
| agent_missions_api | 1229  | 313  |  75% |
| agent_ops_api    | 1390  | 200  |  86% |
| agent_router_api | 2139  | 405  |  81% |
| analytics_mcp    | 734   | 307  |  58% |
| competencies_api | 3883  | 1201 |  69% |
| cv_api           | 6069  | 2064 |  66% |
| drive_api        | 2481  | 1063 |  57% |
| items_api        | 1592  | 460  |  71% |
| missions_api     | 1852  | 518  |  72% |
| monitoring_mcp   | 983   | 389  |  60% |
| platform-engineering | 1155  | 885  |  23% |
| prompts_api      | 1152  | 386  |  66% |
| tests            | 79    | 3    |  96% |
| users_api        | 1658  | 572  |  66% |

### Modifications depuis le dernier push

#### Commits non pushés
- Chore: Nettoyage scripts scratch/patch, reorganisation tests dans tests/

#### Fichiers (non commités)
- `gent_hr_api/conftest.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_ops_api/conftest.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/spec.md` (M)
- `cv_api/spec.md` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/routers/folders_router.py` (M)
- `frontend/vitest.log` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `prompts_api/spec.md` (M)
- `users_api/spec.md` (M)

---

## Mise à jour automatique - 2026-05-04 12:31:15

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1293  | 546  |  58% |
| agent_hr_api     | 1569  | 216  |  86% |
| agent_missions_api | 1236  | 314  |  75% |
| agent_ops_api    | 1392  | 201  |  86% |
| agent_router_api | 2234  | 390  |  83% |
| analytics_mcp    | 735   | 305  |  59% |
| competencies_api | 3883  | 1191 |  69% |
| cv_api           | 6065  | 2051 |  66% |
| drive_api        | 2501  | 1065 |  57% |
| items_api        | 1602  | 453  |  72% |
| missions_api     | 1866  | 514  |  72% |
| monitoring_mcp   | 985   | 389  |  61% |
| platform-engineering | 1240  | 970  |  22% |
| prompts_api      | 1166  | 385  |  67% |
| tests            | 79    | 3    |  96% |
| users_api        | 1668  | 570  |  66% |

### Modifications depuis le dernier push

#### Commits non pushés
- Fix taxonomy prompt fallback warning

#### Fichiers (non commités)
- `agents/workflows/analyse-ui-ux.md` (M)
- `.gcloud/google-cloud-sdk/platform/gsutil/third_party/mock/docs/changelog.txt` (T)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/exception_handler.py` (M)
- `agent_commons/agent_commons/guardrails.py` (M)
- `agent_commons/agent_commons/mcp_proxy.py` (M)
- `agent_commons/agent_commons/runner.py` (M)
- `agent_commons/agent_commons/schemas.py` (M)
- `agent_commons/agent_commons/session.py` (M)
- `agent_commons/pyproject.toml` (M)
- `agent_commons/tests/test_mcp_proxy.py` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/agent_api.assistant_system_instruction.txt` (M)
- `agent_hr_api/agent_api.capabilities_instruction.txt` (M)
- `agent_hr_api/logger.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/requirements.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/test_jwt_propagation.py` (M)
- `agent_hr_api/test_main.py` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/agent.py` (M)
- `agent_missions_api/logger.py` (M)
- `agent_missions_api/main.py` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/agent_api.assistant_system_instruction.txt` (M)
- `agent_ops_api/agent_api.capabilities_instruction.txt` (M)
- `agent_ops_api/logger.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/requirements.txt` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/test_jwt_propagation.py` (M)
- `agent_ops_api/test_main.py` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/agent_api.assistant_system_instruction.txt` (M)
- `agent_router_api/agent_api.capabilities_instruction.txt` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/logger.py` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/requirements.txt` (M)
- `agent_router_api/router.py` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/test_a2a_resilience.py` (M)
- `analytics_mcp/logger.py` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/logger.py` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/competencies_router.py` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/cv_api.generate_taxonomy_tree_reduce.txt` (M)
- `cv_api/cv_api.generate_taxonomy_tree_sweep.txt` (M)
- `cv_api/logger.py` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/routers/profile_router.py` (M)
- `cv_api/src/cvs/routers/taxonomy_router.py` (M)
- `cv_api/src/services/taxonomy_service.py` (M)
- `cv_api/test_taxonomy_service.py` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/logger.py` (M)
- `drive_api/main.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/google_auth.py` (M)
- `drive_api/src/routers/ingestion_router.py` (M)
- `frontend/VERSION` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/Dockerfile` (M)
- `items_api/logger.py` (M)
- `items_api/main.py` (M)
- `items_api/mcp_server.py` (M)
- `items_api/spec.md` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/logger.py` (M)
- `missions_api/main.py` (M)
- `missions_api/mcp_server.py` (M)
- `missions_api/spec.md` (M)
- `monitoring_mcp/logger.py` (M)
- `monitoring_mcp/mcp_app.py` (M)
- `monitoring_mcp/spec.md` (M)
- `monitoring_mcp/tests/test_mcp_server.py` (M)
- `monitoring_mcp/tools/data_tools.py` (M)
- `platform-engineering/bundled_prompts/agent_hr_api/agent_api.assistant_system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_hr_api/agent_api.capabilities_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_ops_api/agent_api.assistant_system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_ops_api/agent_api.capabilities_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/agent_api.assistant_system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/agent_api.capabilities_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/agent_router_api.system_instruction.txt` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_monitoring.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/Dockerfile` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/logger.py` (M)
- `prompts_api/main.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/schemas.py` (M)
- `prompts_api/tests/test_prompts.py` (M)
- `sre_report.md` (M)
- `users_api/Dockerfile` (M)
- `users_api/logger.py` (M)
- `users_api/main.py` (M)
- `users_api/spec.md` (M)
- `users_api/src/mcp_tools/tools_registry.py` (M)
- `users_api/src/users/auth_router.py` (M)
- `agent_commons/agent_commons/guardrails_grounding.py` (??)
- `agent_hr_api/history_routes.py` (??)
- `agent_hr_api/test_create_agent_jwt.py` (??)
- `agent_hr_api/test_history_routes.py` (??)
- `agent_missions_api/test_create_agent_jwt.py` (??)
- `agent_ops_api/history_routes.py` (??)
- `agent_ops_api/test_create_agent_jwt.py` (??)
- `agent_router_api/a2a_tools.py` (??)
- `cv_api/get_status.py` (??)
- `debug_prd_prompt.py` (??)
- `frontend/src/components/agent/CompetencyBadge.vue` (??)
- `frontend/src/components/agent/CompetencyList.vue` (??)
- `frontend/src/components/agent/EvaluationCard.vue` (??)
- `frontend/src/components/agent/EvaluationTable.vue` (??)
- `frontend/src/components/agent/__tests__/CompetencyBadge.spec.ts` (??)
- `frontend/src/components/agent/__tests__/CompetencyList.spec.ts` (??)
- `frontend/src/components/agent/__tests__/EvaluationCard.spec.ts` (??)
- `frontend/src/components/agent/__tests__/EvaluationTable.spec.ts` (??)
- `query_logs.sh` (??)
- `scripts/analytics_mcp_proxy.py` (??)
- `scripts/mcp_cli.py` (??)
- `test_seed.py` (??)
- `tests/` (??)

---

## Mise à jour automatique - 2026-04-30 11:12:47

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1177  | 510  |  57% |
| agent_hr_api     | 1304  | 233  |  82% |
| agent_missions_api | 1098  | 353  |  68% |
| agent_ops_api    | 1274  | 198  |  84% |
| agent_router_api | 2191  | 379  |  83% |
| analytics_mcp    | 696   | 299  |  57% |
| competencies_api | 3844  | 1186 |  69% |
| cv_api           | 5921  | 1955 |  67% |
| drive_api        | 2460  | 1059 |  57% |
| items_api        | 1563  | 448  |  71% |
| missions_api     | 1827  | 509  |  72% |
| monitoring_mcp   | 824   | 462  |  44% |
| platform-engineering | 1240  | 970  |  22% |
| prompts_api      | 1105  | 390  |  65% |
| users_api        | 1628  | 564  |  65% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_commons/pyproject.toml` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/requirements.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/main.py` (M)
- `agent_missions_api/requirements.txt` (M)
- `agent_missions_api/test_guardrail.py` (M)
- `agent_missions_api/test_main.py` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/requirements.txt` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/requirements.txt` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/competencies_router.py` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/cv_api.generate_taxonomy_tree_deduplicate.txt` (M)
- `cv_api/cv_api.generate_taxonomy_tree_reduce.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/routers/taxonomy_router.py` (M)
- `cv_api/src/services/taxonomy_service.py` (M)
- `cv_api/test_taxonomy_router.py` (M)
- `drive_api/spec.md` (M)
- `frontend/VERSION` (M)
- `frontend/src/views/PromptsAdmin.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/bundled_prompts/agent_hr_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/agent_missions_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/agent_ops_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/requirements.txt` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `prompts_api/spec.md` (M)
- `users_api/spec.md` (M)
- `debug_test.py` (??)
- `pytest.ini` (??)

---

## Mise à jour automatique - 2026-04-30 08:22:18

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1177  | 510  |  57% |
| agent_hr_api     | 1302  | 233  |  82% |
| agent_missions_api | 1095  | 302  |  72% |
| agent_ops_api    | 1272  | 198  |  84% |
| agent_router_api | 2187  | 443  |  80% |
| analytics_mcp    | 696   | 299  |  57% |
| competencies_api | 3841  | 1183 |  69% |
| cv_api           | 5815  | 2054 |  65% |
| drive_api        | 2460  | 1059 |  57% |
| items_api        | 1563  | 448  |  71% |
| missions_api     | 1827  | 509  |  72% |
| monitoring_mcp   | 824   | 462  |  44% |
| platform-engineering | 1240  | 970  |  22% |
| prompts_api      | 1105  | 390  |  65% |
| users_api        | 1628  | 564  |  65% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `.agents/workflows/analyse-dette.md` (D)
- `.agents/workflows/analyse-security.md` (M)
- `.agents/workflows/analyse-ux-ui.md` (D)
- `.agents/workflows/bug.md` (M)
- `.agents/workflows/git-push.md` (M)
- `.agents/workflows/go-to-prod.md` (M)
- `.agents/workflows/sre-report.md` (M)
- `agent_hr_api/HASH` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/HASH` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/agent_missions_api.system_instruction.txt` (M)
- `agent_missions_api/main.py` (M)
- `agent_ops_api/HASH` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/HASH` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/agent_api.assistant_system_instruction.txt` (M)
- `agent_router_api/agent_api.capabilities_instruction.txt` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/mcp_client.py` (M)
- `agent_router_api/router.py` (M)
- `agent_router_api/semantic_cache.py` (M)
- `agent_router_api/spec.md` (M)
- `analytics_mcp/HASH` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_server.py` (M)
- `competencies_api/HASH` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/analytics_router.py` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/scoring_service.py` (M)
- `cv_api/HASH` (M)
- `cv_api/README.md` (M)
- `cv_api/VERSION` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/services/bulk_service.py` (M)
- `cv_api/src/services/config.py` (M)
- `cv_api/src/services/cv_import_service.py` (M)
- `cv_api/test_bulk_reanalyse.py` (M)
- `cv_api/test_main.py` (M)
- `cv_api/test_pubsub_handler.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/users/changelog.yaml` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/router.py` (M)
- `frontend/VERSION` (M)
- `frontend/src/views/MissionsList.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/HASH` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `items_api/src/items/crud_router.py` (M)
- `items_api/src/items/router.py` (M)
- `missions_api/HASH` (M)
- `missions_api/VERSION` (M)
- `missions_api/mcp_server.py` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/crud_router.py` (M)
- `missions_api/test_crud.py` (M)
- `monitoring_mcp/HASH` (M)
- `monitoring_mcp/VERSION` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/HASH` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/router.py` (M)
- `prompts_api/src/prompts/schemas.py` (M)
- `prompts_api/tests/test_prompts.py` (M)
- `todo.md` (M)
- `users_api/HASH` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)
- `competencies_api/src/competencies/scoring_pipeline.py` (??)
- `competencies_api/src/competencies/scoring_router.py` (??)
- `competencies_api/src/competencies/scoring_utils.py` (??)
- `competencies_api/test_competencies_crud.py` (??)
- `competencies_api/test_competencies_extra.py` (??)
- `competencies_api/test_scoring_utils.py` (??)
- `cv_api/src/cvs/router.py.bak` (??)
- `cv_api/src/cvs/router.py.orig` (??)
- `cv_api/src/cvs/routers/` (??)
- `cv_api/test_data_quality_service.py` (??)
- `cv_api/test_taxonomy_router.py` (??)
- `drive_api/src/routers/` (??)
- `drive_api/test_dlq_router.py` (??)
- `drive_api/test_folders.py` (??)
- `items_api/src/items/routers/` (??)

---

## Mise à jour automatique - 2026-04-30 00:17:55

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1177  | 510  |  57% |
| agent_hr_api     | 1302  | 233  |  82% |
| agent_missions_api | 1094  | 293  |  73% |
| agent_ops_api    | 1272  | 198  |  84% |
| agent_router_api | 2172  | 370  |  83% |
| analytics_mcp    | 685   | 289  |  58% |
| competencies_api | 3114  | 1343 |  57% |
| cv_api           | 5246  | 2229 |  58% |
| drive_api        | 1998  | 1230 |  38% |
| items_api        | 1477  | 422  |  71% |
| missions_api     | 1812  | 509  |  72% |
| monitoring_mcp   | 824   | 462  |  44% |
| platform-engineering | 1240  | 970  |  22% |
| prompts_api      | 1091  | 388  |  64% |
| users_api        | 1628  | 564  |  65% |

### Modifications depuis le dernier push

#### Commits non pushés
- 129 tests - CompetencyNode SystemHealthCard Types
- 101 tests unitaires frontend - MissionsList FinopsBadge AvailabilityCard
- Ajout tests ItemCard ConsultantCard PageHeader Toast
- Augmente couverture agentApi MissionCard Login
- Stores et composants 33 tests
- Augmentation couverture tests unitaires Vue
- Mise en place Vitest

#### Fichiers (non commités)
- `gent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/spec.md` (M)
- `cv_api/HASH` (M)
- `cv_api/VERSION` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/services/cv_import_service.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `drive_api/HASH` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/schemas.py` (M)
- `frontend/VERSION` (M)
- `frontend/src/components/DriveTreeGraph.vue` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/vitest.log` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `prompts_api/spec.md` (M)
- `users_api/spec.md` (M)

---

## Mise à jour automatique - 2026-04-29 23:12:14

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1115  | 539  |  52% |
| agent_hr_api     | 1302  | 233  |  82% |
| agent_missions_api | 1094  | 293  |  73% |
| agent_ops_api    | 1272  | 198  |  84% |
| agent_router_api | 2172  | 370  |  83% |
| analytics_mcp    | 685   | 289  |  58% |
| competencies_api | 3048  | 1406 |  54% |
| cv_api           | 5133  | 2377 |  54% |
| drive_api        | 1984  | 1221 |  38% |
| items_api        | 1477  | 422  |  71% |
| missions_api     | 1812  | 509  |  72% |
| monitoring_mcp   | 824   | 462  |  44% |
| platform-engineering | 1240  | 970  |  22% |
| prompts_api      | 1091  | 388  |  64% |
| users_api        | 1628  | 564  |  65% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `.agents/workflows/analyse-security.md` (M)
- `.agents/workflows/git-push.md` (M)
- `.agents/workflows/go-to-prod.md` (M)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/__init__.py` (M)
- `agent_commons/agent_commons/finops.py` (M)
- `agent_commons/agent_commons/schemas.py` (M)
- `agent_commons/agent_commons/session.py` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/conftest.py` (M)
- `agent_hr_api/logger.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/metadata.py` (M)
- `agent_hr_api/session.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/.dockerignore` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/agent.py` (M)
- `agent_missions_api/conftest.py` (M)
- `agent_missions_api/main.py` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/conftest.py` (M)
- `agent_ops_api/logger.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/metadata.py` (M)
- `agent_ops_api/session.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/conftest.py` (M)
- `agent_router_api/logger.py` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/semantic_cache.py` (M)
- `agent_router_api/session.py` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/test_main.py` (M)
- `agent_router_api/tests/conftest.py` (M)
- `agent_router_api/tests/test_jwt_propagation.py` (M)
- `agent_router_api/tests/test_semantic_cache.py` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/logger.py` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/mcp_server.py` (M)
- `bootstrap/.terraform.lock.hcl` (M)
- `bootstrap/services.tf` (M)
- `changelog.md` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/conftest.py` (M)
- `competencies_api/database.py` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `competencies_api/test_integration.py` (M)
- `competencies_api/test_scoring_weights.py` (M)
- `competencies_api/test_zero_trust.py` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/VERSION` (M)
- `cv_api/conftest.py` (M)
- `cv_api/cv_api.extract_cv_info.txt` (M)
- `cv_api/cv_api.generate_taxonomy_tree.txt` (D)
- `cv_api/database.py` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/auth.py` (M)
- `cv_api/src/cvs/models.py` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/schemas.py` (M)
- `cv_api/src/cvs/task_state.py` (M)
- `cv_api/test_jwt_propagation.py` (M)
- `cv_api/test_main.py` (M)
- `cv_api/test_mcp_tools.py` (M)
- `cv_api/test_pubsub_handler.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/cv/changelog.yaml` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `db_migrations/changelogs/prompts/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `drive_api/VERSION` (M)
- `drive_api/database.py` (M)
- `drive_api/mcp_server.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/auth.py` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/router.py` (M)
- `drive_api/src/schemas.py` (M)
- `drive_api/tests/test_dlq.py` (D)
- `drive_api/tests/test_drive_business.py` (D)
- `drive_api/tests/test_mcp_app.py` (D)
- `drive_api/tests/test_mcp_tools.py` (D)
- `drive_api/tests/test_router.py` (D)
- `frontend/VERSION` (M)
- `frontend/package-lock.json` (M)
- `frontend/package.json` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/components/CVImportMonitor.vue` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/router/index.ts` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/style.css` (M)
- `frontend/src/types/index.ts` (M)
- `frontend/src/views/Admin.vue` (M)
- `frontend/src/views/AdminDeduplication.vue` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/AdminUsers.vue` (M)
- `frontend/src/views/AiOps.vue` (M)
- `frontend/src/views/Competencies.vue` (M)
- `frontend/src/views/Help.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/ImportCV.vue` (M)
- `frontend/src/views/Login.vue` (M)
- `frontend/src/views/MissionDetail.vue` (M)
- `frontend/src/views/Profile.vue` (M)
- `frontend/src/views/UserDetail.vue` (M)
- `frontend/vite.config.ts` (M)
- `items_api/README.md` (M)
- `items_api/VERSION` (M)
- `items_api/database.py` (M)
- `items_api/mcp_server.py` (M)
- `items_api/spec.md` (M)
- `items_api/src/auth.py` (M)
- `items_api/src/items/router.py` (M)
- `items_api/test_integration.py` (M)
- `missions_api/VERSION` (M)
- `missions_api/conftest.py` (M)
- `missions_api/database.py` (M)
- `missions_api/requirements.txt` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/auth.py` (M)
- `missions_api/src/missions/cache.py` (M)
- `missions_api/src/missions/router.py` (M)
- `missions_api/src/missions/task_state.py` (M)
- `missions_api/test_jwt_propagation.py` (M)
- `missions_api/test_main.py` (D)
- `missions_api/test_security_upload.py` (M)
- `monitoring_mcp/Dockerfile` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/logger.py` (M)
- `monitoring_mcp/mcp_app.py` (M)
- `monitoring_mcp/mcp_server.py` (M)
- `platform-engineering/antigravity_sanity_error.md` (D)
- `platform-engineering/bundled_prompts/cv_api/cv_api.extract_cv_info.txt` (M)
- `platform-engineering/bundled_prompts/missions_api/cv_api.extract_cv_info.txt` (M)
- `platform-engineering/bundled_prompts/prompts_api/prompts_api.error_correction.txt` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/buckets.tf` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_monitoring.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `platform-engineering/terraform/redis.tf` (M)
- `platform-engineering/terraform/scheduler.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/conftest.py` (M)
- `prompts_api/database.py` (M)
- `prompts_api/main.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/analyzer.py` (M)
- `prompts_api/src/prompts/router.py` (M)
- `scripts/async_manage_env.sh` (M)
- `scripts/deploy.sh` (M)
- `scripts/generate_changelog.py` (M)
- `scripts/run_tests.sh` (M)
- `scripts/sync_prompts.py` (M)
- `seed_data.py` (M)
- `users_api/README.md` (M)
- `users_api/VERSION` (M)
- `users_api/database.py` (M)
- `users_api/mcp_server.py` (M)
- `users_api/spec.md` (M)
- `users_api/src/users/router.py` (M)
- `users_api/src/users/schemas.py` (M)
- `users_api/test_mcp_tools.py` (M)
- `.agents/workflows/analyse-ui-ux.md` (??)
- `.agents/workflows/sre-report.md` (??)
- `agent_commons/README.md` (??)
- `agent_commons/agent_commons/exception_handler.py` (??)
- `agent_commons/agent_commons/jwt_middleware.py` (??)
- `agent_hr_api/HASH` (??)
- `agent_hr_api/README.md` (??)
- `agent_missions_api/HASH` (??)
- `agent_missions_api/README.md` (??)
- `agent_ops_api/HASH` (??)
- `agent_ops_api/README.md` (??)
- `agent_router_api/HASH` (??)
- `agent_router_api/README.md` (??)
- `agent_router_api/router.py` (??)
- `agent_router_api/telemetry.py` (??)
- `agent_router_api/test_guardrail.py` (??)
- `agent_router_api/test_jwt_propagation.py` (??)
- `agent_router_api/tools_registry.py` (??)
- `analytics_mcp/HASH` (??)
- `analytics_mcp/README.md` (??)
- `analytics_mcp/init_pricing.py` (??)
- `audit_script.sh` (??)
- `check_db.py` (??)
- `clean_models.py` (??)
- `competencies_api/HASH` (??)
- `competencies_api/README.md` (??)
- `competencies_api/src/competencies/ai_scoring.py` (??)
- `competencies_api/src/competencies/analytics_router.py` (??)
- `competencies_api/src/competencies/assignments_router.py` (??)
- `competencies_api/src/competencies/bulk_task_state.py` (??)
- `competencies_api/src/competencies/competencies_router.py` (??)
- `competencies_api/src/competencies/evaluations_router.py` (??)
- `competencies_api/src/competencies/finops.py` (??)
- `competencies_api/src/competencies/helpers.py` (??)
- `competencies_api/src/competencies/scheduler_control.py` (??)
- `competencies_api/src/competencies/scoring_service.py` (??)
- `competencies_api/test_bulk_endpoints.py` (??)
- `cv_api/HASH` (??)
- `cv_api/README.md` (??)
- `cv_api/cv_api.generate_taxonomy_tree_deduplicate.txt` (??)
- `cv_api/cv_api.generate_taxonomy_tree_map.txt` (??)
- `cv_api/cv_api.generate_taxonomy_tree_reduce.txt` (??)
- `cv_api/cv_api.generate_taxonomy_tree_sweep.txt` (??)
- `cv_api/scratch.py` (??)
- `cv_api/src/cvs/bulk_task_state.py` (??)
- `cv_api/src/services/` (??)
- `cv_api/test_bulk_reanalyse.py` (??)
- `docs/pipelines.md` (??)
- `drive_api/HASH` (??)
- `drive_api/README.md` (??)
- `drive_api/query_db.py` (??)
- `drive_api/test_mcp_tools.py` (??)
- `error.log` (??)
- `failed_tests.txt` (??)
- `frontend/HASH` (??)
- `frontend/README.md` (??)
- `frontend/src/components/DriveTreeGraph.vue` (??)
- `frontend/src/components/__tests__/` (??)
- `frontend/src/views/AdminBulkImport.vue` (??)
- `frontend/src/views/DataQuality.vue` (??)
- `frontend/vitest.log` (??)
- `items_api/HASH` (??)
- `items_api/src/items/admin_router.py` (??)
- `items_api/src/items/crud_router.py` (??)
- `items_api/test_delete_user_items.py` (??)
- `missions_api/HASH` (??)
- `missions_api/README.md` (??)
- `missions_api/src/missions/analysis_router.py` (??)
- `missions_api/src/missions/analysis_service.py` (??)
- `missions_api/src/missions/crud_router.py` (??)
- `missions_api/src/missions/document_extractor.py` (??)
- `missions_api/src/missions/helpers.py` (??)
- `missions_api/src/missions/user_router.py` (??)
- `missions_api/test_analysis.py` (??)
- `missions_api/test_crud.py` (??)
- `monitoring_mcp/HASH` (??)
- `monitoring_mcp/README.md` (??)
- `monitoring_mcp/context.py` (??)
- `monitoring_mcp/tools/` (??)
- `parse_report.py` (??)
- `prompts_api/HASH` (??)
- `prompts_api/README.md` (??)
- `read_gcs.py` (??)
- `read_prompt.py` (??)
- `run_test.py` (??)
- `run_test_debug.py` (??)
- `run_tests.sh` (??)
- `scratch.py` (??)
- `scripts/generate_pipeline_docs.py` (??)
- `split_tests.py` (??)
- `sre_report.md` (??)
- `sre_report_runner.py` (??)
- `test_batch.jsonl` (??)
- `test_hash.sh` (??)
- `test_out.txt` (??)
- `test_out2.txt` (??)
- `test_output.txt` (??)
- `users_api/HASH` (??)
- `users_api/src/mcp_tools/` (??)
- `users_api/src/users/auth_router.py` (??)
- `users_api/src/users/crud_router.py` (??)
- `users_api/src/users/system_router.py` (??)

---

## Mise à jour automatique - 2026-04-24 15:27:16

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_commons    | 1000  | 431  |  57% |
| agent_hr_api     | 1329  | 250  |  81% |
| agent_missions_api | 1134  | 312  |  72% |
| agent_ops_api    | 1318  | 222  |  83% |
| agent_router_api | 2039  | 381  |  81% |
| analytics_mcp    | 646   | 249  |  61% |
| competencies_api | 2179  | 857  |  61% |
| cv_api           | 2890  | 954  |  67% |
| drive_api        | 2135  | 659  |  69% |
| items_api        | 1353  | 413  |  69% |
| missions_api     | 1664  | 458  |  72% |
| monitoring_mcp   | 868   | 530  |  39% |
| platform-engineering | 1194  | 924  |  23% |
| prompts_api      | 1073  | 376  |  65% |
| users_api        | 1574  | 551  |  65% |

### Modifications depuis le dernier push

#### Commits non pushés
- Fix logic & tests, update platform versions
- Release prd analytics_mcp and fixes

#### Fichiers (non commités)
- `cripts/generate_changelog.py` (M)

---

## Mise à jour automatique - 2026-04-24 15:26:41

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 2179  | 857  |  61% |
| cv_api           | 2890  | 954  |  67% |
| drive_api        | 2135  | 659  |  69% |
| items_api        | 1353  | 413  |  69% |
| prompts_api      | 1073  | 376  |  65% |
| users_api        | 1574  | 551  |  65% |

### Modifications depuis le dernier push

#### Commits non pushés
- Release prd analytics_mcp and fixes

#### Fichiers (non commités)
- `gent_hr_api/main.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/main.py` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/spec.md` (M)
- `analytics_mcp/mcp_app.py` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/database.py` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_app.py` (M)
- `competencies_api/spec.md` (M)
- `cv_api/VERSION` (M)
- `cv_api/database.py` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_app.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `drive_api/VERSION` (M)
- `drive_api/main.py` (M)
- `drive_api/mcp_app.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/router.py` (M)
- `drive_api/src/schemas.py` (M)
- `drive_api/tests/test_drive_business.py` (M)
- `frontend/VERSION` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/types/index.ts` (M)
- `frontend/src/views/Home.vue` (M)
- `items_api/VERSION` (M)
- `items_api/main.py` (M)
- `items_api/mcp_app.py` (M)
- `items_api/spec.md` (M)
- `items_api/src/items/router.py` (M)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/mcp_app.py` (M)
- `missions_api/spec.md` (M)
- `monitoring_mcp/mcp_app.py` (M)
- `platform-engineering/antigravity_sanity_error.md` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_monitoring.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/db_migrations_job.tf` (M)
- `platform-engineering/terraform/dns.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `platform-engineering/terraform/waf.tf` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/main.py` (M)
- `prompts_api/prompts_api.error_correction.txt` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/analyzer.py` (M)
- `prompts_api/src/prompts/router.py` (M)
- `scripts/agent_prompt_tests.py` (M)
- `scripts/generate_fake_agencies.py` (M)
- `scripts/generate_gcp_summit_data.py` (M)
- `users_api/VERSION` (M)
- `users_api/main.py` (M)
- `users_api/mcp_app.py` (M)
- `users_api/spec.md` (M)
- `users_api/src/users/router.py` (M)
- `frontend/src/components/agent/CloudRunLogsViewer.vue` (??)
- `frontend/src/components/agent/DebugPromptCard.vue` (??)
- `missions_api/test_mcp_tools.py` (??)
- `prompts_api/mcp_app.py` (??)
- `scripts/_insert_ui_format_tests.py` (??)

---

## Mise à jour automatique - 2026-04-24 08:02:12

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 2176  | 854  |  61% |
| cv_api           | 2861  | 927  |  68% |
| drive_api        | 2084  | 663  |  68% |
| items_api        | 1331  | 391  |  71% |
| prompts_api      | 998   | 301  |  70% |
| users_api        | 1553  | 532  |  66% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/spec.md` (M)
- `cv_api/spec.md` (M)
- `drive_api/spec.md` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/bundled_prompts/agent_router_api/agent_router_api.system_instruction.txt` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `prompts_api/spec.md` (M)
- `users_api/spec.md` (M)
- `platform-engineering/test.py` (??)

---

## Mise à jour automatique - 2026-04-23 20:22:45

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 2176  | 854  |  61% |
| cv_api           | 2861  | 927  |  68% |
| drive_api        | 2084  | 663  |  68% |
| items_api        | 1331  | 391  |  71% |
| prompts_api      | 998   | 301  |  70% |
| users_api        | 1553  | 532  |  66% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `.agents/workflows/analyse-prompt.md` (M)
- `.agents/workflows/analyse-security.md` (M)
- `.agents/workflows/bug.md` (M)
- `.agents/workflows/go-to-prod.md` (M)
- `.antigravity_env` (M)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/finops.py` (M)
- `agent_commons/agent_commons/mcp_client.py` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/mcp_client.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/test_zero_trust.py` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/agent.py` (M)
- `agent_missions_api/conftest.py` (M)
- `agent_missions_api/test_zero_trust.py` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/mcp_client.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/test_guardrail.py` (M)
- `agent_ops_api/test_zero_trust.py` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/mcp_client.py` (M)
- `agent_router_api/test_zero_trust.py` (M)
- `bootstrap/bigquery.tf` (M)
- `changelog.md` (M)
- `cloudbuild_tmp.yaml` (D)
- `competencies_api/VERSION` (M)
- `competencies_api/main.py` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/test_zero_trust.py` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/VERSION` (M)
- `cv_api/main.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/test_jwt_propagation.py` (M)
- `cv_api/test_zero_trust.py` (M)
- `data_ingestion/france_travail_ingestion.py` (M)
- `db_init/VERSION` (M)
- `docker-compose.yml` (M)
- `docs/adr/0002-model-context-protocol-mcp.md` (M)
- `docs/adr/0012-architecture-multi-agent-a2a.md` (M)
- `drive_api/VERSION` (M)
- `drive_api/conftest.py` (M)
- `drive_api/main.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/auth.py` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/google_auth.py` (M)
- `drive_api/src/router.py` (M)
- `drive_api/test_zero_trust.py` (M)
- `drive_api/tests/test_drive_business.py` (M)
- `frontend/VERSION` (M)
- `frontend/nginx/default.conf` (M)
- `frontend/src/components/agent/SystemHealthCard.vue` (M)
- `frontend/src/views/AiOps.vue` (M)
- `frontend/src/views/FinopsAdmin.vue` (M)
- `frontend/src/views/InfraMap.vue` (M)
- `frontend/src/views/Registry.vue` (M)
- `frontend/src/views/Specs.vue` (M)
- `frontend/vite.config.ts` (M)
- `items_api/VERSION` (M)
- `items_api/main.py` (M)
- `items_api/spec.md` (M)
- `items_api/test_zero_trust.py` (M)
- `market_mcp/.dockerignore` (D)
- `market_mcp/Dockerfile` (D)
- `market_mcp/VERSION` (D)
- `market_mcp/auth.py` (D)
- `market_mcp/conftest.py` (D)
- `market_mcp/logger.py` (D)
- `market_mcp/mcp_app.py` (D)
- `market_mcp/mcp_server.py` (D)
- `market_mcp/requirements.txt` (D)
- `market_mcp/spec.md` (D)
- `market_mcp/test_main.py` (D)
- `market_mcp/test_zero_trust.py` (D)
- `market_mcp/tests/test_jwt_user_email.py` (D)
- `market_mcp/tests/test_mcp_server.py` (D)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/router.py` (M)
- `missions_api/test_jwt_propagation.py` (M)
- `missions_api/test_main.py` (M)
- `missions_api/test_zero_trust.py` (M)
- `monitoring_mcp/Dockerfile` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/mcp_server.py` (M)
- `monitoring_mcp/test_zero_trust.py` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_market.tf` (D)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/lb-internal.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/scheduler.tf` (M)
- `platform-engineering/terraform/scratch_check_env.py` (M)
- `platform-engineering/terraform/scratch_check_tf_env.py` (M)
- `platform-engineering/terraform/scratch_gen.py` (M)
- `platform-engineering/terraform/scratch_unroll.py` (M)
- `platform-engineering/terraform/slo.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `platform-engineering/tests/test_manage_env.py` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/main.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/test_zero_trust.py` (M)
- `scripts/agent_prompt_tests.py` (M)
- `scripts/async_manage_env.sh` (M)
- `scripts/deploy.sh` (M)
- `scripts/generate_fake_agencies.py` (M)
- `scripts/generate_fake_missions.py` (M)
- `scripts/generate_gcp_summit_data.py` (M)
- `scripts/sync_prompts.py` (M)
- `todo.md` (M)
- `users_api/VERSION` (M)
- `users_api/main.py` (M)
- `users_api/mcp_server.py` (M)
- `users_api/spec.md` (M)
- `users_api/test_zero_trust.py` (M)
- `.agents/workflows/analyse-dette.md` (??)
- `.agents/workflows/post-mortem.md` (??)
- `agent_missions_api/test_jwt_propagation.py` (??)
- `analytics_mcp/` (??)
- `docs/looker_studio_setup.md` (??)
- `drive_api/tests/test_mcp_tools.py` (??)
- `platform-engineering/antigravity_sanity_error.md` (??)
- `platform-engineering/terraform/cr_analytics.tf` (??)
- `prompts_api/test_mcp_tools.py` (??)
- `scripts/logger_config.py` (??)

---

## Mise à jour automatique - 2026-04-23 15:43:56

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 2173  | 849  |  61% |
| cv_api           | 2855  | 924  |  68% |
| drive_api        | 1922  | 720  |  63% |
| items_api        | 1328  | 386  |  71% |
| prompts_api      | 959   | 371  |  61% |
| users_api        | 1546  | 523  |  66% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/analyse-prompt.md` (M)
- `.antigravity_env` (M)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/__init__.py` (M)
- `agent_commons/agent_commons/guardrails.py` (M)
- `agent_commons/tests/test_guardrails.py` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/agent.py` (M)
- `agent_missions_api/agent_missions_api.system_instruction.txt` (M)
- `agent_missions_api/main.py` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/database.py` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/models.py` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `competencies_api/test_integration.py` (M)
- `cv_api/VERSION` (M)
- `cv_api/cv_api.extract_cv_info.txt` (M)
- `cv_api/cv_api.generate_taxonomy_tree.txt` (M)
- `cv_api/database.py` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/schemas.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/competencies/changelog.yaml` (M)
- `drive_api/VERSION` (M)
- `drive_api/main.py` (M)
- `drive_api/mcp_server.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/router.py` (M)
- `frontend/VERSION` (M)
- `frontend/src/components/AdminUserManagement.vue` (D)
- `frontend/src/components/CompetencyEvaluationPanel.vue` (M)
- `frontend/src/components/TaxonomySuggestions.vue` (M)
- `frontend/src/components/agent/FinopsBadge.vue` (M)
- `frontend/src/components/ui/ToastNotification.vue` (M)
- `frontend/src/views/Competencies.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/UserDetail.vue` (M)
- `frontend/src/views/UserProfile.vue` (D)
- `items_api/VERSION` (M)
- `items_api/database.py` (M)
- `items_api/main.py` (M)
- `items_api/mcp_server.py` (M)
- `items_api/spec.md` (M)
- `items_api/src/items/router.py` (M)
- `items_api/src/items/schemas.py` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/mcp_server.py` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/router.py` (M)
- `missions_api/staffing_heuristics.txt` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/mcp_app.py` (M)
- `monitoring_mcp/mcp_server.py` (M)
- `monitoring_mcp/tests/test_mcp_server.py` (M)
- `platform-engineering/bundled_prompts/agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_missions_api/agent_missions_api.system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/agent_router_api.system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/cv_api/cv_api.extract_cv_info.txt` (M)
- `platform-engineering/bundled_prompts/cv_api/cv_api.generate_taxonomy_tree.txt` (M)
- `platform-engineering/bundled_prompts/missions_api/staffing_heuristics.txt` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_monitoring.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/mcp_server.py` (M)
- `prompts_api/spec.md` (M)
- `scripts/agent_prompt_tests.py` (M)
- `scripts/generate_fake_agencies.py` (M)
- `scripts/sync_prompts.py` (M)
- `users_api/VERSION` (M)
- `users_api/main.py` (M)
- `users_api/mcp_server.py` (M)
- `users_api/spec.md` (M)
- `.agents/workflows/generate-gcp-summit-fake.md` (??)
- `.dockerignore` (??)
- `cloudbuild_tmp.yaml` (??)
- `competencies_api/test_scoring_weights.py` (??)
- `db_migrations/changelogs/competencies/006-add-scoring-metadata.yaml` (??)
- `db_migrations/changelogs/competencies/007-fix-context-column-text.yaml` (??)
- `scripts/generate_fake_missions.py` (??)
- `scripts/generate_gcp_summit_data.py` (??)

---

## Mise à jour automatique - 2026-04-23 10:27:50

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1866  | 749  |  60% |
| cv_api           | 2761  | 847  |  69% |
| drive_api        | 1878  | 688  |  63% |
| items_api        | 1264  | 334  |  74% |
| prompts_api      | 956   | 368  |  62% |
| users_api        | 1517  | 501  |  67% |

### Modifications depuis le dernier push

#### Commits non pushés
- Fix PubSub DLQ DeadlineExceeded timeout exception
- Nettoyage fichiers inutiles et logs

#### Fichiers (non commités)
- `gent_commons/agent_commons.egg-info/SOURCES.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/competencies_test.db` (M)
- `competencies_api/spec.md` (M)
- `cv_api/spec.md` (M)
- `drive_api/drive_business_test.db` (M)
- `drive_api/requirements.txt` (M)
- `drive_api/spec.md` (M)
- `items_api/items_test.db` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `prompts_api/prompts_test.db` (M)
- `prompts_api/spec.md` (M)
- `users_api/spec.md` (M)
- `users_api/users_test.db` (M)

---

## Mise à jour automatique - 2026-04-23 08:50:34

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1866  | 749  |  60% |
| cv_api           | 2761  | 847  |  69% |
| drive_api        | 1857  | 667  |  64% |
| items_api        | 1264  | 334  |  74% |
| prompts_api      | 956   | 368  |  62% |
| users_api        | 1517  | 500  |  67% |

### Modifications depuis le dernier push

#### Commits non pushés
- Fix ModuleNotFoundError: removed forbidden agent_commons import in missions_api

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/metadata.py` (M)
- `agent_commons/agent_commons/runner.py` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/test_jwt_propagation.py` (M)
- `agent_hr_api/test_main.py` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/agent.py` (M)
- `agent_missions_api/main.py` (M)
- `agent_missions_api/metadata.py` (M)
- `agent_missions_api/spec.md` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/test_jwt_propagation.py` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/semantic_cache.py` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/tests/test_jwt_propagation.py` (M)
- `bootstrap/platform_engineering.tf` (M)
- `bootstrap/providers.tf` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/competencies_test.db` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_app.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/test_mcp_tools.py` (M)
- `cv_api/VERSION` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_app.py` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/test_pubsub_handler.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `drive_api/VERSION` (M)
- `drive_api/conftest.py` (M)
- `drive_api/drive_business_test.db` (M)
- `drive_api/main.py` (M)
- `drive_api/mcp_app.py` (M)
- `drive_api/requirements.txt` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/router.py` (M)
- `frontend/VERSION` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/components/CVImportMonitor.vue` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/views/Admin.vue` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/InfraMap.vue` (M)
- `frontend/src/views/PromptsAdmin.vue` (M)
- `frontend/src/views/Registry.vue` (M)
- `frontend/src/views/Specs.vue` (M)
- `items_api/VERSION` (M)
- `items_api/items_test.db` (M)
- `items_api/main.py` (M)
- `items_api/mcp_app.py` (M)
- `items_api/mcp_server.py` (M)
- `items_api/requirements.txt` (M)
- `items_api/spec.md` (M)
- `items_api/src/items/router.py` (M)
- `items_api/test_mcp_tools.py` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/requirements.txt` (M)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/mcp_app.py` (M)
- `missions_api/requirements.txt` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/cache.py` (M)
- `missions_api/src/missions/router.py` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/mcp_app.py` (M)
- `monitoring_mcp/mcp_server.py` (M)
- `monitoring_mcp/requirements.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/cv_api/cv_api.extract_cv_info.txt` (M)
- `platform-engineering/bundled_prompts/cv_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/missions_api/requirements.txt` (M)
- `platform-engineering/bundled_prompts/prompts_api/requirements.txt` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/.terraform.lock.hcl` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/buckets.tf` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_monitoring.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/db_init_job.tf` (M)
- `platform-engineering/terraform/db_migrations_job.tf` (M)
- `platform-engineering/terraform/dns.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/outputs.tf` (M)
- `platform-engineering/terraform/providers.tf` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `platform-engineering/terraform/waf.tf` (M)
- `platform-engineering/tests/test_manage_env.py` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/main.py` (M)
- `prompts_api/prompts_test.db` (M)
- `prompts_api/requirements.txt` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/router.py` (M)
- `scripts/agent_prompt_tests.py` (M)
- `scripts/async_manage_env.sh` (M)
- `scripts/deploy.sh` (M)
- `scripts/generate_fake_agencies.py` (M)
- `todo.md` (M)
- `users_api/VERSION` (M)
- `users_api/main.py` (M)
- `users_api/mcp_app.py` (M)
- `users_api/mcp_server.py` (M)
- `users_api/requirements.txt` (M)
- `users_api/spec.md` (M)
- `users_api/src/users/router.py` (M)
- `users_api/test_mcp_tools.py` (M)
- `users_api/users_test.db` (M)
- `.agents/workflows/analyse-ux-ui.md` (??)
- `agent_hr_api/debug_jwt.py` (??)
- `db_init/` (??)
- `docs/adr/0014-pipeline-import-cv-drive-statuts-et-controles.md` (??)
- `drive_api/tests/test_dlq.py` (??)
- `find_silent_errors.py` (??)
- `fix_agents.py` (??)
- `fix_exception_handler.py` (??)
- `frontend/src/components/CVReanalysisPanel.vue` (??)
- `inject_error_handlers.py` (??)
- `refactor_failfast.py` (??)
- `refactor_mcp_returns.py` (??)
- `refactor_orphan_logs.py` (??)
- `scripts/force_requeue_processing.sh` (??)
- `silent_errors_report.txt` (??)

---

## Mise à jour automatique - 2026-04-22 09:04:09

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1793  | 698  |  61% |
| cv_api           | 2661  | 767  |  71% |
| drive_api        | 1462  | 549  |  62% |
| items_api        | 1206  | 292  |  76% |
| prompts_api      | 895   | 315  |  65% |
| users_api        | 1454  | 453  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Fix ModuleNotFoundError: removed forbidden agent_commons import in cv_api
- Add HTTP error logging to silent drive_api PATCH requests
- Fix push endpoint domain: remove api. prefix
- Fix OIDC audience mismatch after LB path rewrite
- Fix LB routes for Pub/Sub push endpoints
- Revert pubsub import map (ephemeral resources)
- Add Pub/Sub resources to manage_env import map

#### Fichiers (non commités)
- `gent_commons/agent_commons/__init__.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/competencies_test.db` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/models.py` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `cv_api/spec.md` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/competencies/changelog.yaml` (M)
- `drive_api/VERSION` (M)
- `drive_api/drive_business_test.db` (M)
- `drive_api/spec.md` (M)
- `frontend/VERSION` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/views/Admin.vue` (M)
- `frontend/src/views/AdminAvailability.vue` (M)
- `frontend/src/views/AdminDeduplication.vue` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/AdminUsers.vue` (M)
- `frontend/src/views/FinopsAdmin.vue` (M)
- `frontend/src/views/PromptsAdmin.vue` (M)
- `items_api/VERSION` (M)
- `items_api/items_test.db` (M)
- `items_api/spec.md` (M)
- `analytics_mcp/VERSION` (M)
- `missions_api/VERSION` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/router.py` (M)
- `monitoring_mcp/VERSION` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/prompts_test.db` (M)
- `prompts_api/spec.md` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)
- `users_api/users_test.db` (M)
- `agent_commons/agent_commons/taxonomy_utils.py` (??)
- `check_db.py` (??)
- `db_migrations/changelogs/competencies/005-add-competency-suggestions.yaml` (??)
- `fetch_logs.py` (??)
- `frontend/src/components/TaxonomySuggestions.vue` (??)
- `frontend/src/components/ui/PageHeader.vue` (??)

---

## Mise à jour automatique - 2026-04-22 08:02:28

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1667  | 620  |  63% |
| cv_api           | 2657  | 766  |  71% |
| drive_api        | 1462  | 549  |  62% |
| items_api        | 1206  | 292  |  76% |
| prompts_api      | 895   | 315  |  65% |
| users_api        | 1454  | 453  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- fix: exclure les DBs de test du tracking git
- chore: bootstrap IAM cross-project et déploiement prd

#### Fichiers (non commités)
- `gent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/competencies_test.db` (M)
- `competencies_api/spec.md` (M)
- `cv_api/VERSION` (M)
- `cv_api/spec.md` (M)
- `drive_api/VERSION` (M)
- `drive_api/drive_business_test.db` (M)
- `drive_api/spec.md` (M)
- `frontend/VERSION` (M)
- `frontend/src/components/CVImportMonitor.vue` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/views/Admin.vue` (M)
- `items_api/items_test.db` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `prompts_api/prompts_test.db` (M)
- `prompts_api/spec.md` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)
- `users_api/src/users/router.py` (M)
- `users_api/users_test.db` (M)

---

## Mise à jour automatique - 2026-04-22 07:44:32

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1667  | 620  |  63% |
| cv_api           | 2657  | 766  |  71% |
| drive_api        | 1462  | 549  |  62% |
| items_api        | 1206  | 292  |  76% |
| prompts_api      | 895   | 315  |  65% |
| users_api        | 1453  | 452  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `ootstrap/main.tf` (M)
- `bootstrap/services.tf` (M)
- `bootstrap/variables.tf` (M)
- `competencies_api/spec.md` (M)
- `cv_api/VERSION` (M)
- `cv_api/cv_api.extract_cv_info.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/test_pubsub_handler.py` (M)
- `drive_api/VERSION` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/google_auth.py` (M)
- `drive_api/src/router.py` (M)
- `items_api/spec.md` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_server.py` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/mcp_server.py` (M)
- `users_api/VERSION` (M)
- `users_api/src/users/pubsub.py` (M)
- `competencies_api/competencies_test.db` (??)
- `drive_api/drive_business_test.db` (??)
- `items_api/items_test.db` (??)
- `prompts_api/prompts_test.db` (??)
- `scripts/force_flush_queued.sh` (??)
- `users_api/users_test.db` (??)

---

## Mise à jour automatique - 2026-04-22 07:03:15

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1667  | 620  |  63% |
| cv_api           | 2613  | 755  |  71% |
| drive_api        | 1434  | 524  |  63% |
| items_api        | 1206  | 292  |  76% |
| prompts_api      | 895   | 315  |  65% |
| users_api        | 1440  | 448  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- perf(drive): parallelize batch ingestion
- feat(ui): display raw JSON response in logs
- feat(cv): trigger drive full resync on reanalyze
- feat(ui): display fast JSON response in logs
- fix(cv): case-insensitive tag search

#### Fichiers (non commités)
- `agents/workflows/analyse-code-api.md` (M)
- `AGENTS.md` (M)
- `agent_commons/agent_commons/mcp_client.py` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/VERSION` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/spec.md` (M)
- `changelog.md` (M)
- `competencies_api/.coverage` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `cv_api/.coverage` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/VERSION` (M)
- `cv_api/__pycache__/main.cpython-313.pyc` (M)
- `cv_api/__pycache__/mcp_server.cpython-313.pyc` (M)
- `cv_api/__pycache__/test_main.cpython-313-pytest-9.0.2.pyc` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/test_main.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `db_migrations/changelogs/items/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/VERSION` (M)
- `drive_api/main.py` (M)
- `drive_api/requirements.txt` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/router.py` (M)
- `drive_api/src/schemas.py` (M)
- `drive_api/test.db` (M)
- `drive_api/test_zero_trust.py` (M)
- `drive_api/tests/test_drive_business.py` (M)
- `frontend/VERSION` (M)
- `frontend/src/components/CompetencyEvaluationPanel.vue` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/components/agent/CandidateProfileCard.vue` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/views/Admin.vue` (M)
- `frontend/src/views/AdminUsers.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/PromptsAdmin.vue` (M)
- `frontend/src/views/UserProfile.vue` (M)
- `items_api/VERSION` (M)
- `items_api/main.py` (M)
- `items_api/spec.md` (M)
- `items_api/src/items/models.py` (M)
- `items_api/src/items/router.py` (M)
- `items_api/test_integration.py` (M)
- `analytics_mcp/VERSION` (M)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/spec.md` (M)
- `monitoring_mcp/VERSION` (M)
- `monitoring_mcp/mcp_server.py` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/cloudrun.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_monitoring.tf` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `platform-engineering/terraform/scheduler.tf` (M)
- `prompts_api/.coverage` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/main.py` (M)
- `prompts_api/mcp_server.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/prompts/__pycache__/analyzer.cpython-313.pyc` (M)
- `prompts_api/src/prompts/__pycache__/router.cpython-313.pyc` (M)
- `prompts_api/src/prompts/__pycache__/schemas.cpython-313.pyc` (M)
- `prompts_api/src/prompts/analyzer.py` (M)
- `prompts_api/src/prompts/router.py` (M)
- `prompts_api/src/prompts/schemas.py` (M)
- `scripts/agent_prompt_tests.py` (M)
- `scripts/async_manage_env.sh` (M)
- `seed_data.py` (M)
- `users_api/VERSION` (M)
- `users_api/main.py` (M)
- `users_api/spec.md` (M)
- `.gcloud_config/logs/2026.04.21/` (??)
- `cv_api/cv_database.db` (??)
- `cv_api/test_pubsub_handler.py` (??)
- `drive_api/drive_database.db` (??)
- `platform-engineering/bundled_prompts/prompts_api/` (??)
- `prompts_api/prompts_api.error_correction.txt` (??)
- `vtmp/` (??)

---

## Mise à jour automatique - 2026-04-21 12:05:22

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1494  | 488  |  67% |
| cv_api           | 2542  | 762  |  70% |
| drive_api        | 1341  | 464  |  65% |
| items_api        | 1153  | 265  |  77% |
| prompts_api      | 832   | 266  |  68% |
| users_api        | 1421  | 435  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- feat(ui): display raw JSON response in logs
- feat(cv): trigger drive full resync on reanalyze
- feat(ui): display fast JSON response in logs
- fix(cv): case-insensitive tag search

#### Fichiers (non commités)
- `gent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/spec.md` (M)
- `cv_api/VERSION` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/test.db` (M)
- `frontend/src/views/AdminUsers.vue` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `prompts_api/spec.md` (M)
- `users_api/spec.md` (M)

---

## Mise à jour automatique - 2026-04-21 11:55:48

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1494  | 488  |  67% |
| cv_api           | 2542  | 762  |  70% |
| drive_api        | 1325  | 448  |  66% |
| items_api        | 1153  | 265  |  77% |
| prompts_api      | 832   | 266  |  68% |
| users_api        | 1421  | 435  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- feat(ui): display fast JSON response in logs
- fix(cv): case-insensitive tag search

#### Fichiers (non commités)
- `gent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/spec.md` (M)
- `cv_api/.coverage` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/router.py` (M)
- `drive_api/test.db` (M)
- `frontend/VERSION` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `prompts_api/spec.md` (M)
- `users_api/spec.md` (M)

---

## Mise à jour automatique - 2026-04-21 11:48:18

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1494  | 488  |  67% |
| cv_api           | 2530  | 755  |  70% |
| drive_api        | 1316  | 441  |  66% |
| items_api        | 1153  | 265  |  77% |
| prompts_api      | 832   | 266  |  68% |
| users_api        | 1421  | 435  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/go-to-prod.md` (M)
- `agent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `bootstrap/platform_engineering.tf` (M)
- `bootstrap/variables.tf` (M)
- `competencies_api/spec.md` (M)
- `cv_api/.coverage` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/test.db` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/views/AdminUsers.vue` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/terraform/dns.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/spec.md` (M)
- `scripts/destroy_old_cr.sh` (D)
- `users_api/spec.md` (M)
- `cv_api/query_tags.py` (??)
- `scripts/generate_fake_agencies.py` (??)
- `scripts/requirements.txt` (??)

---

## Mise à jour automatique - 2026-04-21 00:13:09

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1494  | 488  |  67% |
| cv_api           | 2516  | 741  |  71% |
| drive_api        | 1309  | 435  |  67% |
| items_api        | 1153  | 265  |  77% |
| prompts_api      | 832   | 266  |  68% |
| users_api        | 1421  | 435  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `antigravity_env` (M)
- `AGENTS.md` (M)
- `agent_commons/VERSION` (M)
- `agent_commons/agent_commons/mcp_client.py` (M)
- `agent_commons/agent_commons/mcp_proxy.py` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/spec.md` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/semantic_cache.py` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/.coverage` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/models.py` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `competencies_api/test_mcp_tools.py` (M)
- `cv_api/.coverage` (M)
- `cv_api/VERSION` (M)
- `cv_api/__pycache__/test_main.cpython-313-pytest-9.0.2.pyc` (M)
- `cv_api/conftest.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/task_state.py` (M)
- `cv_api/test_main.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/competencies/changelog.yaml` (M)
- `db_migrations/changelogs/users/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `frontend/VERSION` (M)
- `frontend/nginx/default.conf` (M)
- `frontend/src/components/ConsultantProfile.vue` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/components/agent/ConsultantCard.vue` (M)
- `frontend/src/services/auth.ts` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/AgentsDocs.vue` (M)
- `frontend/src/views/Competencies.vue` (M)
- `frontend/src/views/Profile.vue` (M)
- `frontend/src/views/Specs.vue` (M)
- `frontend/src/views/UserDetail.vue` (M)
- `frontend/src/views/UserProfile.vue` (M)
- `frontend/vite.config.ts` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `items_api/src/items/router.py` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/mcp_server.py` (M)
- `analytics_mcp/tests/test_mcp_server.py` (M)
- `missions_api/VERSION` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/router.py` (M)
- `platform-engineering/bundled_prompts/agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `platform-engineering/bundled_prompts/agent_router_api/agent_router_api.system_instruction.txt` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/lb-internal.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `platform-engineering/tests/test_manage_env.py` (M)
- `prompts_api/.coverage` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/spec.md` (M)
- `scripts/async_manage_env.sh` (M)
- `scripts/deploy.sh` (M)
- `todo.md` (M)
- `users_api/Dockerfile` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)
- `users_api/src/users/models.py` (M)
- `users_api/src/users/router.py` (M)
- `.agents/workflows/auto-fix-network.md` (??)
- `.agents/workflows/go-to-prod.md` (??)
- `.tmp/` (??)
- `agent_hr_api/test_zero_trust.py` (??)
- `agent_missions_api/test_zero_trust.py` (??)
- `agent_ops_api/test_zero_trust.py` (??)
- `agent_router_api/test_zero_trust.py` (??)
- `competencies_api/test_zero_trust.py` (??)
- `cv_api/test_zero_trust.py` (??)
- `db_migrations/changelogs/competencies/004-add-competency-evaluations.yaml` (??)
- `drive_api/test_zero_trust.py` (??)
- `frontend/src/components/CompetencyEvaluationPanel.vue` (??)
- `frontend/src/components/StarRating.vue` (??)
- `items_api/test_zero_trust.py` (??)
- `analytics_mcp/spec.md` (??)
- `analytics_mcp/test_zero_trust.py` (??)
- `missions_api/test_zero_trust.py` (??)
- `monitoring_mcp/` (??)
- `platform-engineering/terraform/cr_monitoring.tf` (??)
- `prompts_api/test_zero_trust.py` (??)
- `reports/llm_analysis_all_20260420_192935.md` (??)
- `scratch_clean.py` (??)
- `users_api/test_zero_trust.py` (??)

---

## Mise à jour automatique - 2026-04-20 15:40:53

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1181  | 322  |  73% |
| cv_api           | 2337  | 585  |  75% |
| drive_api        | 1271  | 427  |  66% |
| items_api        | 1107  | 250  |  77% |
| prompts_api      | 794   | 258  |  68% |
| users_api        | 1368  | 432  |  68% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/git-push.md` (M)
- `AGENTS.md` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/spec.md` (M)
- `cv_api/.coverage` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/VERSION` (M)
- `cv_api/__pycache__/mcp_server.cpython-313.pyc` (M)
- `cv_api/__pycache__/test_main.cpython-313-pytest-9.0.2.pyc` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/__pycache__/schemas.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/schemas.py` (M)
- `cv_api/test_main.py` (M)
- `db_migrations/changelogs/drive/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/VERSION` (M)
- `drive_api/main.py` (M)
- `drive_api/mcp_server.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/router.py` (M)
- `drive_api/src/schemas.py` (M)
- `drive_api/test.db` (M)
- `drive_api/tests/test_drive_business.py` (M)
- `items_api/Dockerfile` (M)
- `items_api/spec.md` (M)
- `analytics_mcp/Dockerfile` (M)
- `analytics_mcp/auth.py` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `prompts_api/.coverage` (M)
- `prompts_api/Dockerfile` (M)
- `prompts_api/main.py` (M)
- `prompts_api/spec.md` (M)
- `users_api/Dockerfile` (M)
- `users_api/spec.md` (M)
- `agent_commons/VERSION` (??)
- `prompts_api/mcp_server.py` (??)

---

## Mise à jour automatique - 2026-04-20 13:55:06

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1181  | 322  |  73% |
| cv_api           | 1996  | 640  |  68% |
| drive_api        | 1050  | 371  |  65% |
| items_api        | 1107  | 250  |  77% |
| prompts_api      | 676   | 143  |  79% |
| users_api        | 1368  | 432  |  68% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/Dockerfile` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_hr_api/test_guardrail.py` (M)
- `agent_hr_api/test_main.py` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/agent.py` (M)
- `agent_missions_api/main.py` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_ops_api/test_guardrail.py` (M)
- `agent_ops_api/test_main.py` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/metrics.py` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/spec.md` (M)
- `cv_api/spec.md` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `frontend/src/components/agent/FinopsBadge.vue` (M)
- `frontend/src/components/ui/ToastNotification.vue` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/stores/uxStore.ts` (M)
- `frontend/src/types/index.ts` (M)
- `frontend/src/views/Home.vue` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `scripts/run_tests.sh` (M)
- `todo.md` (M)
- `users_api/spec.md` (M)
- `agent_commons/` (??)
- `agent_router_api/tests/test_health_agents.py` (??)

---

## Mise à jour automatique - 2026-04-20 12:49:17

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1181  | 322  |  73% |
| cv_api           | 1996  | 640  |  68% |
| drive_api        | 1050  | 371  |  65% |
| items_api        | 1107  | 250  |  77% |
| prompts_api      | 676   | 143  |  79% |
| users_api        | 1368  | 432  |  68% |

### Modifications depuis le dernier push

#### Commits non pushés
- Fix test regressions with fakeredis isolation

#### Fichiers (non commités)
- `gent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/.coverage` (M)
- `competencies_api/spec.md` (M)
- `cv_api/spec.md` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `users_api/spec.md` (M)

---

## Mise à jour automatique - 2026-04-20 12:37:10

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1182  | 757  |  36% |
| cv_api           | 1996  | 640  |  68% |
| drive_api        | 1050  | 371  |  65% |
| items_api        | 1105  | 656  |  41% |
| prompts_api      | 676   | 143  |  79% |
| users_api        | 1365  | 548  |  60% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/git-push.md` (M)
- `agent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/metrics.py` (M)
- `agent_router_api/requirements.txt` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/.coverage` (M)
- `competencies_api/spec.md` (M)
- `cv_api/spec.md` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `scripts/agent_prompt_tests.py` (M)
- `users_api/spec.md` (M)
- `agent_router_api/.venv_test/lib/python3.9/site-packages/async_timeout-5.0.1.dist-info/` (??)
- `agent_router_api/.venv_test/lib/python3.9/site-packages/async_timeout/` (??)
- `agent_router_api/.venv_test/lib/python3.9/site-packages/redis-7.0.1.dist-info/` (??)
- `agent_router_api/.venv_test/lib/python3.9/site-packages/redis/` (??)
- `agent_router_api/semantic_cache.py` (??)
- `agent_router_api/tests/conftest.py` (??)
- `agent_router_api/tests/test_semantic_cache.py` (??)
- `platform-engineering/pytest.ini` (??)
- `platform-engineering/tests/` (??)

---

## Mise à jour automatique - 2026-04-20 11:17:41

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1182  | 324  |  73% |
| cv_api           | 1996  | 640  |  68% |
| drive_api        | 1050  | 371  |  65% |
| items_api        | 1105  | 250  |  77% |
| prompts_api      | 676   | 143  |  79% |
| users_api        | 1365  | 434  |  68% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/VERSION` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/VERSION` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/spec.md` (M)
- `competencies_api/VERSION` (M)
- `cv_api/.coverage` (M)
- `cv_api/VERSION` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `db_migrations/VERSION` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `drive_api/tests/test_drive_business.py` (M)
- `drive_api/tests/test_router.py` (M)
- `frontend/VERSION` (M)
- `frontend/nginx/default.conf` (M)
- `frontend/src/components/agent/SystemHealthCard.vue` (M)
- `frontend/src/views/AdminUsers.vue` (M)
- `frontend/src/views/FinopsAdmin.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/InfraMap.vue` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_server.py` (M)
- `missions_api/VERSION` (M)
- `missions_api/spec.md` (M)
- `platform-engineering/bundled_prompts/agent_router_api/agent_router_api.system_instruction.txt` (M)
- `prompts_api/VERSION` (M)
- `roi.md` (M)
- `todo.md` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)
- `docs/adr/0013-choix-bdd-vectorielle-alloydb-vs-cloudsql.md` (??)
- `frontend/src/components/agent/ConsultantAvailabilityCard.vue` (??)
- `scratch_secret_fetch.py` (??)

---

## Mise à jour automatique - 2026-04-16 13:25:41

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1182  | 324  |  73% |
| cv_api           | 1989  | 636  |  68% |
| drive_api        | 1037  | 415  |  60% |
| items_api        | 1105  | 250  |  77% |
| prompts_api      | 676   | 143  |  79% |
| users_api        | 1365  | 434  |  68% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/analyse-prompt.md` (M)
- `.agents/workflows/git-push.md` (M)
- `.antigravity_env` (M)
- `agent_hr_api/.dockerignore` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_missions_api/Dockerfile` (M)
- `agent_missions_api/VERSION` (M)
- `agent_missions_api/__init__.py` (M)
- `agent_missions_api/main.py` (M)
- `agent_missions_api/test_main.py` (M)
- `agent_ops_api/.dockerignore` (M)
- `agent_ops_api/Dockerfile` (M)
- `agent_ops_api/VERSION` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/.dockerignore` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/metrics.py` (M)
- `agent_router_api/spec.md` (M)
- `agent_router_api/test_main.py` (M)
- `bootstrap/platform_engineering.tf` (M)
- `competencies_api/.coverage` (M)
- `competencies_api/.dockerignore` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/auth.py` (M)
- `competencies_api/test_integration.py` (M)
- `cv_api/.coverage` (M)
- `cv_api/.dockerignore` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/VERSION` (M)
- `cv_api/__pycache__/mcp_server.cpython-313.pyc` (M)
- `cv_api/__pycache__/test_main.cpython-313-pytest-9.0.2.pyc` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/__pycache__/auth.cpython-313.pyc` (M)
- `cv_api/src/auth.py` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/__pycache__/schemas.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/schemas.py` (M)
- `cv_api/test_main.py` (M)
- `db_migrations/changelogs/missions/changelog.yaml` (M)
- `drive_api/.dockerignore` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/router.py` (M)
- `drive_api/test.db` (M)
- `drive_api/tests/test_router.py` (M)
- `frontend/.dockerignore` (M)
- `frontend/VERSION` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/components/agent/MissionCard.vue` (M)
- `frontend/src/router/index.ts` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/views/Admin.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/ImportCV.vue` (M)
- `frontend/src/views/MissionDetail.vue` (M)
- `frontend/src/views/MissionsList.vue` (M)
- `items_api/.dockerignore` (M)
- `items_api/Dockerfile` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `analytics_mcp/.dockerignore` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_server.py` (M)
- `analytics_mcp/tests/test_mcp_server.py` (M)
- `missions_api/.dockerignore` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/VERSION` (M)
- `missions_api/mcp_server.py` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/missions/models.py` (M)
- `missions_api/src/missions/router.py` (M)
- `missions_api/src/missions/schemas.py` (M)
- `missions_api/test_main.py` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/cloudrun.tf` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_missions.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/database.tf` (M)
- `prompts_api/.coverage` (M)
- `prompts_api/.dockerignore` (M)
- `prompts_api/Dockerfile` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/src/prompts/__pycache__/router.cpython-313.pyc` (M)
- `prompts_api/src/prompts/router.py` (M)
- `scripts/agent_prompt_tests.py` (M)
- `scripts/async_manage_env.sh` (M)
- `scripts/deploy.sh` (M)
- `scripts/run_tests.sh` (M)
- `scripts/sync_prompts.py` (M)
- `todo.md` (M)
- `users_api/.dockerignore` (M)
- `users_api/Dockerfile` (M)
- `users_api/VERSION` (M)
- `users_api/mcp_server.py` (M)
- `users_api/spec.md` (M)
- `users_api/src/__pycache__/auth.cpython-313.pyc` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/users/router.py` (M)
- `PERSONAS.md` (??)
- `agent_hr_api/test_guardrail.py` (??)
- `agent_hr_api/test_jwt_propagation.py` (??)
- `agent_missions_api/test_guardrail.py` (??)
- `agent_ops_api/test_guardrail.py` (??)
- `agent_ops_api/test_jwt_propagation.py` (??)
- `agent_router_api/.venv_test/` (??)
- `agent_router_api/tests/` (??)
- `cv_api/test_jwt_propagation.py` (??)
- `docs/adr/0012-architecture-multi-agent-a2a.md` (??)
- `drive_api/tests/test_drive_business.py` (??)
- `frontend/src/components/CVImportMonitor.vue` (??)
- `analytics_mcp/tests/test_jwt_user_email.py` (??)
- `missions_api/test_jwt_propagation.py` (??)
- `missions_api/test_security_upload.py` (??)
- `platform-engineering/bundled_prompts/` (??)
- `reports/llm_analysis_all_20260416_092410.md` (??)
- `reports/llm_analysis_security_20260416_092941.md` (??)
- `reports/llm_analysis_security_20260416_093013.md` (??)
- `reports/llm_analysis_security_20260416_093105.md` (??)

---

## Mise à jour automatique - 2026-04-16 08:36:46

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1155  | 325  |  72% |
| cv_api           | 1730  | 592  |  66% |
| drive_api        | 872   | 391  |  55% |
| items_api        | 1105  | 250  |  77% |
| prompts_api      | 675   | 143  |  79% |
| users_api        | 1335  | 411  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- fix(agent): stabiliser tests unitaires et serialisation
- fix(agent-router): robustify mcp proxy and harmonize routing via /mcp/
- fix: resolve platform dev bugs (CV sync, MCP registry, AiOps 401) and prepare for redeployment

#### Fichiers (non commités)
- `gent_hr_api/spec.md` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/spec.md` (M)
- `bootstrap/platform_engineering.tf` (M)
- `competencies_api/spec.md` (M)
- `cv_api/spec.md` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `items_api/spec.md` (M)
- `missions_api/spec.md` (M)
- `scripts/async_manage_env.sh` (M)
- `users_api/spec.md` (M)

---

## Mise à jour automatique - 2026-04-15 23:38:06

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1155  | 325  |  72% |
| cv_api           | 1730  | 592  |  66% |
| drive_api        | 872   | 391  |  55% |
| items_api        | 1105  | 250  |  77% |
| prompts_api      | 675   | 143  |  79% |
| users_api        | 1335  | 411  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- fix(agent-router): robustify mcp proxy and harmonize routing via /mcp/
- fix: resolve platform dev bugs (CV sync, MCP registry, AiOps 401) and prepare for redeployment

#### Fichiers (non commités)
- `gitignore` (M)
- `AGENTS.md` (M)
- `agent_hr_api/Dockerfile` (M)
- `agent_hr_api/VERSION` (M)
- `agent_hr_api/agent.py` (M)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/conftest.py` (M)
- `agent_hr_api/main.py` (M)
- `agent_hr_api/mcp_client.py` (M)
- `agent_hr_api/spec.md` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `agent_ops_api/conftest.py` (M)
- `agent_ops_api/main.py` (M)
- `agent_ops_api/mcp_client.py` (M)
- `agent_ops_api/spec.md` (M)
- `agent_router_api/Dockerfile` (M)
- `agent_router_api/VERSION` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `agent_router_api/main.py` (M)
- `agent_router_api/mcp_client.py` (M)
- `agent_router_api/spec.md` (M)
- `bootstrap/platform_engineering.tf` (M)
- `competencies_api/.coverage` (M)
- `competencies_api/Dockerfile` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_server.py` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/auth.py` (M)
- `cv_api/.coverage` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/VERSION` (M)
- `cv_api/__pycache__/main.cpython-313.pyc` (M)
- `cv_api/__pycache__/mcp_server.cpython-313.pyc` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_server.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/__pycache__/auth.cpython-313.pyc` (M)
- `cv_api/src/auth.py` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/__pycache__/schemas.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/schemas.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/users/changelog.yaml` (M)
- `docker-compose.yml` (M)
- `drive_api/Dockerfile` (M)
- `drive_api/VERSION` (M)
- `drive_api/main.py` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/auth.py` (M)
- `drive_api/test.db` (M)
- `frontend/VERSION` (M)
- `frontend/nginx/default.conf` (M)
- `frontend/package-lock.json` (M)
- `frontend/package.json` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/components/agent/AgentExpertTerminal.vue` (M)
- `frontend/src/router/index.ts` (M)
- `frontend/src/services/auth.ts` (M)
- `frontend/src/stores/chatStore.ts` (M)
- `frontend/src/views/AdminAvailability.vue` (M)
- `frontend/src/views/AdminDeduplication.vue` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/AiOps.vue` (M)
- `frontend/src/views/Competencies.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/ImportCV.vue` (M)
- `frontend/src/views/MissionDetail.vue` (M)
- `frontend/src/views/MissionsList.vue` (M)
- `frontend/src/views/Profile.vue` (M)
- `frontend/src/views/PromptsAdmin.vue` (M)
- `frontend/src/views/Specs.vue` (M)
- `frontend/src/views/UserDetail.vue` (M)
- `frontend/src/views/UserProfile.vue` (M)
- `items_api/Dockerfile` (M)
- `items_api/VERSION` (M)
- `items_api/main.py` (M)
- `items_api/spec.md` (M)
- `items_api/src/auth.py` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/mcp_server.py` (M)
- `analytics_mcp/requirements.txt` (M)
- `analytics_mcp/tests/test_mcp_server.py` (M)
- `missions_api/Dockerfile` (M)
- `missions_api/VERSION` (M)
- `missions_api/main.py` (M)
- `missions_api/mcp_server.py` (M)
- `missions_api/spec.md` (M)
- `missions_api/src/auth.py` (M)
- `missions_api/src/missions/router.py` (M)
- `missions_api/staffing_heuristics.txt` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/lb-internal.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/scheduler.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prometheus/prometheus.yml` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/main.py` (M)
- `prompts_api/spec.md` (M)
- `prompts_api/src/__pycache__/cache.cpython-313.pyc` (D)
- `prompts_api/src/__pycache__/database.cpython-313.pyc` (D)
- `prompts_api/src/__pycache__/main.cpython-313.pyc` (D)
- `scripts/async_manage_env.sh` (M)
- `scripts/deploy.sh` (M)
- `scripts/generate_specs.py` (M)
- `todo.md` (M)
- `users_api/Dockerfile` (M)
- `users_api/VERSION` (M)
- `users_api/main.py` (M)
- `users_api/mcp_server.py` (M)
- `users_api/spec.md` (M)
- `users_api/src/users/models.py` (M)
- `users_api/src/users/router.py` (M)
- `users_api/src/users/schemas.py` (M)
- `.agents/workflows/analyse-prompt.md` (??)
- `.antigravity_env` (??)
- `agent_hr_api/metadata.py` (??)
- `agent_hr_api/test_main.py` (??)
- `agent_hr_api/test_mcp.py` (??)
- `agent_hr_api/test_session.py` (??)
- `agent_missions_api/` (??)
- `agent_ops_api/metadata.py` (??)
- `agent_ops_api/test_main.py` (??)
- `agent_ops_api/test_mcp.py` (??)
- `agent_ops_api/test_session.py` (??)
- `agent_router_api/test_main.py` (??)
- `agent_router_api/test_mcp.py` (??)
- `agent_router_api/test_session.py` (??)
- `docs/agent_testing_guide.md` (??)
- `drive_api/test_main.py` (??)
- `frontend/src/components/ConsultantProfile.vue` (??)
- `frontend/src/components/agent/CandidateProfileCard.vue` (??)
- `frontend/src/components/agent/ConsultantCard.vue` (??)
- `frontend/src/components/agent/ItemCard.vue` (??)
- `frontend/src/components/agent/MissionCard.vue` (??)
- `frontend/src/components/agent/SystemHealthCard.vue` (??)
- `frontend/src/components/agent/ToolExecutionList.vue` (??)
- `frontend/src/views/AgentsDocs.vue` (??)
- `get_token.py` (??)
- `analytics_mcp/test_main.py` (??)
- `missions_api/test_main.py` (??)
- `missions_api/test_mcp_app.py` (??)
- `platform-engineering/terraform/cr_agent_missions.tf` (??)
- `prompts_api/test_main.py` (??)
- `reports/` (??)
- `scripts/agent_prompt_tests.py` (??)
- `scripts/sync_prompts.py` (??)

---

## Mise à jour automatique - 2026-04-15 09:14:35

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1145  | 317  |  72% |
| cv_api           | 1706  | 578  |  66% |
| drive_api        | 853   | 370  |  57% |
| items_api        | 1095  | 242  |  78% |
| prompts_api      | 675   | 143  |  79% |
| users_api        | 1327  | 412  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- fix(terraform): suppression des accolades orphelines dans cr_agent_hr/ops/router/analytics

#### Fichiers (non commités)
- `GENTS.md` (M)
- `agent_hr_api/VERSION` (M)
- `agent_ops_api/VERSION` (M)
- `agent_router_api/VERSION` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/spec.md` (M)
- `cv_api/.coverage` (M)
- `cv_api/VERSION` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `frontend/VERSION` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `analytics_mcp/VERSION` (M)
- `missions_api/VERSION` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/.terraform.lock.hcl` (M)
- `platform-engineering/terraform/cr_agent_hr.tf` (M)
- `platform-engineering/terraform/cr_agent_ops.tf` (M)
- `platform-engineering/terraform/cr_agent_router.tf` (M)
- `platform-engineering/terraform/cr_competencies.tf` (M)
- `platform-engineering/terraform/cr_cv.tf` (M)
- `platform-engineering/terraform/cr_drive.tf` (M)
- `platform-engineering/terraform/cr_items.tf` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/cr_missions.tf` (M)
- `platform-engineering/terraform/cr_prompts.tf` (M)
- `platform-engineering/terraform/cr_users.tf` (M)
- `platform-engineering/terraform/slo.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/.coverage` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/src/prompts/__pycache__/analyzer.cpython-313.pyc` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)

---

## Mise à jour automatique - 2026-04-15 08:37:24

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1145  | 317  |  72% |
| cv_api           | 1671  | 570  |  66% |
| drive_api        | 856   | 371  |  57% |
| items_api        | 1098  | 243  |  78% |
| prompts_api      | 640   | 122  |  81% |
| users_api        | 1327  | 412  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Add semantic cache read/write to HR and Ops agents
- Improve agent prompts and A2A observability

#### Fichiers (non commités)
- `rive_api/test.db` (M)
- `prompts_api/.coverage` (M)
- `prompts_api/conftest.py` (M)
- `analytics_mcp/conftest.py` (??)

---

## Mise à jour automatique - 2026-04-15 08:31:17

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1145  | 317  |  72% |
| cv_api           | 1671  | 570  |  66% |
| drive_api        | 818   | 374  |  54% |
| items_api        | 1098  | 243  |  78% |
| prompts_api      | 593   | 116  |  80% |
| users_api        | 1327  | 412  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Improve agent prompts and A2A observability

#### Fichiers (non commités)
- `gent_hr_api/agent.py` (M)
- `agent_ops_api/agent.py` (M)
- `cv_api/.coverage` (M)
- `drive_api/main.py` (M)
- `drive_api/test.db` (M)
- `items_api/main.py` (M)
- `analytics_mcp/mcp_app.py` (M)
- `missions_api/main.py` (M)
- `platform-engineering/terraform/cr_analytics.tf` (M)
- `platform-engineering/terraform/vpc.tf` (M)
- `platform-engineering/terraform/waf.tf` (M)
- `cv_api/conftest.py` (??)
- `drive_api/conftest.py` (??)
- `missions_api/conftest.py` (??)
- `prompts_api/conftest.py` (??)

---

## Mise à jour automatique - 2026-04-15 08:25:36

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1145  | 317  |  72% |
| cv_api           | 1648  | 564  |  66% |
| drive_api        | 792   | 367  |  54% |
| items_api        | 1094  | 242  |  78% |
| prompts_api      | 593   | 116  |  80% |
| users_api        | 1327  | 412  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_hr_api/agent.py` (M)
- `agent_hr_api/agent_hr_api.system_instruction.txt` (M)
- `agent_hr_api/main.py` (M)
- `agent_ops_api/agent.py` (M)
- `agent_ops_api/agent_ops_api.system_instruction.txt` (M)
- `agent_ops_api/main.py` (M)
- `agent_router_api/agent.py` (M)
- `agent_router_api/agent_router_api.system_instruction.txt` (M)
- `drive_api/test.db` (M)

---

## Mise à jour automatique - 2026-04-15 08:11:48

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | N/A   | N/A  | N/A  |
| competencies_api | 1145  | 317  |  72% |
| cv_api           | 1648  | 564  |  66% |
| drive_api        | 792   | 367  |  54% |
| items_api        | 1094  | 242  |  78% |
| prompts_api      | 593   | 116  |  80% |
| users_api        | 1327  | 410  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `GENTS.md` (M)
- `agent_api/.coverage` (D)
- `agent_api/.dockerignore` (D)
- `agent_api/Dockerfile` (D)
- `agent_api/VERSION` (D)
- `agent_api/__init__.py` (D)
- `agent_api/agent.py` (D)
- `agent_api/agent_api.assistant_system_instruction.txt` (D)
- `agent_api/agent_api.capabilities_instruction.txt` (D)
- `agent_api/conftest.py` (D)
- `agent_api/logger.py` (D)
- `agent_api/main.py` (D)
- `agent_api/mcp_client.py` (D)
- `agent_api/metrics.py` (D)
- `agent_api/requirements.txt` (D)
- `agent_api/session.py` (D)
- `agent_api/spec.md` (D)
- `agent_api/test_agent_logic.py` (D)
- `agent_api/test_main.py` (D)
- `agent_api/test_mcp.py` (D)
- `agent_api/test_session.py` (D)
- `competencies_api/.coverage` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/router.py` (M)
- `competencies_api/src/competencies/schemas.py` (M)
- `competencies_api/test_integration.py` (M)
- `cv_api/VERSION` (M)
- `cv_api/spec.md` (M)
- `docker-compose.yml` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/src/drive_service.py` (M)
- `drive_api/src/models.py` (M)
- `drive_api/src/router.py` (M)
- `drive_api/src/schemas.py` (M)
- `drive_api/test.db` (M)
- `frontend/VERSION` (M)
- `frontend/nginx/default.conf` (M)
- `frontend/src/components/DriveAdminPanel.vue` (M)
- `frontend/src/components/agent/AgentExpertTerminal.vue` (M)
- `frontend/src/services/auth.ts` (M)
- `frontend/src/views/Registry.vue` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `missions_api/VERSION` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/cloudrun.tf` (M)
- `platform-engineering/terraform/database.tf` (M)
- `platform-engineering/terraform/db_init_job.tf` (M)
- `platform-engineering/terraform/db_migrations_job.tf` (M)
- `platform-engineering/terraform/imports_users.tf` (D)
- `platform-engineering/terraform/lb-internal.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/pubsub.tf` (M)
- `platform-engineering/terraform/scheduler.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/VERSION` (M)
- `scripts/deploy.sh` (M)
- `scripts/run_tests.sh` (M)
- `seed_data.py` (M)
- `todo.md` (M)
- `users_api/VERSION` (M)
- `users_api/spec.md` (M)
- `agent_hr_api/` (??)
- `agent_ops_api/` (??)
- `agent_router_api/` (??)
- `bootstrap/platform_engineering.tf` (??)
- `platform-engineering/.dockerignore` (??)
- `platform-engineering/Dockerfile` (??)
- `platform-engineering/terraform/cr_agent_hr.tf` (??)
- `platform-engineering/terraform/cr_agent_ops.tf` (??)
- `platform-engineering/terraform/cr_agent_router.tf` (??)
- `platform-engineering/terraform/cr_competencies.tf` (??)
- `platform-engineering/terraform/cr_cv.tf` (??)
- `platform-engineering/terraform/cr_drive.tf` (??)
- `platform-engineering/terraform/cr_items.tf` (??)
- `platform-engineering/terraform/cr_analytics.tf` (??)
- `platform-engineering/terraform/cr_missions.tf` (??)
- `platform-engineering/terraform/cr_prompts.tf` (??)
- `platform-engineering/terraform/cr_users.tf` (??)
- `platform-engineering/terraform/scratch_check_env.py` (??)
- `platform-engineering/terraform/scratch_check_tf_env.py` (??)
- `platform-engineering/terraform/scratch_clean_db.py` (??)
- `platform-engineering/terraform/scratch_clean_external_bg.py` (??)
- `platform-engineering/terraform/scratch_cleanup.py` (??)
- `platform-engineering/terraform/scratch_fix_agents.py` (??)
- `platform-engineering/terraform/scratch_fix_names.py` (??)
- `platform-engineering/terraform/scratch_fix_refs.py` (??)
- `platform-engineering/terraform/scratch_gen.py` (??)
- `platform-engineering/terraform/scratch_unroll.py` (??)
- `scripts/async_manage_env.sh` (??)
- `scripts/destroy_old_cr.sh` (??)

---

## Mise à jour automatique - 2026-04-13 23:43:17

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1615  | 372  |  77% |
| competencies_api | 1126  | 314  |  72% |
| cv_api           | 1648  | 564  |  66% |
| drive_api        | 786   | 363  |  54% |
| items_api        | 1094  | 242  |  78% |
| prompts_api      | 593   | 116  |  80% |
| users_api        | 1327  | 412  |  69% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `agents/workflows/git-push.md` (M)
- `.gitignore` (M)
- `.pre-commit-config.yaml` (M)
- `AGENTS.md` (M)
- `agent_api/.coverage` (M)
- `agent_api/VERSION` (M)
- `agent_api/agent.py` (M)
- `agent_api/main.py` (M)
- `agent_api/mcp_client.py` (M)
- `agent_api/spec.md` (M)
- `agent_api/test_agent_logic.py` (M)
- `agent_api/test_main.py` (M)
- `bootstrap/services.tf` (M)
- `competencies_api/.coverage` (M)
- `competencies_api/VERSION` (M)
- `competencies_api/spec.md` (M)
- `competencies_api/src/competencies/router.py` (M)
- `cv_api/.coverage` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/VERSION` (M)
- `cv_api/__pycache__/test_main.cpython-313-pytest-9.0.2.pyc` (M)
- `cv_api/metrics.py` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/__pycache__/schemas.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `cv_api/src/cvs/schemas.py` (M)
- `cv_api/test_main.py` (M)
- `db_migrations/VERSION` (M)
- `db_migrations/changelogs/users/changelog.yaml` (M)
- `db_migrations/docker-entrypoint.sh` (M)
- `docker-compose.yml` (M)
- `drive_api/VERSION` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `frontend/VERSION` (M)
- `frontend/nginx/default.conf` (M)
- `frontend/package-lock.json` (M)
- `frontend/package.json` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/main.ts` (M)
- `frontend/src/router/index.ts` (M)
- `frontend/src/services/auth.ts` (M)
- `frontend/src/style.css` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/Profile.vue` (M)
- `frontend/src/views/Specs.vue` (M)
- `frontend/vite.config.ts` (M)
- `items_api/VERSION` (M)
- `items_api/spec.md` (M)
- `analytics_mcp/VERSION` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/requirements.txt` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/bigquery.tf` (M)
- `platform-engineering/terraform/cloudrun.tf` (M)
- `platform-engineering/terraform/db_init_job.tf` (M)
- `platform-engineering/terraform/lb-internal.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `prompts_api/.coverage` (M)
- `prompts_api/Dockerfile` (M)
- `prompts_api/VERSION` (M)
- `prompts_api/src/prompts/__pycache__/analyzer.cpython-313.pyc` (M)
- `prompts_api/src/prompts/__pycache__/router.cpython-313.pyc` (M)
- `prompts_api/src/prompts/analyzer.py` (M)
- `prompts_api/src/prompts/router.py` (M)
- `prompts_api/tests/__pycache__/test_prompts.cpython-313-pytest-9.0.2.pyc` (M)
- `prompts_api/tests/test_prompts.py` (M)
- `scripts/deploy.sh` (M)
- `scripts/run_tests.sh` (M)
- `seed_data.py` (M)
- `todo.md` (M)
- `users_api/VERSION` (M)
- `users_api/main.py` (M)
- `users_api/mcp_server.py` (M)
- `users_api/spec.md` (M)
- `users_api/src/__pycache__/auth.cpython-313.pyc` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/users/models.py` (M)
- `users_api/src/users/router.py` (M)
- `users_api/src/users/schemas.py` (M)
- `.agents/workflows/analyse-code-api.md` (??)
- `.agents/workflows/analyse-security.md` (??)
- `agent_api/.dockerignore` (??)
- `db_migrations/changelogs/missions/` (??)
- `docs/` (??)
- `drive_api/.dockerignore` (??)
- `frontend/src/components/agent/` (??)
- `frontend/src/components/ui/` (??)
- `frontend/src/services/agentApi.ts` (??)
- `frontend/src/stores/` (??)
- `frontend/src/types/` (??)
- `frontend/src/utils/` (??)
- `frontend/src/views/AdminAvailability.vue` (??)
- `frontend/src/views/FinopsAdmin.vue` (??)
- `frontend/src/views/MissionDetail.vue` (??)
- `frontend/src/views/MissionsList.vue` (??)
- `analytics_mcp/.dockerignore` (??)
- `analytics_mcp/logger.py` (??)
- `missions_api/` (??)
- `platform-engineering/terraform/imports_users.tf` (??)
- `platform-engineering/terraform/scheduler.tf` (??)
- `roi.md` (??)

---

## Mise à jour automatique - 2026-04-13 14:30:07

### Résumé des Changements

### Changements fonctionnels
- Finalisation de l'intégration FinOps pour le suivi de la consommation de l'IA (Agent et analyse de CV) et l'export vers BigQuery.

### Changements techniques
- Résolution du conflit de dépendance `opentelemetry-instrumentation-httpx` et rétablissement des imports.
- Correction des tests unitaires: types SQLAlchemy (compatibilité JSON sur SQLite), neutralisation de l'exporteur OTEL en phase de test pour éviter les crashs I/O, restauration de l'authentification dans les tests d'intégration en gérant mieux les overrides JWT de fastapi.

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1511  | 424  |  72% |
| competencies_api | 1120  | 308  |  72% |
| cv_api           | 1537  | 579  |  62% |
| drive_api        | 786   | 363  |  54% |
| items_api        | 1094  | 242  |  78% |
| prompts_api      | 585   | 116  |  80% |
| users_api        | 1253  | 359  |  71% |

### Modifications depuis le dernier push

#### Commits non pushés
- Aucun commit local en attente

#### Fichiers (non commités)
- `gent_api/.coverage` (M)
- `agent_api/agent.py` (M)
- `agent_api/main.py` (M)
- `agent_api/mcp_client.py` (M)
- `agent_api/pytest.log` (M)
- `agent_api/requirements.txt` (M)
- `agent_api/spec.md` (M)
- `competencies_api/.coverage` (M)
- `competencies_api/competencies_test.db` (M)
- `competencies_api/main.py` (M)
- `competencies_api/mcp_app.py` (M)
- `competencies_api/pytest.log` (M)
- `competencies_api/requirements.txt` (M)
- `competencies_api/spec.md` (M)
- `cv_api/.coverage` (M)
- `cv_api/Dockerfile` (M)
- `cv_api/__pycache__/main.cpython-313.pyc` (M)
- `cv_api/main.py` (M)
- `cv_api/mcp_app.py` (M)
- `cv_api/pytest.log` (M)
- `cv_api/requirements.txt` (M)
- `cv_api/spec.md` (M)
- `cv_api/src/cvs/__pycache__/router.cpython-313.pyc` (M)
- `cv_api/src/cvs/router.py` (M)
- `docker-compose.yml` (M)
- `drive_api/main.py` (M)
- `drive_api/mcp_app.py` (M)
- `drive_api/pytest.log` (M)
- `drive_api/requirements.txt` (M)
- `drive_api/spec.md` (M)
- `drive_api/test.db` (M)
- `frontend/dist/assets/Admin-CJOjBzkP.js` (D)
- `frontend/dist/assets/AdminDeduplication-DFhzrgse.js` (D)
- `frontend/dist/assets/AdminDeduplication-LZH1033o.css` (D)
- `frontend/dist/assets/AdminReanalysis-DfBatNjo.css` (D)
- `frontend/dist/assets/AdminReanalysis-HpkUAFAm.js` (D)
- `frontend/dist/assets/AdminUsers-BDtHBpsN.css` (D)
- `frontend/dist/assets/AdminUsers-CiN8hdIZ.js` (D)
- `frontend/dist/assets/Competencies-CcGKhSmv.js` (D)
- `frontend/dist/assets/Docs-HoP60Exl.js` (D)
- `frontend/dist/assets/Help-DG4gdE-Q.js` (D)
- `frontend/dist/assets/ImportCV-wVndKWoU.js` (D)
- `frontend/dist/assets/Login-CwNjBHuQ.js` (D)
- `frontend/dist/assets/Profile-ChfpUFcr.js` (D)
- `frontend/dist/assets/PromptsAdmin-WENqPvc-.js` (D)
- `frontend/dist/assets/Registry-BJsGtb_H.css` (D)
- `frontend/dist/assets/Registry-D8ZISgLH.js` (D)
- `frontend/dist/assets/Specs-B1cYOVyG.css` (D)
- `frontend/dist/assets/Specs-CXPno_d_.js` (D)
- `frontend/dist/assets/UserDetail-BljmA_iX.js` (D)
- `frontend/dist/assets/alert-circle-CKaBzym4.js` (D)
- `frontend/dist/assets/file-text-DaTRcG5l.js` (D)
- `frontend/dist/assets/fingerprint-DMT3B78s.js` (D)
- `frontend/dist/assets/index-CHC8wD0C.js` (D)
- `frontend/dist/assets/index-gdZgbVQS.css` (D)
- `frontend/dist/assets/loader-2-DTI3CKkx.js` (D)
- `frontend/dist/assets/lock-AK_MPM4f.js` (D)
- `frontend/dist/assets/message-square-sMBfwYeI.js` (D)
- `frontend/dist/assets/search-BaSoE7wl.js` (D)
- `frontend/dist/assets/shield-check-Ds-3_e63.js` (D)
- `frontend/dist/assets/users-C9_j-OyP.js` (D)
- `frontend/dist/index.html` (M)
- `frontend/nginx/default.conf` (M)
- `frontend/node_modules/.package-lock.json` (M)
- `frontend/package-lock.json` (M)
- `frontend/package.json` (M)
- `frontend/src/App.vue` (M)
- `frontend/src/components/AdminUserManagement.vue` (M)
- `frontend/src/router/index.ts` (M)
- `frontend/src/views/AdminDeduplication.vue` (M)
- `frontend/src/views/AdminReanalysis.vue` (M)
- `frontend/src/views/AdminUsers.vue` (M)
- `frontend/src/views/Home.vue` (M)
- `frontend/src/views/Registry.vue` (M)
- `frontend/src/views/Specs.vue` (M)
- `items_api/items_test.db` (M)
- `items_api/main.py` (M)
- `items_api/mcp_app.py` (M)
- `items_api/pytest.log` (M)
- `items_api/requirements.txt` (M)
- `items_api/spec.md` (M)
- `items_api/src/items/models.py` (M)
- `analytics_mcp/mcp_app.py` (M)
- `analytics_mcp/mcp_server.py` (M)
- `analytics_mcp/pytest.log` (M)
- `analytics_mcp/requirements.txt` (M)
- `analytics_mcp/tests/test_mcp_server.py` (M)
- `platform-engineering/envs/dev.yaml` (M)
- `platform-engineering/envs/prd.yaml` (M)
- `platform-engineering/envs/uat.yaml` (M)
- `platform-engineering/manage_env.py` (M)
- `platform-engineering/terraform/cloudrun.tf` (M)
- `platform-engineering/terraform/dashboard.tf` (M)
- `platform-engineering/terraform/lb-internal.tf` (M)
- `platform-engineering/terraform/lb.tf` (M)
- `platform-engineering/terraform/variables.tf` (M)
- `platform-engineering/terraform/vpc.tf` (M)
- `prometheus/prometheus.yml` (M)
- `prompts_api/.coverage` (M)
- `prompts_api/main.py` (M)
- `prompts_api/prompts_test.db` (M)
- `prompts_api/pytest.log` (M)
- `prompts_api/requirements.txt` (M)
- `prompts_api/spec.md` (M)
- `scripts/deploy.sh` (M)
- `scripts/run_tests.sh` (M)
- `seed_data.py` (M)
- `todo.md` (M)
- `users_api/main.py` (M)
- `users_api/mcp_app.py` (M)
- `users_api/mcp_server.py` (M)
- `users_api/pytest.log` (M)
- `users_api/requirements.txt` (M)
- `users_api/spec.md` (M)
- `users_api/src/__pycache__/auth.cpython-313.pyc` (M)
- `users_api/src/auth.py` (M)
- `users_api/src/users/router.py` (M)
- `users_api/test_integration.py` (M)
- `users_api/users_test.db` (M)
- `agent_api/VERSION` (??)
- `agent_api/metrics.py` (??)
- `competencies_api/VERSION` (??)
- `cv_api/VERSION` (??)
- `cv_api/metrics.py` (??)
- `db_migrations/VERSION` (??)
- `drive_api/VERSION` (??)
- `frontend/VERSION` (??)
- `frontend/dist/assets/Admin-BPeYJl5F.js` (??)
- `frontend/dist/assets/AdminDeduplication-DV1ouHww.css` (??)
- `frontend/dist/assets/AdminDeduplication-qzETmdpE.js` (??)
- `frontend/dist/assets/AdminReanalysis-507jyQvo.css` (??)
- `frontend/dist/assets/AdminReanalysis-Bny6ljrV.js` (??)
- `frontend/dist/assets/AdminUsers-DOX-dt6Q.js` (??)
- `frontend/dist/assets/AdminUsers-Dw21skb3.css` (??)
- `frontend/dist/assets/AiOps-1FMdrcXG.js` (??)
- `frontend/dist/assets/AiOps-iFx12hq8.css` (??)
- `frontend/dist/assets/Competencies-alogPQXZ.js` (??)
- `frontend/dist/assets/Docs-Dw79DhaI.js` (??)
- `frontend/dist/assets/Help-B2maHI9Y.js` (??)
- `frontend/dist/assets/ImportCV-akeHXa-4.js` (??)
- `frontend/dist/assets/InfraMap-CokP4oNZ.js` (??)
- `frontend/dist/assets/InfraMap-iA5HexTi.css` (??)
- `frontend/dist/assets/Login-CMC4QWqF.js` (??)
- `frontend/dist/assets/Profile-CyCFyzpX.js` (??)
- `frontend/dist/assets/PromptsAdmin-DJVJNqvv.js` (??)
- `frontend/dist/assets/Registry-BfBEPINd.js` (??)
- `frontend/dist/assets/Registry-CWRmEu-H.css` (??)
- `frontend/dist/assets/Specs-6i3sfdnh.css` (??)
- `frontend/dist/assets/Specs-BAkYghip.js` (??)
- `frontend/dist/assets/Tableau10-B-NsZVaP.js` (??)
- `frontend/dist/assets/UserDetail-sFRfUvvp.js` (??)
- `frontend/dist/assets/alert-circle-Cf1SMGkT.js` (??)
- `frontend/dist/assets/arc-Dn7IjmMZ.js` (??)
- `frontend/dist/assets/array-BKyUJesY.js` (??)
- `frontend/dist/assets/blockDiagram-c4efeb88-D9-OO_uE.js` (??)
- `frontend/dist/assets/c4Diagram-c83219d4-CpWXPZxb.js` (??)
- `frontend/dist/assets/channel-Bww4FrTA.js` (??)
- `frontend/dist/assets/classDiagram-beda092f-DrnHKBA7.js` (??)
- `frontend/dist/assets/classDiagram-v2-2358418a-SQa1TSEC.js` (??)
- `frontend/dist/assets/clone-3YSEd349.js` (??)
- `frontend/dist/assets/createText-1719965b-DDKD6rY6.js` (??)
- `frontend/dist/assets/edges-96097737-1K8FpBIa.js` (??)
- `frontend/dist/assets/erDiagram-0228fc6a-DqKquF9v.js` (??)
- `frontend/dist/assets/file-text-CtD1Pebx.js` (??)
- `frontend/dist/assets/fingerprint-CReZd-Te.js` (??)
- `frontend/dist/assets/flowDb-c6c81e3f-BJ14_0KW.js` (??)
- `frontend/dist/assets/flowDiagram-50d868cf-WJrna2rq.js` (??)
- `frontend/dist/assets/flowDiagram-v2-4f6560a1-rsAqWf4U.js` (??)
- `frontend/dist/assets/flowchart-elk-definition-6af322e1-DxJXKNHM.js` (??)
- `frontend/dist/assets/ganttDiagram-a2739b55-zS1q5oki.js` (??)
- `frontend/dist/assets/gitGraphDiagram-82fe8481-2zydsTii.js` (??)
- `frontend/dist/assets/graph-BBkctj09.js` (??)
- `frontend/dist/assets/index-5325376f-DzUYN1DX.js` (??)
- `frontend/dist/assets/index-BQJ9CG0p.css` (??)
- `frontend/dist/assets/index-DVv23O1N.js` (??)
- `frontend/dist/assets/infoDiagram-8eee0895-8Y9A9VRe.js` (??)
- `frontend/dist/assets/init-Gi6I4Gst.js` (??)
- `frontend/dist/assets/journeyDiagram-c64418c1-RRJDrpat.js` (??)
- `frontend/dist/assets/katex-DkKDou_j.js` (??)
- `frontend/dist/assets/layout-v3cWZ40Z.js` (??)
- `frontend/dist/assets/line-C-aO-QSY.js` (??)
- `frontend/dist/assets/linear-BJdUXJds.js` (??)
- `frontend/dist/assets/loader-2-Cizr1noC.js` (??)
- `frontend/dist/assets/lock-DuSbfI7T.js` (??)
- `frontend/dist/assets/message-square-C0STsqdz.js` (??)
- `frontend/dist/assets/mindmap-definition-8da855dc-COqpXAmP.js` (??)
- `frontend/dist/assets/ordinal-Cboi1Yqb.js` (??)
- `frontend/dist/assets/path-CbwjOpE9.js` (??)
- `frontend/dist/assets/pieDiagram-a8764435-CdaZd1gj.js` (??)
- `frontend/dist/assets/quadrantDiagram-1e28029f-DSuJtVqv.js` (??)
- `frontend/dist/assets/requirementDiagram-08caed73-B-PvON7s.js` (??)
- `frontend/dist/assets/sankeyDiagram-a04cb91d-CV1hBwLG.js` (??)
- `frontend/dist/assets/search-D2ZhX7BJ.js` (??)
- `frontend/dist/assets/sequenceDiagram-c5b8d532-DFdUIztb.js` (??)
- `frontend/dist/assets/shield-check-DSZ9YNK7.js` (??)
- `frontend/dist/assets/stateDiagram-1ecb1508-C_E-CfWV.js` (??)
- `frontend/dist/assets/stateDiagram-v2-c2b004d7-B8hO1WdS.js` (??)
- `frontend/dist/assets/styles-b4e223ce-BDOX84Mo.js` (??)
- `frontend/dist/assets/styles-ca3715f6-Bv7MouOo.js` (??)
- `frontend/dist/assets/styles-d45a18b0-CwBttNpV.js` (??)
- `frontend/dist/assets/svgDrawCommon-b86b1483-d7hAn6Xz.js` (??)
- `frontend/dist/assets/timeline-definition-faaaa080-C9NxjybX.js` (??)
- `frontend/dist/assets/users-DvW7kGSY.js` (??)
- `frontend/dist/assets/xychartDiagram-f5964ef8-4_qribry.js` (??)
- `frontend/node_modules/.bin/csv2json` (??)
- `frontend/node_modules/.bin/csv2tsv` (??)
- `frontend/node_modules/.bin/dsv2dsv` (??)
- `frontend/node_modules/.bin/dsv2json` (??)
- `frontend/node_modules/.bin/json2csv` (??)
- `frontend/node_modules/.bin/json2dsv` (??)
- `frontend/node_modules/.bin/json2tsv` (??)
- `frontend/node_modules/.bin/katex` (??)
- `frontend/node_modules/.bin/tsv2csv` (??)
- `frontend/node_modules/.bin/tsv2json` (??)
- `frontend/node_modules/.bin/uuid` (??)
- `frontend/node_modules/.bin/uvu` (??)
- `frontend/node_modules/@braintree/` (??)
- `frontend/node_modules/@kurkle/` (??)
- `frontend/node_modules/@types/d3-scale-chromatic/` (??)
- `frontend/node_modules/@types/d3-scale/` (??)
- `frontend/node_modules/@types/d3-time/` (??)
- `frontend/node_modules/@types/debug/` (??)
- `frontend/node_modules/@types/mdast/` (??)
- `frontend/node_modules/@types/ms/` (??)
- `frontend/node_modules/@types/trusted-types/` (??)
- `frontend/node_modules/@types/unist/` (??)
- `frontend/node_modules/character-entities/` (??)
- `frontend/node_modules/chart.js/` (??)
- `frontend/node_modules/commander/` (??)
- `frontend/node_modules/cose-base/` (??)
- `frontend/node_modules/cytoscape-cose-bilkent/` (??)
- `frontend/node_modules/cytoscape/` (??)
- `frontend/node_modules/d3-array/` (??)
- `frontend/node_modules/d3-axis/` (??)
- `frontend/node_modules/d3-brush/` (??)
- `frontend/node_modules/d3-chord/` (??)
- `frontend/node_modules/d3-color/` (??)
- `frontend/node_modules/d3-contour/` (??)
- `frontend/node_modules/d3-delaunay/` (??)
- `frontend/node_modules/d3-dispatch/` (??)
- `frontend/node_modules/d3-drag/` (??)
- `frontend/node_modules/d3-dsv/` (??)
- `frontend/node_modules/d3-ease/` (??)
- `frontend/node_modules/d3-fetch/` (??)
- `frontend/node_modules/d3-force/` (??)
- `frontend/node_modules/d3-format/` (??)
- `frontend/node_modules/d3-geo/` (??)
- `frontend/node_modules/d3-hierarchy/` (??)
- `frontend/node_modules/d3-interpolate/` (??)
- `frontend/node_modules/d3-path/` (??)
- `frontend/node_modules/d3-polygon/` (??)
- `frontend/node_modules/d3-quadtree/` (??)
- `frontend/node_modules/d3-random/` (??)
- `frontend/node_modules/d3-sankey/` (??)
- `frontend/node_modules/d3-scale-chromatic/` (??)
- `frontend/node_modules/d3-scale/` (??)
- `frontend/node_modules/d3-selection/` (??)
- `frontend/node_modules/d3-shape/` (??)
- `frontend/node_modules/d3-time-format/` (??)
- `frontend/node_modules/d3-time/` (??)
- `frontend/node_modules/d3-timer/` (??)
- `frontend/node_modules/d3-transition/` (??)
- `frontend/node_modules/d3-zoom/` (??)
- `frontend/node_modules/d3/` (??)
- `frontend/node_modules/dagre-d3-es/` (??)
- `frontend/node_modules/dayjs/` (??)
- `frontend/node_modules/debug/` (??)
- `frontend/node_modules/decode-named-character-reference/` (??)
- `frontend/node_modules/delaunator/` (??)
- `frontend/node_modules/dequal/` (??)
- `frontend/node_modules/diff/` (??)
- `frontend/node_modules/dompurify/` (??)
- `frontend/node_modules/elkjs/` (??)
- `frontend/node_modules/iconv-lite/` (??)
- `frontend/node_modules/internmap/` (??)
- `frontend/node_modules/katex/` (??)
- `frontend/node_modules/khroma/` (??)
- `frontend/node_modules/kleur/` (??)
- `frontend/node_modules/layout-base/` (??)
- `frontend/node_modules/lodash-es/` (??)
- `frontend/node_modules/mdast-util-from-markdown/` (??)
- `frontend/node_modules/mdast-util-to-string/` (??)
- `frontend/node_modules/mermaid/` (??)
- `frontend/node_modules/micromark-core-commonmark/` (??)
- `frontend/node_modules/micromark-factory-destination/` (??)
- `frontend/node_modules/micromark-factory-label/` (??)
- `frontend/node_modules/micromark-factory-space/` (??)
- `frontend/node_modules/micromark-factory-title/` (??)
- `frontend/node_modules/micromark-factory-whitespace/` (??)
- `frontend/node_modules/micromark-util-character/` (??)
- `frontend/node_modules/micromark-util-chunked/` (??)
- `frontend/node_modules/micromark-util-classify-character/` (??)
- `frontend/node_modules/micromark-util-combine-extensions/` (??)
- `frontend/node_modules/micromark-util-decode-numeric-character-reference/` (??)
- `frontend/node_modules/micromark-util-decode-string/` (??)
- `frontend/node_modules/micromark-util-encode/` (??)
- `frontend/node_modules/micromark-util-html-tag-name/` (??)
- `frontend/node_modules/micromark-util-normalize-identifier/` (??)
- `frontend/node_modules/micromark-util-resolve-all/` (??)
- `frontend/node_modules/micromark-util-sanitize-uri/` (??)
- `frontend/node_modules/micromark-util-subtokenize/` (??)
- `frontend/node_modules/micromark-util-symbol/` (??)
- `frontend/node_modules/micromark-util-types/` (??)
- `frontend/node_modules/micromark/` (??)
- `frontend/node_modules/mri/` (??)
- `frontend/node_modules/ms/` (??)
- `frontend/node_modules/non-layered-tidy-tree-layout/` (??)
- `frontend/node_modules/robust-predicates/` (??)
- `frontend/node_modules/rw/` (??)
- `frontend/node_modules/sade/` (??)
- `frontend/node_modules/safer-buffer/` (??)
- `frontend/node_modules/stylis/` (??)
- `frontend/node_modules/ts-dedent/` (??)
- `frontend/node_modules/unist-util-stringify-position/` (??)
- `frontend/node_modules/uuid/` (??)
- `frontend/node_modules/uvu/` (??)
- `frontend/node_modules/vue-chartjs/` (??)
- `frontend/node_modules/web-worker/` (??)
- `frontend/src/views/AiOps.vue` (??)
- `frontend/src/views/InfraMap.vue` (??)
- `grafana/dashboards/functional_dashboard.json` (??)
- `items_api/VERSION` (??)
- `analytics_mcp/VERSION` (??)
- `analytics_mcp/auth.py` (??)
- `platform-engineering/terraform/bigquery.tf` (??)
- `prompts_api/VERSION` (??)
- `test_trace.py` (??)
- `users_api/VERSION` (??)
- `users_api/metrics.py` (??)

---

## Mise à jour automatique - 2026-04-09 12:08:18

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1176  | 144  |  88% |
| competencies_api | 898   | 198  |  78% |
| cv_api           | 987   | 175  |  82% |
| drive_api        | 719   | 327  |  55% |
| items_api        | 1031  | 210  |  80% |
| prompts_api      | 574   | 115  |  80% |
| users_api        | 1065  | 235  |  78% |

### Modifications depuis le dernier push

#### Commits non pushés
- Fix tests for async routing and mocks

#### Fichiers (non commités)
- `agents/workflows/git-push.md` (M)
- `agent_api/main.py` (M)
- `competencies_api/main.py` (M)
- `drive_api/main.py` (M)
- `get_failures.py` (D)
- `patch_async_tests.py` (D)
- `patch_code.py` (D)
- `patch_code_new.py` (D)
- `patch_cv_tests.py` (D)
- `patch_databases.py` (D)
- `patch_health.py` (D)
- `patch_health_v2.py` (D)
- `patch_mock.py` (D)
- `patch_secrets.py` (D)
- `patch_tf.py` (D)
- `prompts_api/main.py` (M)
- `scripts/generate_changelog.py` (M)
- `test_drive.py` (D)
- `test_drive_adc.py` (D)
- `test_fastapi_mock.py` (D)

---

## Mise à jour automatique - 2026-04-09 12:03:28

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1176  | 144  |  88% |
| competencies_api | 898   | 198  |  78% |
| cv_api           | 987   | 175  |  82% |
| drive_api        | 719   | 327  |  55% |
| items_api        | 1031  | 210  |  80% |
| prompts_api      | 574   | 115  |  80% |
| users_api        | 1065  | 235  |  78% |

---

## Mise à jour automatique - 2026-04-04 17:24:24

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1125  | 102  |  91% |
| competencies_api | 796   | 73   |  91% |
| cv_api           | 828   | 93   |  89% |
| drive_api        | 552   | 220  |  60% |
| items_api        | 880   | 86   |  90% |
| prompts_api      | 462   | 40   |  91% |
| users_api        | 995   | 103  |  90% |

---

## Mise à jour automatique - 2026-04-03 00:08:49

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1125  | 102  |  91% |
| competencies_api | 796   | 73   |  91% |
| cv_api           | 828   | 93   |  89% |
| drive_api        | 552   | 220  |  60% |
| items_api        | 880   | 86   |  90% |
| prompts_api      | 462   | 40   |  91% |
| users_api        | 995   | 103  |  90% |

---

## Mise à jour automatique - 2026-04-02 23:50:00

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1097  | 85   |  92% |
| competencies_api | 796   | 73   |  91% |
| cv_api           | 804   | 92   |  89% |
| drive_api        | 541   | 296  |  45% |
| items_api        | 880   | 86   |  90% |
| prompts_api      | 462   | 40   |  91% |
| users_api        | 995   | 103  |  90% |

---

## Mise à jour automatique - 2026-04-02 23:46:25

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1097  | 85   |  92% |
| competencies_api | 796   | 73   |  91% |
| cv_api           | 804   | 92   |  89% |
| items_api        | 880   | 86   |  90% |
| prompts_api      | 462   | 40   |  91% |
| users_api        | 995   | 103  |  90% |

---

## Mise à jour automatique - 2026-04-02 15:08:29

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 996   | 136  |  86% |
| competencies_api | 804   | 76   |  91% |
| cv_api           | 691   | 146  |  79% |
| items_api        | 889   | 89   |  90% |
| prompts_api      | 473   | 39   |  92% |
| users_api        | 900   | 95   |  89% |

---

## Mise à jour automatique - 2026-04-01 19:40:33

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 947   | 132  |  86% |
| competencies_api | 739   | 56   |  92% |
| cv_api           | 626   | 129  |  79% |
| items_api        | 824   | 69   |  92% |
| prompts_api      | 406   | 21   |  95% |
| users_api        | 835   | 68   |  92% |

---

## Mise à jour automatique - 2026-04-01 18:07:12

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 947   | 132  |  86% |
| competencies_api | 739   | 56   |  92% |
| cv_api           | 626   | 129  |  79% |
| items_api        | 824   | 69   |  92% |
| prompts_api      | 406   | 21   |  95% |
| users_api        | 835   | 68   |  92% |

---

## Mise à jour automatique - 2026-04-01 17:38:16

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 947   | 132  |  86% |
| competencies_api | 739   | 56   |  92% |
| cv_api           | 626   | 129  |  79% |
| items_api        | 824   | 69   |  92% |
| prompts_api      | 406   | 21   |  95% |
| users_api        | 835   | 68   |  92% |

---

## Mise à jour automatique - 2026-04-01 12:09:27

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 930   | 117  |  87% |
| competencies_api | 727   | 48   |  93% |
| cv_api           | 614   | 121  |  80% |
| items_api        | 812   | 61   |  92% |
| prompts_api      | 394   | 13   |  97% |
| users_api        | 813   | 50   |  94% |

---

## Mise à jour automatique - 2026-04-01 12:02:57

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 929   | 149  |  84% |
| competencies_api | 727   | 48   |  93% |
| cv_api           | 614   | 121  |  80% |
| items_api        | 812   | 61   |  92% |
| prompts_api      | 394   | 13   |  97% |
| users_api        | 813   | 50   |  94% |

---

# Changelog

## 2026-04-01

### Nouveautés et Améliorations
- Application d'une politique de sécurité *Zero-Trust* : Tous les `APIRouter` (Items, Prompts, Users, Competencies, CV, Agent) sont désormais protégés statiquement par le validateur `verify_jwt`.
- Le token JWT est propagé inter-services et requis pour valider les tests d'intégration.
- Optimisation et maximisation globale de la couverture de test (unitaires et d'intégration) pour l'ensemble des microservices afin de garantir la fiabilité des pipelines.

### Couverture de Code (Code Coverage)

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 929   | 149  | 84%   |
| competencies_api | 727   | 48   | 93%   |
| cv_api           | 614   | 121  | 80%   |
| items_api        | 812   | 61   | 92%   |
| prompts_api      | 394   | 13   | 97%   |
| users_api        | 813   | 50   | 94%   |
