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
- `market_mcp/VERSION` (M)
- `market_mcp/mcp_app.py` (M)
- `market_mcp/requirements.txt` (M)
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
- `market_mcp/.dockerignore` (??)
- `market_mcp/logger.py` (??)
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
- `market_mcp/mcp_app.py` (M)
- `market_mcp/mcp_server.py` (M)
- `market_mcp/pytest.log` (M)
- `market_mcp/requirements.txt` (M)
- `market_mcp/tests/test_mcp_server.py` (M)
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
- `market_mcp/VERSION` (??)
- `market_mcp/auth.py` (??)
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
