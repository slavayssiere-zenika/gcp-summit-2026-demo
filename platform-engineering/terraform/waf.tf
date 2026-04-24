# Stratégie de sécurité Cloud Armor protégeant le Load Balancer
resource "google_compute_security_policy" "waf" {
  name        = "waf-${terraform.workspace}"
  description = "WAF policy for ${terraform.workspace} level protection"

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }

  # ── Couche 1 : Threat Intelligence ────────────────────────────────────────────
  # DÉSACTIVÉE : evaluateThreatIntelligence() nécessite Cloud Armor Enterprise (tier payant).
  # Réactiver en PRD si le tier Enterprise est souscrit :
  #   rule { action = "deny(403)" priority = 100
  #     match { expr { expression = "evaluateThreatIntelligence('iplist-known-malicious-ips')" } }
  #   }
  #   rule { action = "deny(403)" priority = 101
  #     match { expr { expression = "evaluateThreatIntelligence('iplist-tor-exit-nodes')" } }
  #   }

  # ── Couche 0 : Exceptions — routes légitimes exemptées des règles OWASP ────────
  # Ces routes reçoivent des payloads JSON légitimes (login, création de ressources)
  # qui déclenchent faussement les signatures SQLi / XSS / scannerdetection.
  # La règle allow ici est UNIQUEMENT sur des paths préfixés stricts — pas un allow-all.
  # Le rate-limit (priorité 2000) s'applique toujours sur ces routes.
  rule {
    action   = "allow"
    priority = 100
    match {
      expr {
        # RE2 regex (syntaxe Cloud Armor CEL) — groupe NON-capturant (?:...) obligatoire.
        # Les groupes capturants (...) sont rejetés avec "Capture Groups are not allowed".
        # Couvre : /auth/, /api/, /monitoring-mcp/, /cv-api/, /items-api/, /drive-api/
        # CRITIQUE pour Pub/Sub : les push vers /cv-api/pubsub/import-cv arrivent avec
        # des payloads base64 qui déclenchent faussement les règles OWASP → 403 silencieux.
        expression = "request.path.matches('^/(?:auth|api|mcp|monitoring-mcp|analytics-mcp|cv-api|items-api|drive-api)/.*')"
      }
    }
    description = "Allow legitimate API & Pub/Sub push paths — exempted from OWASP signatures (rate-limit still applies)"
  }

  # ── Couche 2 : Règles OWASP signature-based ──────────────────────────────────
  # Ces règles DOIVENT être évaluées AVANT le rate-limit pour bloquer
  # les payloads malveillants qui restent sous le seuil de rate-limit.
  rule {
    action   = "deny(403)"
    priority = 500
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "OWASP SQLi protection"
  }

  rule {
    action   = "deny(403)"
    priority = 501
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "OWASP XSS protection"
  }

  rule {
    action   = "deny(403)"
    priority = 502
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('lfi-v33-stable')"
      }
    }
    description = "OWASP LFI protection"
  }

  rule {
    action   = "deny(403)"
    priority = 503
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('rce-v33-stable')"
      }
    }
    description = "OWASP RCE protection"
  }

  rule {
    action   = "deny(403)"
    priority = 504
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('scannerdetection-v33-stable')"
      }
    }
    description = "OWASP Scanner Detection"
  }

  # ── Couche 3 : Rate Limiting DDoS ─────────────────────────────────────────────
  # APRÈS les règles OWASP : un payload légitime mais abusif est rate-limité,
  # mais un payload malveillant est déjà bloqué par les règles OWASP ci-dessus.
  rule {
    action   = "rate_based_ban"
    priority = 2000
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
    description = "Rate Limiting to protect backend services (après OWASP)"
  }

  # ── Couche 4 : Default Allow (catch-all) ──────────────────────────────────────
  rule {
    action   = "allow"
    priority = 2147483647 # Règle de base numéro maximum (catch-all)
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow — trafic légitime non capturé par les règles précédentes"
  }
}
