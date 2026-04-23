# ==============================================================
# SLOs définis par service dans chaque fichier cr_<service>.tf
# ==============================================================
# Les SLOs (Disponibilité + Latence) et les Custom Services
# Monitoring sont définis directement dans le fichier Terraform
# dédié à chaque microservice, permettant ainsi une configuration
# individualisée (seuils, objectifs) par service.
#
# Fichiers concernés :
#   - cr_users.tf         → users-api
#   - cr_items.tf         → items-api
#   - cr_competencies.tf  → competencies-api
#   - cr_cv.tf            → cv-api
#   - cr_missions.tf      → missions-api
#   - cr_drive.tf         → drive-api
#   - cr_prompts.tf       → prompts-api
#   - cr_agent_router.tf  → agent-router-api
#   - cr_agent_hr.tf      → agent-hr-api
#   - cr_agent_ops.tf     → agent-ops-api
#   - cr_analytics.tf        → analytics-mcp
# ==============================================================
