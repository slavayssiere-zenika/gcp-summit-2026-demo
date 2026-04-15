# ==============================================================
# GCP Pub/Sub Infrastructure for User Events (Phase 3)
# ==============================================================

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
    push_endpoint = "https://api.${terraform.workspace}.${var.base_domain}/cv-api/pubsub/user-events"

    # OIDC authentication (Zero-Trust)
    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
      audience              = "https://api.${terraform.workspace}.${var.base_domain}/cv-api/pubsub/user-events"
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
    push_endpoint = "https://api.${terraform.workspace}.${var.base_domain}/items-api/pubsub/user-events"

    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
      audience              = "https://api.${terraform.workspace}.${var.base_domain}/items-api/pubsub/user-events"
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
