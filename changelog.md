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
