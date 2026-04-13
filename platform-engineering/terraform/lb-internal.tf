# =========================================================
# INTERNAL REGIONAL HTTP L7 LOAD BALANCER
# =========================================================

resource "google_compute_region_backend_service" "internal_mcp_backend" {
  for_each              = toset(local.mcp_services)
  name                  = "backend-internal-${each.value}-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"

  backend {
    group           = google_compute_region_network_endpoint_group.mcp_neg[each.key].id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_compute_region_backend_service" "internal_prompts_backend" {
  name                  = "backend-internal-prompts-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"

  backend {
    group           = google_compute_region_network_endpoint_group.prompts_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_compute_region_backend_service" "internal_drive_backend" {
  name                  = "backend-internal-drive-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"

  backend {
    group           = google_compute_region_network_endpoint_group.drive_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_compute_region_backend_service" "internal_market_backend" {
  name                  = "backend-internal-market-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"

  backend {
    group           = google_compute_region_network_endpoint_group.market_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_compute_region_url_map" "internal_url_map" {
  name            = "lb-internal-${terraform.workspace}"
  region          = var.region
  default_service = google_compute_region_backend_service.internal_mcp_backend["users"].id

  host_rule {
    hosts        = ["api.internal.zenika"]
    path_matcher = "internal-routes"
  }

  path_matcher {
    name            = "internal-routes"
    default_service = google_compute_region_backend_service.internal_mcp_backend["users"].id

    route_rules {
      priority = 20
      match_rules { prefix_match = "/auth/" }
      service = google_compute_region_backend_service.internal_mcp_backend["users"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/users/"
        }
      }
    }

    route_rules {
      priority = 30
      match_rules { prefix_match = "/users-api/" }
      service = google_compute_region_backend_service.internal_mcp_backend["users"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 40
      match_rules { prefix_match = "/items-api/" }
      service = google_compute_region_backend_service.internal_mcp_backend["items"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 50
      match_rules { prefix_match = "/prompts-api/" }
      service = google_compute_region_backend_service.internal_prompts_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 60
      match_rules { prefix_match = "/comp-api/" }
      service = google_compute_region_backend_service.internal_mcp_backend["competencies"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 70
      match_rules { prefix_match = "/cv-api/" }
      service = google_compute_region_backend_service.internal_mcp_backend["cv"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 75
      match_rules { prefix_match = "/missions-api/" }
      service = google_compute_region_backend_service.internal_mcp_backend["missions"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 80
      match_rules { prefix_match = "/drive-api/" }
      service = google_compute_region_backend_service.internal_drive_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 90
      match_rules { prefix_match = "/market-mcp/" }
      service = google_compute_region_backend_service.internal_market_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
  }
}

resource "google_compute_region_target_http_proxy" "internal_proxy" {
  name    = "ilb-proxy-${terraform.workspace}"
  region  = var.region
  url_map = google_compute_region_url_map.internal_url_map.id
}

resource "google_compute_forwarding_rule" "internal_rule" {
  name                  = "ilb-forwarding-rule-${terraform.workspace}"
  region                = var.region
  load_balancing_scheme = "INTERNAL_MANAGED"
  port_range            = "80"
  target                = google_compute_region_target_http_proxy.internal_proxy.id
  network               = google_compute_network.main.id
  subnetwork            = google_compute_subnetwork.main.id
  network_tier          = "PREMIUM"
  depends_on            = [google_compute_subnetwork.proxy_only]
}
