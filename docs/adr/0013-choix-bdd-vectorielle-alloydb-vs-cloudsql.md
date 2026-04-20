# ADR 0013 : Choix de la Base de Données Vectorielle Financièrement Optimisée (AlloyDB vs Cloud SQL)

## Statut
Accepté

## Contexte
La console Zenika Agent s'appuie massivement sur des capacités RAG (Retrieval-Augmented Generation) pour rechercher sémantiquement à travers des documents complexes (CVs, Missions, Compétences). Actuellement, la plateforme repose sur Google **AlloyDB pour PostgreSQL** (vecteurs et données relationnelles couplées). 

Une étude FinOps a été requise pour évaluer le gain potentiel de la migration vers le standard managé **Cloud SQL pour PostgreSQL**, moins onéreux, et évaluer les compromis en termes de performances brutes de l'Indexation Vectorielle.

## Décision
Nous prenons la décision délibérée de **maintenir AlloyDB** au lieu de descendre vers Cloud SQL, en raison de notre besoin d'interrogation multi-agents concurrente et du volume évolutif des documents. Le surcoût fixe de l'infrastructure est toléré pour garantir une latence sous-milliseconde et une efficience mémoire à l'échelle.

## Conséquences

- **Négatives (FinOps partiel) :** Le maintien d'AlloyDB impose un surcoût d'environ +70$/mois par rapport à une instance Cloud SQL Standard équivalente (2 vCPU / 16 Go de RAM). L'économie de près de 45% sur le poste de base de données est donc sacrifiée.
- **Positives (Technique & Évolutivité) :** AlloyDB intègre nativement **ScaNN** (`alloydb_scann`), l'algorithme d'indexation vectorielle propriétaire de Google (Scalable Nearest Neighbors). Contrairement au plugin `pgvector` standard de Cloud SQL (qui utilise un graphe HNSW très gourmand en RAM), ScaNN consomme 3 à 4 fois moins de mémoire. 
- **Risques évités :** Sur Cloud SQL, un index HNSW s'agrandissant avec l'ingestion massive de nouveaux CVs/Missions finirait par saturer les 16 Go de RAM, générant de la lecture sur le disque (ce qui dégraderait drastiquement les QPS et la latence temps réel de l'agent). Maintenir ces performances sur Cloud SQL forcerait un "upscale" à 32 ou 64 Go de RAM, recréant un surcoût qui annulerait l'économie initiale.
- **Synthèse :** La décision sacrifie ~840$ annuels d'infrastructure de base pour s'assurer une capacité de montée en échelle sur le volume documentaire, rendant l'usage du LLM fluide et empêchant d'inévitables problèmes structurels de mémoire RAM dans le pipeline RAG.
