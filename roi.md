# Projection FinOps & R.O.I de la Console Zenika

Sur la base de l'infrastructure as code (`terraform`) et de l'architecture micro-services implémentée, voici la projection FinOps mensuelle de la plateforme déployée sur Google Cloud Platform (région `europe-west1`).

## 1. Le Socle Fixe d'Infrastructure (Indépendant des utilisateurs)

C'est le coût de maintien en conditions opérationnelles (MCO) de votre plateforme, même si personne ne s'y connecte :

| Composant | Description | Estimation Mensuelle |
| :--- | :--- | :--- |
| **AlloyDB** | Cluster primaire (`alloydb_cpu: 2`, soit 2 vCPU + 16 Go de RAM) pour la gestion avancée PostgreSQL. | ~ 160,00 $ |
| **Memorystore (Redis)** | Instance `BASIC` de 1 GB servant notamment au cache sémantique LLM. | ~ 35,00 $ |
| **Load Balancing L7** | Règle de routage global (`forwarding rules`) HTTPS et intégration Serverless NEG. | ~ 18,00 $ |
| **Cloud Armor (WAF)** | Politique de sécurité de base anti-flood. | ~ 5,00 $ |
| **Cloud Run (Warmup)** | Optionnel : Si `cloudrun_min_instances = 1` est actif sur les 9 micro-services as-code pour garantir une réactivité sous les 50ms constante (Maintien à chaud). | ~ 90,00 $ |

**TOTAL FRAIS FIXES : ~218$ / mois** *(ou ~308$ en comptant le maintien à chaud optionnel des conteneurs).*

---

## 2. Les Frais Variables (Élastiques par utilisateur)

### A. Le Coût de l'Intelligence Artificielle (Multi-Agent Gemini 3.1)
L'architecture multi-agent utilise un mix de modèles pour optimiser les performances et le coût (selon les recommandations de type "Génération Actuelle" 3.1) :
- **Routeur (Gemini 3.1 Pro)** : `gemini-3.1-pro-preview` (~ 2,00$ / 1M in, 12,00$ / 1M out) pour le raisonnement complexe et l'orchestration.
- **Agents Spécialisés (Gemini 3.1 Flash-Lite)** : `gemini-3.1-flash-lite-preview` (~ 0,25$ / 1M in, 1,50$ / 1M out) pour le RAG à fort volume et l'exécution.

- **Simulation de requête type (Router + RAG)** : Un collaborateur interroge la plateforme. Le Routeur analyse l'intention (~1 000 tokens in, ~100 tokens out), puis un Agent HR ou Ops injecte un contexte RAG (CV, Compétences) lourd (~10 000 tokens in) et génère la réponse finale (~500 tokens out).
- **Coût de la requête (mixte)** :
  - *Routeur (Pro)* : ~ 0,0032 $
  - *Agent (Flash-Lite)* : ~ 0,0033 $
  - **Total** : ~ 0,0065 $ par requête complexe.
- **Coût mensuel par Utilisateur Actif** : S'il effectue **100 requêtes complexes par mois**, cela facture approximativement **0,65$ / mois** (l'évolution depuis Gemini 2.5 Flash reflète un choix assumé pour la très haute intelligence du Pro sur l'orchestration). 
*(Ce coût chute drastiquement grâce à l'interception instantanée et sans surcoût des réponses par le Cache Sémantique Redis sur des prompts similaires, ce qui évite de déclencher le Routeur et les LLMs).*

### B. Le Compute pur (Cloud Run) et la Télémétrie
- Les requêtes additionnelles distribuées sur les APIs (facturées à la centaine de millisecondes près) sont structurellement négligeables comparées au volume classique (quelques centimes maximum).
- L'ingestion des logs FinOps ou traces Grafana/Tempo tombe quasi intégralement sous les *Free Tiers* Google Cloud et Observability standards (ex: 1 To de requêtes BigQuery gratuit par mois).
- **Coût estimé additionnel par utilisateur** : ~ 0,02$ / mois.

---

## 3. Calcul de Synthèse Macro et ROI

En intégrant un comportement d'usage métier classique (environ 10 à 20 min d'utilisation métier quotidienne par personne), avec un coût marginal approchant les **0,67$ / mois / utilisateur actif** (IA + Compute) :

| Volumétrie Active | Frais Fixes d'Infra (avec instances chaudes) | Coûts d'usages (IA + Compute) | Estimation Mensuelle Totale |
| :--- | :--- | :--- | :--- |
| **10 utilisateurs** | ~ 308 $ | ~ 6,70 $ | **~ 314,70 $ / mois** |
| **100 utilisateurs** | ~ 308 $ | ~ 67,00 $ | **~ 375,00 $ / mois** |
| **1 000 utilisateurs** | ~ 308 $ | ~ 670,00 $ | **~ 978,00 $ / mois** |

### Conclusion
Le retour sur investissement technique est impressionnant sur GCP. Jusqu'à hauteur d'environ 500 collaborateurs simultanés, le poste majeur de dépense de toute la plateforme d'entreprise continuera d'être la base de données relationnelle haute-puissance (AlloyDB). Grâce au couplage du design Serverless Google Cloud, d'un bon Caching sémantique, et du routage intelligent vers Gemini 3.1 Flash-Lite, l'intelligence distribuée elle-même devient une commodité extrêmement scalable et prédictible financièrement.
