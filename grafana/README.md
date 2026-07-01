# Grafana

Tableau de bord d'observabilité pour la stack GCP.

## Variables d'environnement (build-time)
- Aucune variable build-time spécifique requise.

## Périmètre d'intervention agent
| Fichier | Agent peut modifier ? |
|---|---|
| `dashboards/*.json` | ✅ Oui — via l'UI Grafana puis export |
| `provisioning/...` | ✅ Oui |
| `Dockerfile` | ⚠️ Validation user requise |

## MCP tools exposés
_Aucun tool MCP exposé._

## Gotchas connus
- Ce service est déployé via Cloud Run de la même manière que les APIs backend.
- Les identifiants de connexion (admin/admin par défaut ou via Secret Manager) doivent être gérés avec précaution.

## Dernière modification
2026-06-24 — v0.0.6 — Ajout initial du service Grafana
