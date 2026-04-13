# ADR 0009 : Choix d'Infrastructure as Code (GCP & Cloud Run)

## Statut
Accepté

## Contexte
La console, étant fractionnée en de nombreux services indépendants (Front-end, orchestrateur IA, APIs de backend), exigeait un hébergement à forte scalabilité capable de résister aux pics imprévisibles des sollicitations de l'Agent. Il était tout aussi capital que les déploiements de chaque sous-composant n'engendrent aucune indisponibilité, sans pour autant sombrer dans une complexité de gestion telle que Kubernetes nécessiterait.

## Décision
- **Moteur Serverless : Google Cloud Run.** Le choix d'exécuter des conteneurs sans état (stateless) favorise le modèle "Scale-to-Zero" propice à l'approche FinOps.
- **Modèle IaC : Terraform.** L'intégralité du socle (DNS, Bases de Données managed AlloyDB, Réseaux, IAM, Load Balancers, Cloud Run) est gérée d'une seule source de vérité par l'automatisation Terraform. L'absence de bouton ou clic manuel est imposée.
- Les conteneurs exigent des pratiques multi-stage strictes (Images `distroless` ou Non-Root) dictées en AGENTS.md, car la plateforme Google sanctionne durement toute faille via les contrats Serverless sécurisés.
- Le nommage unifié (Variables `APP_VERSION`, Semantic Versioning patchés à chaud) est injecté nativement via variables d'environnement.

## Conséquences
- **Positives :**
  - **Friction opérationnelle 0 :** Un développeur focalisé python n'a pas à maintenir de nœuds Linux.
  - Le provisionnement d'un environnement de `staging` isolé depuis le code n'est l'affaire que de changer l'identifiant Terraform `workspace`.
- **Négatives :** 
  - La forte adhésion aux produits Google : DocumentAI, Cloud Trace, AlloyDB et Secret Manager induisent un **Vendor Lock-in** certain.
- **Risques :** Erreurs d'Idempotence Terraform: toute action asynchrone non-traitable via API standard requiert une résilience supplémentaire dans les scripts python `manage_env`.
