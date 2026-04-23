---
description: Workflow d'audit automatisé de sécurité applicative, Terraform et bonnes pratiques Zero-Trust.
---

# Worfklow : Analyse de Sécurité Globale (/analyse-security)

// turbo-all

Ce workflow fournit une marche à suivre stricte pour auditer la posture de sécurité de la plateforme, depuis l'Infrastructure as Code (Terraform) jusqu'à la logique applicative (FastAPI, LLM). Lorsqu'un utilisateur exécute ce workflow, l'Agent DOIT exécuter les vérifications suivantes de manière autonome.

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
