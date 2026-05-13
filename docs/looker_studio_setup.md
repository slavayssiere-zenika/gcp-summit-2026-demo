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

---

# Dashboard 2 : Usages Utilisateurs & FinOps IA

Ce dashboard visualise la consommation IA réelle de la plateforme à partir de la table BigQuery `ai_usage` (dataset `finops`), alimentée en temps réel par chaque appel au tool `log_ai_consumption` de l'`analytics_mcp`.

> [!NOTE]
> La table `ai_usage` est alimentée en continu (temps réel) à chaque requête agent. Elle est partitionnée par jour sur le champ `timestamp`.

## Schéma de la table `finops.ai_usage`

| Colonne | Type BQ | Description |
|---|---|---|
| `timestamp` | TIMESTAMP | Horodatage UTC de l'appel |
| `user_email` | STRING | Email de l'utilisateur |
| `action` | STRING | Tool ou action LLM déclenchée (ex: `agent_query`, `analyze_cv`) |
| `model` | STRING | Modèle IA utilisé (ex: `gemini-2.5-flash`) |
| `input_tokens` | INTEGER | Tokens en entrée |
| `output_tokens` | INTEGER | Tokens en sortie |
| `unit_cost` | FLOAT | Coût unitaire estimé (optionnel, peut être NULL) |
| `is_batch` | BOOLEAN | Si `true`, le coût est divisé par 2 (Vertex AI Batch) |
| `metadata` | STRING | JSON sérialisé avec contexte additionnel |

## Étape 1 : Créer la source de données `ai_usage`

1. Rendez-vous sur [Looker Studio](https://lookerstudio.google.com/).
2. Cliquez sur **Créer** > **Source de données** > **BigQuery**.
3. Sélectionnez :
   - **Projet** : votre projet GCP (ex: `prod-ia-staffing`)
   - **Ensemble de données** : `finops`
   - **Table** : `ai_usage`
4. Cliquez sur **Associer**.

## Étape 2 : Configurer les types de champs

Dans l'écran de configuration des champs, vérifiez et corrigez :

| Champ | Type attendu | Agrégation par défaut |
|---|---|---|
| `timestamp` | Date & Heure | — |
| `user_email` | Texte | — |
| `action` | Texte | — |
| `model` | Texte | — |
| `input_tokens` | Nombre | Somme |
| `output_tokens` | Nombre | Somme |
| `unit_cost` | Nombre | Somme |
| `is_batch` | Booléen | — |

### Champs calculés à créer

Cliquez sur **Ajouter un champ** (en bas à gauche) pour créer ces métriques dérivées :

**`total_tokens`** — Total de tokens consommés par ligne :
```
input_tokens + output_tokens
```

**`cout_estime_usd`** — Coût estimé par requête (en utilisant les prix Gemini par défaut) :
```
(input_tokens * 0.000000075 + output_tokens * 0.0000003) * IF(is_batch, 0.5, 1.0)
```

**`date_jour`** — Date tronquée au jour (pour les graphiques en série temporelle) :
```
TODATE(timestamp, 'YYYYMMDD')
```

> [!TIP]
> Le champ `timestamp` peut directement servir de dimension temporelle. Looker Studio permet de choisir la granularité (Heure, Jour, Semaine, Mois) dans le panneau de chaque graphique — pas besoin de créer `date_jour` si vous préférez rester flexible.

## Étape 3 : Construire le Dashboard

### Page 1 — Vue Exécutive (KPIs)

Ajoutez **4 scorecards** en haut de page :

| Scorecard | Métrique | Agrégation |
|---|---|---|
| **Requêtes totales** | `Record Count` | Comptage |
| **Tokens consommés** | `total_tokens` | Somme |
| **Coût estimé (USD)** | `cout_estime_usd` | Somme |
| **Utilisateurs actifs** | `user_email` | Comptage distinct |

> [!NOTE]
> Pour le scorecard "Utilisateurs actifs", sélectionnez la métrique `user_email` et changez l'agrégation en **"Comptage distinct"** (≠ Comptage) dans le panneau de droite.

Ajoutez un **contrôle de plage de dates** (lié à `timestamp`) pour que tous les graphiques soient filtrables par période.

---

### Page 2 — Évolution dans le Temps

#### Graphique 1 : Nombre de requêtes par jour (Courbe)
Idéal pour détecter les pics d'usage et les jours creux.

- **Type** : Graphique en courbes (ou barres)
- **Dimension** : `timestamp` → granularité **Jour**
- **Métrique** : `Record Count`
- **Tri** : `timestamp` Croissant

#### Graphique 2 : Tokens consommés par jour (Aires empilées)
Permet de voir la volumétrie et la répartition input/output.

- **Type** : Graphique en aires empilées
- **Dimension** : `timestamp` → granularité **Jour**
- **Métriques** :
  - `input_tokens` (Somme)
  - `output_tokens` (Somme)
- **Tri** : `timestamp` Croissant

#### Graphique 3 : Coût estimé par jour (Barres)
Vue FinOps journalière.

- **Type** : Graphique à barres
- **Dimension** : `timestamp` → granularité **Jour**
- **Métrique** : `cout_estime_usd` (Somme)
- **Tri** : `timestamp` Croissant

---

### Page 3 — Analyse par Utilisateur

#### Graphique 4 : Top 10 utilisateurs par nombre de requêtes (Barres horizontales)
Qui interroge le plus les agents ?

- **Type** : Graphique à barres (horizontal)
- **Dimension** : `user_email`
- **Métrique** : `Record Count`
- **Tri** : `Record Count` Décroissant
- **Lignes affichées** : 10

#### Graphique 5 : Top 10 utilisateurs par coût (Barres horizontales)
Qui génère le plus de coût IA ?

- **Type** : Graphique à barres (horizontal)
- **Dimension** : `user_email`
- **Métrique** : `cout_estime_usd` (Somme)
- **Tri** : `cout_estime_usd` Décroissant
- **Lignes affichées** : 10

#### Graphique 6 : Tableau détaillé par utilisateur

- **Type** : Tableau
- **Dimension** : `user_email`
- **Métriques** : `Record Count`, `total_tokens` (Somme), `cout_estime_usd` (Somme)
- **Mise en forme conditionnelle** sur `cout_estime_usd` : dégradé vert → rouge selon la valeur.

---

### Page 4 — Analyse par Type de Requête (`action`)

C'est la page clé pour comprendre **quels usages dominent**.

#### Graphique 7 : Répartition par action (Camembert)
Vue macro de la distribution des types de requêtes.

- **Type** : Graphique en secteurs (Camembert)
- **Dimension** : `action`
- **Métrique** : `Record Count`
- **Nombre de secteurs max** : 10

#### Graphique 8 : Top actions par volume de tokens (Barres)
Quelle action consomme le plus de tokens (= la plus coûteuse en LLM) ?

- **Type** : Graphique à barres (horizontal)
- **Dimension** : `action`
- **Métriques** :
  - `input_tokens` (Somme)
  - `output_tokens` (Somme)
- **Tri** : `total_tokens` Décroissant

#### Graphique 9 : Évolution des actions dans le temps (Barres empilées)
Permet de voir si certains usages émergent ou disparaissent.

- **Type** : Graphique à barres empilées
- **Dimension** : `timestamp` → granularité **Semaine**
- **Répartition** (Breakdown) : `action`
- **Métrique** : `Record Count`

---

### Page 5 — Analyse par Modèle IA

#### Graphique 10 : Répartition par modèle (Camembert)
Quelle proportion des requêtes utilise chaque modèle ?

- **Type** : Camembert
- **Dimension** : `model`
- **Métrique** : `Record Count`

#### Graphique 11 : Coût par modèle (Barres)
Quel modèle génère le plus de coût ?

- **Type** : Graphique à barres
- **Dimension** : `model`
- **Métrique** : `cout_estime_usd` (Somme)
- **Tri** : Décroissant

---

### Page 6 — Anomalies & Monitoring

#### Graphique 12 : Tokens par heure (Courbe — détection de pics)
Permet de détecter visuellement les comportements anormaux (flood de requêtes).

- **Type** : Graphique en courbes
- **Dimension** : `timestamp` → granularité **Heure**
- **Métrique** : `total_tokens` (Somme)
- **Filtre** : Restreindre à la dernière semaine via le contrôle de dates.

> [!WARNING]
> Si une courbe horaire dépasse **50 000 tokens/heure** pour un utilisateur, cela correspond au seuil de l'outil `detect_usage_anomalies`. Vous pouvez créer un filtre `user_email` pour isoler l'utilisateur suspect.

#### Graphique 13 : Tableau des sessions suspectes

- **Type** : Tableau
- **Dimensions** : `user_email`, `timestamp` (granularité Heure)
- **Métrique** : `total_tokens` (Somme)
- **Filtre** : Créer un filtre **"Metric Filter"** → `total_tokens > 10000` pour ne montrer que les heures à fort volume.

---

## Étape 4 : Filtres globaux recommandés

Ajoutez ces contrôles en haut de chaque page (ou dans une barre de navigation commune) :

| Contrôle | Champ source | Utilité |
|---|---|---|
| **Plage de dates** | `timestamp` | Filtrer par période |
| **Utilisateur** | `user_email` | Zoom sur un consultant spécifique |
| **Type de requête** | `action` | Isoler `agent_query` vs `analyze_cv` etc. |
| **Modèle IA** | `model` | Comparer Gemini Flash vs Pro |

> [!TIP]
> Pour appliquer un filtre à plusieurs graphiques sur la même page : sélectionnez tous les graphiques (Ctrl+A), puis faites clic-droit > **Ajouter un filtre**.

## Étape 5 : Partage

1. Cliquez sur **Partager** > entrez les emails des parties prenantes.
2. Pour un accès en lecture seule sans compte Google : **Partage de lien** > *Tout utilisateur avec le lien peut voir*.
3. Pour intégrer dans Notion / Confluence : **Fichier** > **Intégrer le rapport** > copier l'iframe.

> [!IMPORTANT]
> Les personnes accédant au rapport doivent avoir le rôle **`roles/bigquery.dataViewer`** sur le dataset `finops` du projet GCP, sinon la connexion BigQuery retournera une erreur 403. Vérifiez dans IAM > "Accorder l'accès".

