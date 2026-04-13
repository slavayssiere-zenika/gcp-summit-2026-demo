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

### A. Le Coût de l'Intelligence Artificielle (Gemini Flash RAG)
Le modèle configuré dans l'API Agent (`gemini-2.0-flash`) bénéficie d'une tarification très agressive pour le RAG de grand volume : ~0,075$ pour 1M de tokens en entrée et 0,30$ en sortie.

- **Simulation de requête type** : Un collaborateur interroge l'Agent. L'Agent injecte le contexte RAG de 3 candidats (~10 000 tokens in) et génère une réponse détaillée (~500 tokens out).
- **Coût de la requête** : ~ 0,0009 $.
- **Coût mensuel par Utilisateur Actif** : S'il effectue **100 requêtes complexes par mois**, cela facture approximativement **0,10$ / mois**. 
*(Ce coût peut même chuter grâce à l'interception instantanée et sans surcoût des réponses par le Cache Sémantique Redis sur des prompts similaires).*

### B. Le Compute pur (Cloud Run) et la Télémétrie
- Les requêtes additionnelles distribuées sur les APIs (facturées à la centaine de millisecondes près) sont structurellement négligeables comparées au volume classique (quelques centimes maximum).
- L'ingestion des logs FinOps ou traces Grafana/Tempo tombe quasi intégralement sous les *Free Tiers* Google Cloud et Observability standards (ex: 1 To de requêtes BigQuery gratuit par mois).
- **Coût estimé additionnel par utilisateur** : ~ 0,02$ / mois.

---

## 3. Calcul de Synthèse Macro et ROI

En intégrant un comportement d'usage métier classique (environ 10 à 20 min d'utilisation métier quotidienne par personne) :

| Volumétrie Active | Frais Fixes d'Infra (avec instances chaudes) | Coûts d'usages (IA + Compute) | Estimation Mensuelle Totale |
| :--- | :--- | :--- | :--- |
| **10 utilisateurs** | ~ 308 $ | ~ 1,20 $ | **~ 309,20 $ / mois** |
| **100 utilisateurs** | ~ 308 $ | ~ 12,00 $ | **~ 320,00 $ / mois** |
| **1 000 utilisateurs** | ~ 308 $ | ~ 120,00 $ | **~ 428,00 $ / mois** |

### Conclusion
Le retour sur investissement technique est impressionnant sur GCP. Jusqu'à hauteur de 2500 collaborateurs simultanés, le poste majeur de dépense de toute la plateforme d'entreprise continuera d'être la base de données relationnelle haute-puissance (AlloyDB). Grâce au couplage du design Serverless Google Cloud, d'un bon Caching sémantique et du modèle Gemini Flash de Google ADK, l'intelligence distribuée elle-même devient une commodité presque mathématiquement gratuite.
