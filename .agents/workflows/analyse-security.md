---
description: Workflow d'audit automatisé de sécurité applicative, Terraform et bonnes pratiques Zero-Trust.
---

# Worfklow : Analyse de Sécurité Globale (/analyse-security)

// turbo-all

Ce workflow fournit une marche à suivre stricte pour auditer la posture de sécurité de la plateforme, depuis l'Infrastructure as Code (Terraform) jusqu'à la logique applicative (FastAPI, LLM). Lorsqu'un utilisateur exécute ce workflow, l'Agent DOIT exécuter les vérifications suivantes de manière autonome.

## Étape 0 : Lecture des README.md

Avant tout audit de code, lire le fichier `README.md` de chaque service ciblé. C'est la source de vérité sur l'architecture, les dépendances et les points sensibles du service.

```bash
for d in *_api *_mcp agent_*; do [ -f "$d/README.md" ] && echo "=== $d ===" && head -30 "$d/README.md"; done
```

Si un README est absent pour un service ciblé → le créer conformément au template §13 AGENTS.md avant de continuer.

## 1. Audit Périmétrique et Terraform (Network & IAM)
Vérifiez activement le code contenu dans `platform-engineering/terraform/` :
- **Règles WAF (Cloud Armor)** : S'assurer que les défenses OWASP (`sqli`, `xss`, `lfi`, `rce`, `scannerdetection`) et les *Rate Limiters* (Protection Anti-DoS et FinOps) sont actifs et configurés dans le fichier `waf.tf`.
- **Zero-Trust Networking (VPC Egress)** : Contrôler `vpc.tf` pour certifier l'existence d'une règle "Deny All" (`fw-deny-egress`). Confirmer que seuls AlloyDB, Redis, le Load Balancer interne et les APIs Google (HTTPS sortant) sont sur liste blanche.
- **Moindre Privilège (IAM)** : Vérifier que chaque microservice dispose de son *Service Account* dédié (`cr_sa`). S'assurer que le scope `secretAccessor` ne soit attribué qu'aux services strictement contraints de lire un secret applicatif en particulier.

## 2. Audit Applicatif Backend (API et Contrat HTTP)
Vérifiez le code source (Python/FastAPI) :
- **Vérification JWT Systématique** : Confirmer que `Depends(verify_jwt)` est imposé sur les instanciations de `APIRouter` de chaque microservice et Serveur MCP, garantissant un contrôle strict des accès, même en trafic inter-microservices VPC natif.
- **Anti-Fingerprinting Serveur** : Valider que les configurations `uvicorn` (que ce soit via CLI Terraform `args` flag `--no-server-header` ou script Python `server_header=False`) suppriment les empreintes côté serveur.
- **Leak Mitigation Mémoire** : S'assurer que toutes les clés critiques ou mots de passe initiaux subissent d'office un `os.environ.pop()` immédiatement au démarrage (`main.py`, `auth.py`). L'objectif principal est de parer à un comportement inattendu où l'agent fouillerait les variables d'environnement de son système (Prompt Injection).
- **Pagination — Absence de Hard Limits** : Vérifier que tout endpoint retournant une liste utilise `skip`/`limit` + `total` et que la consommation d'APIs externes (Google Drive, BigQuery) utilise les page tokens. Commandes de détection :
  ```bash
  # Hard limits sans pagination
  grep -rn "\.limit(" */src/ | grep -v "skip\|offset\|page" | head -20
  # Appels Google API sans boucle pageToken
  grep -rn "\.list(" */src/ --include="*.py" | grep -v "pageToken\|page_token\|while" | head -20
  ```

## 3. Pratiques Avancées et Nouvelles Règles de Sécurité (Agent)
En plus du contexte historique, valider l'intégrité globale sur ces directives additionnelles :
- **Protection Supply Chain (Dependency Audit)** : Vérifier que le dépôt force l'utilisation de tests SAST (comme `bandit` dans le fichier `.pre-commit-config.yaml`) et vérifier les fichiers `requirements.txt` pour éviter toute utilisation de paquets LLM vulnérables très anciens.
- **Rotation et Éphémérité** : Les Access Tokens (JWT) générés doivent être volontairement très volatils (Short-lvied). S'assurer que le cycle de vie réseau tolère des expirations sans compromettre l'UX (ex: utilisation stricte du mécanisme d'actualisation transparent, ou invalidation via Redis si un compte devient compromis).
- **Surveillance Comportementale et FinOps** : L'infrastructure de l'IA coûtant très cher à chaque requête malicieuse (Exfiltration de base de connaissance par un attaquant), il convient de vérifier la présence d'un *Semantic Cache* solide (Redis) ainsi qu'un outil "Anomaly Detection" couplé au stream BigQuery existant dans le projet.
- **Isolation de la Multimodalité (RCE Sandbox)** : Parce que l'Agent traite fréquemment des PDFs et fichiers Docs via MCP CV/Mission : vérifier que tout outil MCP parsant des flux binaires utilisateurs externes soit strictement cantonné à une zone volatile (Sandbox, isolation en ram ou `/tmp`) afin d'écraser automatiquement une tentative de Remote Code Execution liée aux macros cachées.

## 4. Audit du Contrat Docker (Cloud Run)
Parcourez l'ensemble des `Dockerfile` :
- Refus implicite de toute image tournant en mode `root`. L'utilisateur `USER appuser` doit être défini pour le Backend, et `nginx-unprivileged` géré côté VueJs.
- Hygiène du Build avec des `.dockerignore` stricts validant l'exclusion de `.env`, clefs asymétriques ou de secrets.

## 5. Analyse Systémique RBAC (Contrôle d'Accès par Rôle)
Vérifier la matrice des droits pour chaque rôle (`user`, `rh`, `commercial`, `admin`, `service_account`) :

- **Formalisation des Rôles** : Contrôler que le champ `role` dans `users_api/src/users/schemas.py` est une `Literal` Python (ou équivalent Pydantic) imposant des valeurs strictes (`user`, `rh`, `commercial`, `admin`, `service_account`). Un champ `String` libre est une faille permettant l'injection de rôles arbitraires.
- **Guards Backend sur Actions Coûteuses** : Vérifier que les endpoints déclenchant un LLM ou un batch Vertex AI (ex: `POST /missions`, `POST /cvs/import`, `POST /recalculate_tree`) sont protégés par une vérification de rôle explicite au-delà du simple JWT. Tout JWT valide d'un `user` standard ne doit pas pouvoir déclencher une analyse Gemini.
- **Guards Backend sur Actions Administratives** : Contrôler que les endpoints de mutation structurelle (création d'utilisateur, suspension de compte, suppression de missions, bulk_tree de taxonomie) imposent `role in ["admin", "service_account"]`. La commande `grep -rn 'role.*!=.*admin\|role not in' --include="*.py"` doit couvrir tous les endpoints sensibles.
- **Cohérence Frontend/Backend** : S'assurer que les routes frontend marquées `adminOnly` dans le router Vue sont AUSSI protégées côté backend. Une route frontend sans meta `adminOnly` accessible directement par URL est une faille si le backend ne vérifie pas le rôle.
- **Enum Rôle Obligatoire** : Ajouter un changeset Liquibase avec une contrainte `CHECK (role IN ('user', 'rh', 'commercial', 'admin', 'service_account'))` sur la colonne `role` de la table `users` pour prévenir la corruption en base.
- **Matrice Cible** : Pour chaque API data, vérifier la conformité à la matrice suivante :

| Action | user | rh | commercial | admin | service_account |
|--------|:----:|:--:|:----------:|:-----:|:---------------:|
| Créer mission + LLM | ❌ | ❌ | ✅ | ✅ | ✅ |
| Importer CV + LLM | ❌ | ✅ | ❌ | ✅ | ✅ |
| Créer compétence | ❌ | ✅ | ❌ | ✅ | ✅ |
| Créer utilisateur | ❌ | ❌ | ❌ | ✅ | ✅ |
| Suspendre utilisateur | ❌ | ❌ | ❌ | ✅ | ❌ |
| Ré-analyse batch (Vertex AI) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Modifier prompts IA | ❌ | ❌ | ❌ | ✅ | ❌ |

## 6. Audit MCP — Élévation de Privilèges via Tools
Les serveurs MCP (`mcp_server.py`) constituent un vecteur d'attaque indirect : un agent IA peut appeler un tool MCP qui contourne les gardes de rôle si celles-ci ne sont pas en place côté backend.

- **Propagation JWT Obligatoire** : Vérifier que chaque `mcp_server.py` propage le JWT entrant via `mcp_auth_header_var` (ContextVar) dans les headers des appels HTTP sortants vers les APIs data. L'absence de propagation implique que les appels MCP arrivent sans JWT → rejet 401 ou, pire, bypass si le backend n'a pas de guard.
- **Pas de Logique de Rôle dans les MCP** : Les tools MCP ne doivent PAS implémenter de logique de rôle propre — ce serait de la duplication fragile. La responsabilité est intégralement dans l'API data cible. Vérifier qu'aucun MCP ne contient de pattern `if role == "admin": skip_guard`.
- **Tools Destructifs Sans Guard Backend** : Identifier les tools MCP exposant des actions destructives (`delete_competency`, `delete_all_missions`, `clear_user_competencies`) et s'assurer que l'API cible impose une vérification de rôle `admin` sur ces endpoints. Commande : `grep -n "delete\|clear\|drop\|suspend" */mcp_server.py`.
- **Pas de Fabrication de Token** : Vérifier que les MCP servers ne génèrent pas de JWT de service en interne (pas d'appel à `/auth/internal/service-token` sans audit trail). Seul `agent_router_api` est autorisé à obtenir un service token avant de lancer une background task.
- **Isolation Stdio** : Les sidecars MCP stdio (`mcp_server.py`) ne doivent pas avoir accès aux variables d'environnement contenant des secrets (SECRET_KEY, GOOGLE_API_KEY). Ces variables doivent être purgées via `os.environ.pop()` dans `main.py` avant le démarrage du sidecar.
