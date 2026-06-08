# ==============================================================================
# SRE - Google Cloud Platform Monitoring & Alerting
# ==============================================================================
# Ce fichier définit les ressources de métrologie, d'alerte et de notification
# pour le warm-up automatique des microservices Cloud Run après authentification.
#
# Prérequis IAM (compte de service Terraform) :
#   - roles/logging.admin                           → créer les log-based metrics
#   - roles/monitoring.alertPolicyEditor            → créer les policies d'alerte
#   - roles/monitoring.notificationChannelEditor    → créer les canaux email

# ==============================================================================
# 1. Rôles IAM requis pour le compte de service Terraform
# ==============================================================================
# Attribue les rôles IAM nécessaires au compte de service Terraform par défaut
# (format : {PROJECT_NUMBER}@cloudservices.gserviceaccount.com).
# Utilise `google_project_iam_member` (non-autoritaire) pour coexister avec les
# autres attributions IAM de la plateforme.

resource "google_project_iam_member" "tf_logging_admin" {
  project = var.project_id
  role    = "roles/logging.admin"
  member  = "serviceAccount:${data.google_project.current.number}@cloudservices.gserviceaccount.com"
}

resource "google_project_iam_member" "tf_monitoring_alert_editor" {
  project = var.project_id
  role    = "roles/monitoring.alertPolicyEditor"
  member  = "serviceAccount:${data.google_project.current.number}@cloudservices.gserviceaccount.com"
}

resource "google_project_iam_member" "tf_monitoring_channel_editor" {
  project = var.project_id
  role    = "roles/monitoring.notificationChannelEditor"
  member  = "serviceAccount:${data.google_project.current.number}@cloudservices.gserviceaccount.com"
}

# Data source pour récupérer le numéro de projet GCP (utilisé dans les IAM members)
data "google_project" "current" {
  project_id = var.project_id
}

# ==============================================================================
# 2. Canaux de notification email (un canal par adresse dans sre_alert_emails)
# ==============================================================================
# Crée un google_monitoring_notification_channel de type "email" par entrée dans
# la variable sre_alert_emails (définie dans envs/*.yaml et passée par manage_env.py).
# Utilise for_each pour rester idempotent même si la liste évolue.

resource "google_monitoring_notification_channel" "sre_email" {
  for_each = toset(var.sre_alert_emails)

  project      = var.project_id
  display_name = "SRE Alert — ${each.value}"
  type         = "email"

  labels = {
    email_address = each.value
  }

  force_delete = false
}

# ==============================================================================
# 2b. Canal de notification Google Chat (webhook)
# ==============================================================================
# Cloud Monitoring supporte le type "webhook_tokenauth" pour Google Chat.
# Le canal est partagé par toutes les alert policies (SRE triage + SLO burn rate).

resource "google_monitoring_notification_channel" "sre_chat" {
  project      = var.project_id
  display_name = "SRE Google Chat — ${terraform.workspace}"
  type         = "webhook_tokenauth"

  labels = {
    url = var.sre_chat_webhook_url
  }

  force_delete = false
}

# ==============================================================================
# 3. Métrique basée sur les journaux (Log-based Metric)
# ==============================================================================
# Compte le nombre d'occurrences de l'événement "[SRE-WARMUP] SERVICE DEGRADED"
# dans les logs d'exécution des conteneurs Cloud Run.

resource "google_logging_metric" "warmup_degraded_metric" {
  project = var.project_id
  name    = "sre/warmup_degraded_count"
  filter  = "resource.type=\"cloud_run_revision\" AND textPayload =~ \"\\[SRE-WARMUP\\] SERVICE DEGRADED.*\""

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    display_name = "SRE - Degraded Warm-up failures"
    unit         = "1"
  }
}

# ==============================================================================
# 4. Politique d'alerte (Alert Policy)
# ==============================================================================
# Déclenche un incident SRE si plus de 2 échecs de warm-up (mode dégradé)
# surviennent sur une période glissante de 5 minutes.
# Notifie tous les canaux email déclarés dans sre_alert_emails.

resource "google_monitoring_alert_policy" "warmup_degraded_alert" {
  project      = var.project_id
  display_name = "SRE - Alert - Cold Starts / Degraded Warm-up Persistent"
  combiner     = "OR"

  # Lie tous les canaux de notification créés ci-dessus
  notification_channels = concat(
    [for ch in google_monitoring_notification_channel.sre_email : ch.name],
    [google_monitoring_notification_channel.sre_chat.name]
  )

  conditions {
    display_name = "Degraded Warm-up failures count > 2 in 5m"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.warmup_degraded_metric.name}\" AND resource.type=\"cloud_run_revision\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2

      trigger {
        count = 1
      }

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  documentation {
    content   = <<-EOT
      ## Alerte Critique : Échec persistant du Warm-up automatique Cloud Run

      Le pré-chauffage des conteneurs après connexion de l'utilisateur a échoué à plusieurs reprises et la console a dû s'ouvrir en **mode dégradé**.

      ### Impact Utilisateur
      Les utilisateurs ont un accès fonctionnel mais certains services secondaires (ex: competencies-api, items-api, ou prompts-api) peuvent subir des ralentissements, des erreurs d'interactions ou des timeouts lors du premier appel.

      ### Diagnostic & Remédiation SRE
      1. Accédez à la console **GCP Logging** et recherchez l'origine exacte :
         ```sql
         resource.type="cloud_run_revision"
         textPayload =~ "\[SRE-WARMUP\] SERVICE DEGRADED"
         ```
      2. Identifiez le service en échec mentionné dans le log (ex: `competencies-api`).
      3. Inspectez les temps de démarrage à froid de ce conteneur ainsi que l'état d'authentification AlloyDB IAM (qui peut prendre jusqu'à 15s sous forte charge).
      4. Si nécessaire, augmentez temporairement les instances minimales via `manage_env.py` ou ajustez les timeouts de connexion.
    EOT
    mime_type = "text/markdown"
  }

  depends_on = [
    google_logging_metric.warmup_degraded_metric,
    google_project_iam_member.tf_logging_admin,
    google_project_iam_member.tf_monitoring_alert_editor,
    google_project_iam_member.tf_monitoring_channel_editor,
  ]
}

# ==============================================================================
# 5. Log-based Metric — SRE Triage Critical
# ==============================================================================
# Compte les logs [SRE-TRIAGE-CRITICAL] émis par sre_triage.py dans agent_ops_api.
# Ces logs sont produits automatiquement toutes les 2h par le Cloud Scheduler
# quand l'Agent Ops détecte un 🔴 incident critique (seuil 5xx dépassé).

resource "google_logging_metric" "sre_triage_critical_metric" {
  project = var.project_id
  name    = "sre/triage_critical_count"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    labels."run.googleapis.com/service_name"=~"agent-ops-api-.*"
    jsonPayload.message=~"\[SRE-TRIAGE-CRITICAL\]"
  EOT

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    display_name = "SRE - Triage Agent Ops — Incidents Critiques"
    unit         = "1"

    labels {
      key         = "sre_severity"
      value_type  = "STRING"
      description = "Sévérité du rapport SRE (CRITICAL)"
    }
  }

  label_extractors = {
    "sre_severity" = "EXTRACT(jsonPayload.sre_severity)"
  }
}

# ==============================================================================
# 6. Alert Policy — SRE Triage Critical
# ==============================================================================
# Déclenche une alerte dès le 1er [SRE-TRIAGE-CRITICAL] détecté sur 5 minutes.
# Notifie tous les canaux email définis dans var.sre_alert_emails.

resource "google_monitoring_alert_policy" "sre_triage_critical_alert" {
  project      = var.project_id
  display_name = "SRE - Alert - Triage Agent Ops : Incident Critique Détecté"
  combiner     = "OR"

  notification_channels = concat(
    [for ch in google_monitoring_notification_channel.sre_email : ch.name],
    [google_monitoring_notification_channel.sre_chat.name]
  )

  conditions {
    display_name = "SRE Triage CRITICAL ≥ 1 occurrence in 5m"
    condition_threshold {
      filter = join(" AND ", [
        "metric.type=\"logging.googleapis.com/user/${google_logging_metric.sre_triage_critical_metric.name}\"",
        "resource.type=\"cloud_run_revision\"",
      ])
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      trigger {
        count = 1
      }

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  documentation {
    content   = <<-EOT
      ## 🔴 Alerte SRE : Incident Critique Détecté par l'Agent Ops

      L'Agent de Triage SRE (déclenché toutes les 2h par Cloud Scheduler) a détecté
      **au moins un service en état critique** sur la plateforme Zenika.

      ### Contexte
      - **Trigger** : `[SRE-TRIAGE-CRITICAL]` émis par `agent_ops_api` / `sre_triage.py`
      - **Fenêtre analysée** : dernières 2 heures
      - **Seuil 5xx** : ≥ 5 erreurs HTTP 5xx sur la fenêtre

      ### Consulter le rapport complet
      Ouvrez Cloud Logging Explorer avec ce filtre :
      ```
      resource.type="cloud_run_revision"
      labels."run.googleapis.com/service_name"=~"agent-ops-api-.*"
      jsonPayload.message=~"\[SRE-TRIAGE-CRITICAL\]"
      ```
      → Le champ `jsonPayload.sre_report_excerpt` contient les 500 premiers caractères du rapport Markdown.

      ### Diagnostic & Remédiation
      1. Lire `sre_report_excerpt` dans le log pour identifier le(s) service(s) critique(s)
      2. Consulter directement Cloud Logging pour les erreurs du service concerné
      3. Vérifier les traces Cloud Trace pour les latences anormales
      4. Déclencher un triage manuel via `/sre-report` si nécessaire
      5. Escalader à l'astreinte si le service est inaccessible (HTTP 503)
    EOT
    mime_type = "text/markdown"
  }

  depends_on = [
    google_logging_metric.sre_triage_critical_metric,
    google_monitoring_notification_channel.sre_email,
    google_monitoring_notification_channel.sre_chat,
    google_project_iam_member.tf_logging_admin,
    google_project_iam_member.tf_monitoring_alert_editor,
    google_project_iam_member.tf_monitoring_channel_editor,
  ]
}
