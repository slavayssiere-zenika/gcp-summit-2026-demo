# Certificat SSL Managé
# Couvre le domaine principal de l'environnement + les domaines additionnels (ex: gen-skillz.znk.io)
resource "google_compute_managed_ssl_certificate" "default" {
  name = "ssl-${terraform.workspace}"
  managed {
    domains = concat(
      [
        "${terraform.workspace}.${var.base_domain}",
        "api.${terraform.workspace}.${var.base_domain}"
      ],
      # Domaines additionnels (ex: gen-skillz.znk.io en prd)
      [for d in var.extra_domains : trim(d.dns_name, ".")]
    )
  }

  lifecycle {
    prevent_destroy = true
  }
}

# =========================================================
# Serverless NEGs pour connecter le LB aux Cloud Runs
# =========================================================
















resource "google_compute_backend_bucket" "frontend" {
  name        = "backend-frontend-${terraform.workspace}"
  bucket_name = google_storage_bucket.frontend.name
  enable_cdn  = true
}

# =========================================================
# URL Map avec routing et réécriture inspiré du Nginx
# =========================================================
resource "google_compute_url_map" "default" {
  name            = "lb-${terraform.workspace}"
  description     = "URL Map split between frontend and API"
  default_service = google_compute_backend_bucket.frontend.id

  # Host Rule unifiée pour l'API et le Frontend (domaine principal)
  host_rule {
    hosts = [
      "api.${terraform.workspace}.${var.base_domain}",
      "${terraform.workspace}.${var.base_domain}"
    ]
    path_matcher = "unified-routes"
  }

  # Host Rules pour les domaines additionnels (ex: gen-skillz.znk.io)
  # Chaque domaine extra pointe vers le même path_matcher que le domaine principal
  dynamic "host_rule" {
    for_each = var.extra_domains
    content {
      hosts        = [trim(host_rule.value.dns_name, ".")]
      path_matcher = "unified-routes"
    }
  }

  path_matcher {
    name = "unified-routes"
    # Tout ce qui n'est pas explicitement une route d'API retournera le frontend (GCS)
    default_service = google_compute_backend_bucket.frontend.id

    route_rules {
      priority = 5
      match_rules { prefix_match = "/api/market/" }
      service = google_compute_backend_service.market_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/api/"
        }
      }
    }

    route_rules {
      priority = 6
      match_rules { prefix_match = "/mcp/market/" }
      service = google_compute_backend_service.market_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    # ── Push Pub/Sub endpoints (préfixe direct, sans /api/) ─────────────────
    # Pub/Sub pousse vers /cv-api/pubsub/import-cv et /cv-api/pubsub/user-events
    # Ces routes DOIVENT être déclarées avant la règle générique /api/ (prio 20)
    route_rules {
      priority = 8
      match_rules { prefix_match = "/cv-api/" }
      service = google_compute_backend_service.cv_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 9
      match_rules { prefix_match = "/items-api/" }
      service = google_compute_backend_service.items_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 10
      match_rules { prefix_match = "/api/users/" }
      service = google_compute_backend_service.users_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 11
      match_rules { prefix_match = "/api/items/" }
      service = google_compute_backend_service.items_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 12
      match_rules { prefix_match = "/api/prompts/" }
      service = google_compute_backend_service.prompts_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 13
      match_rules { prefix_match = "/api/competencies/" }
      service = google_compute_backend_service.competencies_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 14
      match_rules { prefix_match = "/api/cv/" }
      service = google_compute_backend_service.cv_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 15
      match_rules { prefix_match = "/api/missions/" }
      service = google_compute_backend_service.missions_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 16
      match_rules { prefix_match = "/api/drive/" }
      service = google_compute_backend_service.drive_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 17
      match_rules { prefix_match = "/api/agent-hr/" }
      service = google_compute_backend_service.agent_hr_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 18
      match_rules { prefix_match = "/api/agent-ops/" }
      service = google_compute_backend_service.agent_ops_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 19
      match_rules { prefix_match = "/api/agent-missions/" }
      service = google_compute_backend_service.agent_missions_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 20
      match_rules { prefix_match = "/api/" }
      service = google_compute_backend_service.agent_router_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 21
      match_rules { prefix_match = "/mcp/" }
      service = google_compute_backend_service.agent_router_backend.id
    }

    route_rules {
      priority = 30
      match_rules { prefix_match = "/auth/" }
      service = google_compute_backend_service.users_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    # Compatibilité pour les anciens paths (Legacy)
    route_rules {
      priority = 35
      match_rules { prefix_match = "/market-mcp/" }
      service = google_compute_backend_service.market_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 36
      match_rules { prefix_match = "/monitoring-mcp/" }
      service = google_compute_backend_service.monitoring_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }



    # SPA routing for all frontend views to avoid 404s on direct navigation or refresh
    # We rewrite these known frontend paths to / so that GCS serves index.html
    route_rules {
      priority = 40
      match_rules { prefix_match = "/admin" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 41
      match_rules { prefix_match = "/login" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 42
      match_rules { prefix_match = "/registry" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 43
      match_rules { prefix_match = "/profile" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 44
      match_rules { prefix_match = "/user" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 45
      match_rules { prefix_match = "/competencies" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 46
      match_rules { prefix_match = "/specs" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 47
      match_rules { prefix_match = "/import-cv" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 48
      match_rules { prefix_match = "/help" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 49
      match_rules { prefix_match = "/infrastructure" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 50
      match_rules { prefix_match = "/aiops" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
    route_rules {
      priority = 51
      match_rules { prefix_match = "/missions" }
      service = google_compute_backend_bucket.frontend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
  }
}

# =========================================================
# Proxies et Forwarding Rules IP Globale
# =========================================================
resource "google_compute_target_https_proxy" "default" {
  name             = "https-proxy-${terraform.workspace}"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_managed_ssl_certificate.default.id]
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "http-proxy-${terraform.workspace}"
  url_map = google_compute_url_map.redirect.id
}

# Redirection HTTP vers HTTPS automatique
resource "google_compute_url_map" "redirect" {
  name = "http-redirect-${terraform.workspace}"
  default_url_redirect {
    https_redirect         = true
    strip_query            = false
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
  }
}

resource "google_compute_global_address" "lb_ip" {
  name = "lb-ip-${terraform.workspace}"
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "https-rule-${terraform.workspace}"
  target                = google_compute_target_https_proxy.default.id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "http-rule-${terraform.workspace}"
  target                = google_compute_target_http_proxy.redirect.id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# Ajout d'un enregistrement au DNS
resource "google_dns_record_set" "a" {
  name         = google_dns_managed_zone.env_zone.dns_name
  managed_zone = google_dns_managed_zone.env_zone.name
  type         = "A"
  ttl          = 300

  rrdatas = [google_compute_global_address.lb_ip.address]

  lifecycle {
    prevent_destroy = true
  }
}

# Enregistrement DNS supplémentaire pour le routage de l'API (api.env.domain)
resource "google_dns_record_set" "api_a" {
  name         = "api.${google_dns_managed_zone.env_zone.dns_name}"
  managed_zone = google_dns_managed_zone.env_zone.name
  type         = "A"
  ttl          = 300

  rrdatas = [google_compute_global_address.lb_ip.address]

  lifecycle {
    prevent_destroy = true
  }
}

# Note: L'import de cette ressource est géré impérativement par manage_env.py
# via resource_exists_in_gcp("ssl_cert") + import_persistent_resource() pour être conditionnel.
