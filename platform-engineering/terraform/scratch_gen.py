import os

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code/platform-engineering/terraform"

def generate_cr_mcp_tf(service_key):
    # Base variables
    env_vars = f"""
      env {{
        name  = "DATABASE_URL"
        value = "postgresql://${{replace(google_service_account.cr_sa["{service_key}"].email, ".gserviceaccount.com", "")}}@${{google_alloydb_instance.primary.ip_address}}:5432/{service_key}"
      }}
      env {{
        name  = "ROOT_PATH"
        value = "{"/comp-api" if service_key == "competencies" else f"/{service_key}-api"}"
      }}
      env {{
        name  = "USE_IAM_AUTH"
        value = "true"
      }}
      env {{
        name  = "ALLOYDB_INSTANCE_URI"
        value = "projects/${{var.project_id}}/locations/${{var.region}}/clusters/${{google_alloydb_cluster.main.cluster_id}}/instances/${{google_alloydb_instance.primary.instance_id}}"
      }}
      env {{
        name  = "REDIS_URL"
        value = "redis://${{google_redis_instance.cache.host}}:${{google_redis_instance.cache.port}}/0"
      }}
      env {{
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }}
      env {{
        name  = "APP_VERSION"
        value = var.{service_key}_api_version
      }}
      env {{
        name = "SECRET_KEY"
        value_source {{
          secret_key_ref {{
            secret  = data.google_secret_manager_secret.jwt_secret.secret_id
            version = "latest"
          }}
        }}
      }}
"""

    if service_key == "users":
        env_vars += f"""
      env {{
        name = "DEFAULT_ADMIN_PASSWORD"
        value_source {{
          secret_key_ref {{
            secret  = google_secret_manager_secret.admin_password.secret_id
            version = "latest"
          }}
        }}
      }}
      env {{
        name = "GOOGLE_SECRET_ID"
        value_source {{
          secret_key_ref {{
            secret  = data.google_secret_manager_secret.google_secret_id.secret_id
            version = "latest"
          }}
        }}
      }}
      env {{
        name = "GOOGLE_SECRET_KEY"
        value_source {{
          secret_key_ref {{
            secret  = data.google_secret_manager_secret.google_secret_key.secret_id
            version = "latest"
          }}
        }}
      }}
      env {{
        name  = "CV_API_URL"
        value = "http://api.internal.zenika/cv-api/"
      }}
      env {{
        name  = "ITEMS_API_URL"
        value = "http://api.internal.zenika/items-api/"
      }}
      env {{
        name  = "COMPETENCIES_API_URL"
        value = "http://api.internal.zenika/comp-api/"
      }}
      env {{
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }}
      env {{
        name  = "USER_EVENTS_TOPIC"
        value = google_pubsub_topic.user_events.name
      }}"""

    if service_key in ["cv", "competencies", "missions"]:
        env_vars += f"""
      env {{
        name  = "USERS_API_URL"
        value = "http://api.internal.zenika/users-api/"
      }}"""

    if service_key in ["cv", "missions"]:
        env_vars += f"""
      env {{
        name = "GOOGLE_API_KEY"
        value_source {{
          secret_key_ref {{
            secret  = data.google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }}
        }}
      }}
      env {{
        name  = "PROMPTS_API_URL"
        value = "http://api.internal.zenika/prompts-api/"
      }}
      env {{
        name  = "COMPETENCIES_API_URL"
        value = "http://api.internal.zenika/comp-api/"
      }}
      env {{
        name  = "ITEMS_API_URL"
        value = "http://api.internal.zenika/items-api/"
      }}
      env {{
        name  = "DRIVE_API_URL"
        value = "http://api.internal.zenika/drive-api/"
      }}
      env {{
        name  = "MARKET_MCP_URL"
        value = "http://api.internal.zenika/market-mcp/"
      }}"""

    if service_key == "missions":
        env_vars += f"""
      env {{
        name  = "CV_API_URL"
        value = "http://api.internal.zenika/cv-api/"
      }}"""

    template = f"""resource "google_cloud_run_v2_service" "{service_key}_api" {{
  name     = "{service_key}-api-${{terraform.workspace}}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {{
    service_account = google_service_account.cr_sa["{service_key}"].email

    scaling {{
      min_instance_count = var.cloudrun_min_instances
      max_instance_count = var.cloudrun_max_instances
    }}

    vpc_access {{
      network_interfaces {{
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.main.id
        tags       = ["cr-egress"]
      }}
    }}

    # Conteneur principal (API)
    containers {{
      name    = "api"
      image   = var.image_{service_key}
      command = ["python"]
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
      ports {{
        container_port = 8080
      }}
      dynamic "startup_probe" {{
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {{
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 5
          failure_threshold     = 20
          http_get {{
            path = "/health"
          }}
        }}
      }}
      dynamic "liveness_probe" {{
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {{
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {{
            path = "/health"
          }}
        }}
      }}
      resources {{
        limits = {{
          memory = "1024Mi"
        }}
      }}
{env_vars}
    }}

    # Conteneur Sidecar (MCP)
    containers {{
      name    = "mcp"
      image   = var.image_{service_key}
      command = ["python"]
      args    = ["-m", "uvicorn", "mcp_app:app", "--host", "0.0.0.0", "--port", "8081", "--no-server-header"]
      dynamic "startup_probe" {{
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {{
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 5
          failure_threshold     = 20
          http_get {{
            path = "/health"
            port = 8081
          }}
        }}
      }}
      dynamic "liveness_probe" {{
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {{
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {{
            path = "/health"
            port = 8081
          }}
        }}
      }}
      resources {{
        limits = {{
          memory = "512Mi"
        }}
      }}

      env {{
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }}
      env {{
        name  = "PORT"
        value = "8081"
      }}
      env {{
        name  = "APP_VERSION"
        value = var.{service_key}_api_version
      }}
      env {{
        name  = "{service_key.upper()}_API_URL"
        value = "http://localhost:8080"
      }}
    }}
  }}

  lifecycle {{
    ignore_changes = [
      template[0].containers[0].resources[0].limits["cpu"],
      template[0].containers[1].resources[0].limits["cpu"]
    ]
  }}

  depends_on = [
    time_sleep.wait_for_iam_propagation,
    null_resource.run_db_migrations_job
  ]
}}
"""
    with open(os.path.join(base_dir, f"cr_{service_key}.tf"), "w") as f:
        f.write(template)

for svc in ["users", "items", "competencies", "cv", "missions"]:
    generate_cr_mcp_tf(svc)

print("Generated MCP files.")
