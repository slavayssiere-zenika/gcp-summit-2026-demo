# ADR 0010 : Approche de Platform Engineering et Expérience Développeur (DX)

## Statut
Accepté

## Contexte
Avec l'explosion du nombre de microservices (actuellement une dizaine impliquant les APIs natives, les proxy MCP et l'Agent) et de l'orchestration sous-jacente associant des bases de données relationnelles dynamiques (AlloyDB), du cache distribué (Redis), et de l'IA (Gemini, DocumentAI), la complexité opérationnelle globale était devenue un frein. Les développeurs n'auraient pas dû se soucier de maîtriser les arcanes de la distribution Cloud Run, du routage réseau interne GCP ou même des rouages de dépendances asynchrones pour livrer une nouvelle fonctionnalité métier.

Il était impératif de mettre en place un outillage garantissant une haute "Developer Experience" (DX) via une abstraction de la couche d'infrastructure.

## Décision
Intégration d'une doctrine de **Platform Engineering** comme pont entre le DevOps et les ingénieurs applicatifs :
- **Internal Developer Platform (IDP) :** Regroupement de la logique complexe de déploiement, de provisionnement et du cycle de vie des bases de données dans un dossier isolé et centralisé `platform-engineering`. 
- **Plateformes Éphémères ("Ephemeral Environments") :** Le cycle de vie complet de l'infrastructure est rattaché à la notion de *Terraform Workspaces* dynamiques. Un développeur peut instancier un clone parfait et isolé de la production pour tester une branche spécifique (`manage_env.py apply dev-feature-x`) et le détruire en un clic sitôt validé. Aucun serveur n'est considéré "Pet" ; toute ressource est jetable et provisionnée à la volée.
- **Idempotence Stricte d'Infrastructure :** L'écosystème Cloud (GCP/Cloud Run) impose des caprices asynchrones parfois retors (erreurs `409 Conflict`, APIs lentes à propager, configurations DNS verrouillées). La couche `manage_env.py` ne se contente pas d'appeler naïvement Terraform ; elle implémente une orchestration de rattrapage déterministe (sondes d'état dynamiques, import automatique d'états asynchrones) garantissant que lancer le script 1 fois ou 100 fois aboutira systématiquement au même état fonctionnel (Idempotence) sans la moindre erreur fatale HTTP.
- **Semantic Versioning Automatisé :** Le pipeline `scripts/deploy.sh` analyse les commits pour incrémenter nativement les `VERSION` files de tous les composants isolés, poussant les logs et tags sans intervention asynchrone complexe du developpeur métier.
- **Outil local vs Cloud :** Le développeur s'appuie sur `docker-compose.yml` couplé à un `monitoring_net` pour émuler le déploiement local parfait de Tempo/Otel, calquant scrupuleusement la topologie cible Cloud Run.

## Conséquences
- **Positives :**
  - **Réduction de la charge cognitive :** Les développeurs Produit codent en FastAPI/Vue.js sans manipuler le langage Hashicorp (HCL) ou interagir directement avec la GCP Console.
  - **Standardisation :** Les Golden Rules de l'Agent (`AGENTS.md`) et le formatage automatique (pre-commit) maintiennent une propreté de code uniforme indépendamment de son auteur.
  - Les Time-To-Market de déploiements d'API (Missions, CV, etc.) sont accélérés grâce au couplage lâche.
- **Négatives :** 
  - La maintenance des scripts de commodité Python ou shell doit être supportée par un ou plusieurs ingénieurs dédiés et calés en DevOps profond (Platform Engineers).
- **Risques :** "L'Over-engineering". Si la documentation interne (les scripts de bootstrap) devient plus dense à appréhender que l'utilisation directe de Terraform, le Platform Engineering s'essouffle. La simplicité cognitive doit être auditable en permanence.
