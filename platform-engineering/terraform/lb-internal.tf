# =========================================================
# INTERNAL REGIONAL HTTP L7 LOAD BALANCER
# =========================================================













resource "google_compute_region_url_map" "internal_url_map" {
  name            = "lb-internal-${terraform.workspace}"
  region          = var.region
  default_service = google_compute_region_backend_service.users_internal_backend.id

  host_rule {
    hosts        = ["api.internal.zenika"]
    path_matcher = "internal-routes"
  }

  path_matcher {
    name            = "internal-routes"
    default_service = google_compute_region_backend_service.users_internal_backend.id

    route_rules {
      priority = 10
      match_rules { prefix_match = "/api/" }
      service = google_compute_region_backend_service.agent_router_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 20
      match_rules { prefix_match = "/auth/" }
      service = google_compute_region_backend_service.users_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/users/"
        }
      }
    }

    route_rules {
      priority = 30
      match_rules { prefix_match = "/users-api/" }
      service = google_compute_region_backend_service.users_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 40
      match_rules { prefix_match = "/items-api/" }
      service = google_compute_region_backend_service.items_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 50
      match_rules { prefix_match = "/prompts-api/" }
      service = google_compute_region_backend_service.prompts_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 60
      match_rules { prefix_match = "/comp-api/" }
      service = google_compute_region_backend_service.competencies_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 70
      match_rules { prefix_match = "/cv-api/" }
      service = google_compute_region_backend_service.cv_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 75
      match_rules { prefix_match = "/missions-api/" }
      service = google_compute_region_backend_service.missions_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 80
      match_rules { prefix_match = "/drive-api/" }
      service = google_compute_region_backend_service.drive_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 90
      match_rules { prefix_match = "/market-mcp/" }
      service = google_compute_region_backend_service.market_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 100
      match_rules { prefix_match = "/agent-hr-api/" }
      service = google_compute_region_backend_service.agent_hr_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 110
      match_rules { prefix_match = "/agent-ops-api/" }
      service = google_compute_region_backend_service.agent_ops_internal_backend.id
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
