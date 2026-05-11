# 🚨 Rapport d'Erreur Sanity Check (pour Antigravity)

> **Directives pour l'Agent Antigravity :**
> Analyse ces erreurs, cherche les causes probables et propose une réparation.
> 🔎 **IMPORTANT** : Pense à rechercher les logs pertinents directement dans GCP pour le projet `prod-ia-staffing` via les outils MCP.
> Une fois résolues, utilise la CLI Antigravity Memory pour logguer la solution.

## Erreur interceptée à 2026-05-11 12:54:27 UTC

- **Contexte** : Exécution Terraform / Déploiement infra
- **Projet GCP** : `prod-ia-staffing`
- **Tags** : `terraform, deployment, infrastructure`
- **Détails de l'erreur** :

```text
[!] Error executing: terraform plan
```

---

## Erreur interceptée à 2026-05-11 13:01:17 UTC

- **Contexte** : Sanity Check 5/5 : API Microservices
- **Projet GCP** : `prod-ia-staffing`
- **Tags** : `routing, sanity-check, exception`
- **Détails de l'erreur** :

```text
FAIL (ConnectionResetError: [Errno 54] Connection reset by peer) sur /api/agent-ops/spec
```

---

## Erreur interceptée à 2026-05-11 13:01:17 UTC

- **Contexte** : Sanity Check 5/5 : API Microservices
- **Projet GCP** : `prod-ia-staffing`
- **Tags** : `routing, sanity-check, exception`
- **Détails de l'erreur** :

```text
FAIL (ConnectionResetError: [Errno 54] Connection reset by peer) sur /api/items/spec
```

---

## Erreur interceptée à 2026-05-11 13:01:17 UTC

- **Contexte** : Sanity Check 5/5 : API Microservices
- **Projet GCP** : `prod-ia-staffing`
- **Tags** : `routing, sanity-check, exception`
- **Détails de l'erreur** :

```text
FAIL (ConnectionResetError: [Errno 54] Connection reset by peer) sur /api/agent-ops/health
```

---

## Erreur interceptée à 2026-05-11 13:01:17 UTC

- **Contexte** : Sanity Check 5/5 : API Microservices
- **Projet GCP** : `prod-ia-staffing`
- **Tags** : `routing, sanity-check, exception`
- **Détails de l'erreur** :

```text
FAIL (ConnectionResetError: [Errno 54] Connection reset by peer) sur /api/agent-ops/docs
```

---

## Erreur interceptée à 2026-05-11 13:01:17 UTC

- **Contexte** : Sanity Check 5/5 : API Microservices
- **Projet GCP** : `prod-ia-staffing`
- **Tags** : `routing, sanity-check, exception`
- **Détails de l'erreur** :

```text
FAIL (ConnectionResetError: [Errno 54] Connection reset by peer) sur /api/items/ready
```

---

## Erreur interceptée à 2026-05-11 13:01:43 UTC

- **Contexte** : Exécution Terraform / Déploiement infra
- **Projet GCP** : `prod-ia-staffing`
- **Tags** : `terraform, deployment, infrastructure`
- **Détails de l'erreur** :

```text
5 Sanity Checks failed. Consultez le rapport antigravity_sanity_error.md
```

---

