# Tutoriel : Configuration du Dashboard Looker Studio pour le Skill Gap Analysis

Ce tutoriel explique comment configurer un dashboard interactif dans Looker Studio basé sur la table BigQuery `skill_gap_analysis` alimentée quotidiennement par l'agent `analytics_mcp`.

> [!NOTE]
> La table `skill_gap_analysis` est mise à jour automatiquement toutes les nuits. Elle croise la demande (compétences requises par les missions actives) et l'offre (consultants internes).

## Prérequis

1. Avoir un compte Google avec un accès en lecture sur le projet GCP hébergeant la Console Zenika.
2. S'assurer que la table BigQuery `skill_gap_analysis` existe et contient des données (dataset : généralement `analytics` ou `finops` selon l'environnement).

## Étape 1 : Créer la source de données

1. Rendez-vous sur [Looker Studio](https://lookerstudio.google.com/).
2. Cliquez sur **Créer** > **Source de données**.
3. Sélectionnez le connecteur **BigQuery**.
4. Autorisez l'accès à votre compte si demandé.
5. Dans l'arborescence, sélectionnez :
   - Votre **Projet** (ex: `zenika-console-prd`).
   - Votre **Ensemble de données** (ex: `zenika_analytics`).
   - Votre **Table** (`skill_gap_analysis`).
6. Cliquez sur **Associer** en haut à droite.

## Étape 2 : Configurer les champs de la source de données

Dans l'écran de configuration des champs :
- Vérifiez que les types de données sont corrects :
  - `competency_name` : Texte
  - `demand_missions_count` : Nombre (Agrégation : Somme)
  - `supply_consultants_count` : Nombre (Agrégation : Somme)
  - `gap` : Nombre (Agrégation : Somme)
  - `date_computed` : Date
- Cliquez sur **Créer un rapport** en haut à droite.

## Étape 3 : Créer le Dashboard (Template Recommandé)

Voici les graphiques recommandés pour visualiser efficacement le Skill Gap :

### 1. Le graphique à barres du Skill Gap (Top Compétences)
Ce graphique permet de voir quelles compétences sont les plus demandées par rapport aux consultants disponibles.
- **Type de graphique** : Graphique à barres combinées.
- **Dimension** : `competency_name`
- **Métriques** :
  - `demand_missions_count` (La demande)
  - `supply_consultants_count` (L'offre)
- **Tri** : `gap` (Décroissant) pour afficher les plus gros déficits en premier.

### 2. Tableau détaillé
Un tableau simple pour l'analyse brute.
- **Type** : Tableau.
- **Dimension** : `competency_name`
- **Métriques** : `demand_missions_count`, `supply_consultants_count`, `gap`.
- **Mise en forme conditionnelle** : Ajoutez une règle sur la colonne `gap` pour mettre en rouge les valeurs négatives (déficit de consultants) et en vert les valeurs positives (surplus).

### 3. Contrôles de filtrage
Ajoutez des filtres en haut de la page pour permettre à l'utilisateur de manipuler les données.
- **Commande de plage de dates** : Lié à `date_computed` (pour voir l'évolution historique).
- **Filtre liste déroulante** : Lié à `competency_name` pour chercher une technologie précise (ex: *Python* ou *React*).

## Étape 4 : Partage et Intégration

1. Cliquez sur **Partager** en haut à droite.
2. Ajoutez les adresses emails des Product Owners, RH et Commerciaux.
3. (Optionnel) Vous pouvez obtenir un lien d'intégration (iframe) pour inclure ce rapport directement dans une page interne (ex: Notion, Confluence, ou le Frontend Zenika Console si désiré plus tard).

> [!TIP]
> **Maintenance** : Si l'architecture de la table évolue dans l'agent `analytics_mcp`, n'oubliez pas de retourner dans Looker Studio > *Ressources* > *Gérer les sources de données ajoutées* et cliquez sur **Actualiser les champs**.
