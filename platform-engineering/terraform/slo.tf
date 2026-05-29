# ==============================================================
# SLOs définis par service dans chaque fichier cr_<service>.tf
# ==============================================================
# Les SLOs (Disponibilité + Latence) et les Custom Services
# Monitoring sont définis directement dans le fichier Terraform
# dédié à chaque microservice, permettant ainsi une configuration
# individualisée (seuils, objectifs) par service.
#
# Inventaire complet — 13 services, 26 SLOs (2 par service) :
#   - cr_users.tf           → users-api         (dispo 99.9%, latence 95%)
#   - cr_items.tf           → items-api          (dispo 99.9%, latence 95%)
#   - cr_competencies.tf    → competencies-api   (dispo 99.9%, latence 95%)
#   - cr_cv.tf              → cv-api             (dispo 99.0%, latence 95%)
#   - cr_missions.tf        → missions-api       (dispo 99.0%, latence 95%)
#   - cr_drive.tf           → drive-api          (dispo 99.5%, latence 95%)
#   - cr_prompts.tf         → prompts-api        (dispo 99.9%, latence 95%)
#   - cr_agent_router.tf    → agent-router-api   (dispo 99.5%, latence 95%)
#   - cr_agent_hr.tf        → agent-hr-api       (dispo 99.5%, latence 95%)
#   - cr_agent_ops.tf       → agent-ops-api      (dispo 99.5%, latence 95%)
#   - cr_agent_missions.tf  → agent-missions-api (dispo 99.5%, latence 95%)
#   - cr_analytics.tf       → analytics-mcp      (dispo 99.5%, latence 95%)
#   - cr_monitoring.tf      → monitoring-mcp     (dispo 99.5%, latence 95%)
#
# Note : frontend (cr_frontend.tf) n'expose pas de métriques
# Cloud Run standard — il est servi derrière Nginx/CDN.
# Son SLO est couvert par l'uptime check GCP défini dans uptime.tf.
# ==============================================================
