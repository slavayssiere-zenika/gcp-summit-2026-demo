# Stratégie de sécurité Cloud Armor protégeant le Load Balancer
resource "google_compute_security_policy" "waf" {
  name        = "waf-${terraform.workspace}"
  description = "WAF policy for ${terraform.workspace} level protection"

  # Règle par défaut : autoriser (ou on peut refuser et whitelist, selon les besoins)
  # Pour un LB public, on laisse passer et on log, ou on applique des règles pré-packagées.
  rule {
    action   = "allow"
    priority = "2147483647" # Règle numéro de base (catch-all)
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow"
  }

  # Exemple de mitigation DDoS de base avec rate limiting (ajuster selon les besoins exacts de dev/prd)
  rule {
    action   = "rate_based_ban"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.waf_rate_limit
        interval_sec = 60
      }
      ban_duration_sec = 300
    }
    description = "Rate Limiting to protect backend services"
  }
}
