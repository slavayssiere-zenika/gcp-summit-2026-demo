# ==============================================================
# GCP Pub/Sub Infrastructure for User Events (Phase 3)
# ==============================================================

# ==============================================================
# GCP Pub/Sub Infrastructure for CV Ingestion Pipeline (Phase 4)
# ==============================================================

# Dead Letter Queue topic (messages after 5 failed deliveries)
# TTL : 14 jours — le scheduler horaire drainera bien avant expiration
resource "google_pubsub_topic" "cv_import_events_dead_letter" {
  name = "zenika-cv-import-events-dead-letter-${terraform.workspace}"

  message_retention_duration = "1209600s" # 14 jours (14 * 24 * 3600)

  labels = {
    environment = terraform.workspace
    managed_by  = "terraform"
  }
}

# Main CV import topic
# TTL : 7 jours — si drive_api est en panne, les messages survivent à un weekend
resource "google_pubsub_topic" "cv_import_events" {
  name = "zenika-cv-import-events-${terraform.workspace}"

  message_retention_duration = "604800s" # 7 jours (7 * 24 * 3600)

  labels = {
    environment = terraform.workspace
    managed_by  = "terraform"
  }
}

# Push Subscription — cv_api is the worker (OIDC Zero-Trust)
resource "google_pubsub_subscription" "cv_import_events_sub" {
  name  = "cv-import-events-sub-${terraform.workspace}"
  topic = google_pubsub_topic.cv_import_events.id

  # 10 minutes: covers Gemini extraction + competencies + missions HTTP calls
  ack_deadline_seconds = 600

  push_config {
    push_endpoint = "https://${terraform.workspace}.${var.base_domain}/cv-api/pubsub/import-cv"

    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
      audience              = "https://${terraform.workspace}.${var.base_domain}/cv-api/pubsub/import-cv"
    }
  }

  # Exponential backoff: 30s → 600s
  retry_policy {
    minimum_backoff = "30s"
    maximum_backoff = "600s"
  }

  # Dead Letter Queue after 5 failed delivery attempts
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.cv_import_events_dead_letter.id
    max_delivery_attempts = 5
  }

  depends_on = [google_service_account_iam_member.pubsub_token_creator]
}

# Allow drive_api SA to publish CV import events
resource "google_pubsub_topic_iam_member" "drive_cv_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.cv_import_events.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_service_account.drive_sa.email}"
}

# Allow pubsub_invoker SA to invoke cv_api Cloud Run
resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker_cv_import" {
  location = var.region
  name     = google_cloud_run_v2_service.cv_api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}

# Allow Pub/Sub to forward to DLQ
resource "google_pubsub_topic_iam_member" "pubsub_dlq_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.cv_import_events_dead_letter.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# Allow Pub/Sub system SA to subscribe to the source subscription (required for DLQ forwarding)
# Without this, GCP cannot forward dead-lettered messages to the DLQ topic
resource "google_pubsub_subscription_iam_member" "pubsub_dlq_subscriber" {
  project      = var.project_id
  subscription = google_pubsub_subscription.cv_import_events_sub.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# DLQ Subscription — conserve les messages dead-lettered pour analyse/monitoring
# TTL : 14 jours (aligné sur le topic DLQ)
resource "google_pubsub_subscription" "cv_import_events_dlq_sub" {
  name  = "cv-import-events-dlq-sub-${terraform.workspace}"
  topic = google_pubsub_topic.cv_import_events_dead_letter.id

  ack_deadline_seconds = 20

  # Aligne le TTL de la subscription sur celui du topic (14 jours)
  message_retention_duration = "1209600s" # 14 jours

  # Expiration de la subscription elle-même si inactive (28 jours > 14 jours TTL)
  expiration_policy {
    ttl = "2419200s" # 28 jours
  }

  labels = {
    environment = terraform.workspace
    managed_by  = "terraform"
  }
}



resource "google_pubsub_topic" "user_events" {
  name = "zenika-user-events-${terraform.workspace}"

  labels = {
    environment = terraform.workspace
    managed_by  = "terraform"
  }
}

# --------------------------------------------------------------
# Push Subscriptions for microservices
# --------------------------------------------------------------

# Service account used by Pub/Sub to push to Cloud Run (OIDC)
resource "google_service_account" "pubsub_invoker" {
  account_id   = "sa-pubsub-invoker-${terraform.workspace}"
  display_name = "Pub/Sub Invoker SA"
}

resource "google_pubsub_subscription" "cv_api_sub" {
  name  = "cv-api-user-events-sub-${terraform.workspace}"
  topic = google_pubsub_topic.user_events.id

  ack_deadline_seconds = 20

  push_config {
    # Pointing to the External HTTPS URL (required for public Pub/Sub push)
    push_endpoint = "https://${terraform.workspace}.${var.base_domain}/cv-api/pubsub/user-events"

    # OIDC authentication (Zero-Trust)
    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
      audience              = "https://${terraform.workspace}.${var.base_domain}/cv-api/pubsub/user-events"
    }
  }

  # Ensure IAM permissions are propagated before creating the subscription
  depends_on = [google_service_account_iam_member.pubsub_token_creator]
}

resource "google_pubsub_subscription" "items_api_sub" {
  name  = "items-api-user-events-sub-${terraform.workspace}"
  topic = google_pubsub_topic.user_events.id

  ack_deadline_seconds = 20

  push_config {
    push_endpoint = "https://${terraform.workspace}.${var.base_domain}/items-api/pubsub/user-events"

    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
      audience              = "https://${terraform.workspace}.${var.base_domain}/items-api/pubsub/user-events"
    }
  }

  depends_on = [google_service_account_iam_member.pubsub_token_creator]
}

# --------------------------------------------------------------
# IAM Permissions
# --------------------------------------------------------------

# Allow Users API to publish messages
resource "google_pubsub_topic_iam_member" "users_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.user_events.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.users_sa.email}"
}

# Allow Pub/Sub to invoke Cloud Run services (Push via OIDC)
resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker_cv" {
  location = var.region
  name     = google_cloud_run_v2_service.cv_api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}

resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker_items" {
  location = var.region
  name     = google_cloud_run_v2_service.items_api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}

# (Optional) Ensure the Pub/Sub technical service agent can create tokens
resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.pubsub_invoker.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

data "google_project" "project" {}
