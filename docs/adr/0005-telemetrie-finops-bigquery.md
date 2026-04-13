# ADR 0005 : Télémétrie IA et Modèle FinOps BigQuery

## Statut
Accepté

## Contexte
Afin d'éviter toute explosion des coûts due à des itérations démesurées de l'Assistant IA hébergé ou des requêtes d'Enrichissement par appel récursif (Extracteur de profil), il nous fallait garantir un tracking précis du coût "par utilisateur", "par jour", et "par Action de l'agent".
Utiliser PostgreSQL pour ceci encombrerait une base transactionnelle avec potentiellement des milliards de lignes d'audit append-only.

## Décision
- Choix de **Google BigQuery** (OLAP) via la table `ai_usage` comme point central et réceptacle unique des dépenses IA en matière de *Prompt Tokens* et *Completion Tokens*.
- Conception d'une table partitionnée par la colonne d'insertion temporelle par jours (`DAY`) favorisant des requêtes de lecture optimisées pour les dashboards de gestion des coûts (Facture Journalière / Mensuelle par Collaborateur).
- Un *Kill-Switch* intelligent intégré via `Cloud Scheduler` s'appuie sur la consultation de ces partitions agglomérées en direct pour suspendre (désactivation soft dans `users_api`) des comptes dont l'usage anomal des APIs dépasserait un seuil pécuniaire (`FINOPS_ANOMALY_THRESHOLD`).

## Conséquences
- **Positives :**
  - Capacité analytique infinie pour générer un dashboard ROI sans paralyser le transactional.
  - Prise de décisions dynamiques basées sur des requêtes groupées sans scanner toute l'historicité.
- **Négatives :** 
  - L'insertion asynchrone (via une architecture Cloud pub/sub ou Streaming Insert) a pu être court-circuitée pour l'instant via l'API, ce qui rajoute de la latence à l'agent lui-même.
- **Risques :** L'absence d'authentification stricte `auth_token` sur les Tâches Cron (Background tasks) peut fausser les mesures vers l'utilisateur générique "unknown".
