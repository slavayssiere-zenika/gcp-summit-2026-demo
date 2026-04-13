# Certificat SSL Managé
resource "google_compute_managed_ssl_certificate" "default" {
  name = "ssl-${terraform.workspace}"
  managed {
    domains = [
      "${terraform.workspace}.${var.base_domain}",
      "api.${terraform.workspace}.${var.base_domain}"
    ]
  }

  lifecycle {
    prevent_destroy = true
  }
}

# =========================================================
# Serverless NEGs pour connecter le LB aux Cloud Runs
# =========================================================
resource "google_compute_region_network_endpoint_group" "mcp_neg" {
  for_each              = toset(local.mcp_services)
  name                  = "neg-${each.key}-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.mcp_services[each.key].name
  }
}

resource "google_compute_region_network_endpoint_group" "prompts_neg" {
  name                  = "neg-prompts-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.prompts_api.name
  }
}

resource "google_compute_region_network_endpoint_group" "agent_neg" {
  name                  = "neg-agent-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.agent_api.name
  }
}

resource "google_compute_region_network_endpoint_group" "drive_neg" {
  name                  = "neg-drive-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.drive_api.name
  }
}

resource "google_compute_region_network_endpoint_group" "market_neg" {
  name                  = "neg-market-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.market_mcp.name
  }
}

# =========================================================
# Backend Services
# =========================================================
resource "google_compute_backend_service" "mcp_backend" {
  for_each              = toset(local.mcp_services)
  name                  = "backend-${each.key}-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id

  backend {
    group = google_compute_region_network_endpoint_group.mcp_neg[each.key].id
  }
}

resource "google_compute_backend_service" "prompts_backend" {
  name                  = "backend-prompts-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.prompts_neg.id
  }
}

resource "google_compute_backend_service" "agent_backend" {
  name                  = "backend-agent-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.agent_neg.id
  }
}

resource "google_compute_backend_service" "drive_backend" {
  name                  = "backend-drive-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.drive_neg.id
  }
}

resource "google_compute_backend_service" "market_backend" {
  name                  = "backend-market-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.market_neg.id
  }
}

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

  # Host Rule unifiée pour l'API et le Frontend
  host_rule {
    hosts = [
      "api.${terraform.workspace}.${var.base_domain}",
      "${terraform.workspace}.${var.base_domain}"
    ]
    path_matcher = "unified-routes"
  }

  path_matcher {
    name = "unified-routes"
    # Tout ce qui n'est pas explicitement une route d'API retournera le frontend (GCS)
    default_service = google_compute_backend_bucket.frontend.id

    route_rules {
      priority = 10
      match_rules { prefix_match = "/api/" }
      service = google_compute_backend_service.agent_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 20
      match_rules { prefix_match = "/auth/" }
      service = google_compute_backend_service.mcp_backend["users"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 30
      match_rules { prefix_match = "/users-api/" }
      service = google_compute_backend_service.mcp_backend["users"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 40
      match_rules { prefix_match = "/items-api/" }
      service = google_compute_backend_service.mcp_backend["items"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 50
      match_rules { prefix_match = "/prompts-api/" }
      service = google_compute_backend_service.prompts_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 60
      match_rules { prefix_match = "/comp-api/" }
      service = google_compute_backend_service.mcp_backend["competencies"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 70
      match_rules { prefix_match = "/cv-api/" }
      service = google_compute_backend_service.mcp_backend["cv"].id
    }
    route_rules {
      priority = 75
      match_rules { prefix_match = "/missions-api/" }
      service = google_compute_backend_service.mcp_backend["missions"].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 80
      match_rules { prefix_match = "/drive-api/" }
      service = google_compute_backend_service.drive_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 85
      match_rules { prefix_match = "/market-mcp/" }
      service = google_compute_backend_service.market_backend.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    # SPA routing for /admin to avoid 404s on refresh
    route_rules {
      priority = 90
      match_rules { prefix_match = "/admin" }
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

import {
  to = google_compute_managed_ssl_certificate.default
  id = "projects/${var.project_id}/global/sslCertificates/ssl-${terraform.workspace}"
}
