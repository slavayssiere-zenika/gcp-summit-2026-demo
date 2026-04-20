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
      priority = 5
      match_rules { prefix_match = "/api/market/" }
      service = google_compute_region_backend_service.market_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 6
      match_rules { prefix_match = "/mcp/market/" }
      service = google_compute_region_backend_service.market_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 10
      match_rules { prefix_match = "/api/users/" }
      service = google_compute_region_backend_service.users_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 11
      match_rules { prefix_match = "/api/items/" }
      service = google_compute_region_backend_service.items_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 12
      match_rules { prefix_match = "/api/prompts/" }
      service = google_compute_region_backend_service.prompts_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 13
      match_rules { prefix_match = "/api/competencies/" }
      service = google_compute_region_backend_service.competencies_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 14
      match_rules { prefix_match = "/api/cv/" }
      service = google_compute_region_backend_service.cv_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 15
      match_rules { prefix_match = "/api/missions/" }
      service = google_compute_region_backend_service.missions_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 16
      match_rules { prefix_match = "/api/drive/" }
      service = google_compute_region_backend_service.drive_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 17
      match_rules { prefix_match = "/api/agent-hr/" }
      service = google_compute_region_backend_service.agent_hr_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 18
      match_rules { prefix_match = "/api/agent-ops/" }
      service = google_compute_region_backend_service.agent_ops_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 19
      match_rules { prefix_match = "/api/agent-missions/" }
      service = google_compute_region_backend_service.agent_missions_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 20
      match_rules { prefix_match = "/api/" }
      service = google_compute_region_backend_service.agent_router_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 30
      match_rules { prefix_match = "/auth/" }
      service = google_compute_region_backend_service.users_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/users/"
        }
      }
    }

    # Compatibilité Legacy interne
    route_rules {
      priority = 200
      match_rules { prefix_match = "/market-mcp/" }
      service = google_compute_region_backend_service.market_internal_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 201
      match_rules { prefix_match = "/monitoring-mcp/" }
      service = google_compute_region_backend_service.monitoring_internal_backend.id
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
