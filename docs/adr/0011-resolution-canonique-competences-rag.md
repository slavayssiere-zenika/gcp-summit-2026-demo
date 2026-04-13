# ADR 0011 : Résolution Canonique des Compétences et Injection Taxonomique RAG

## Statut
Accepté

## Contexte
Le moteur de mise en relation (*matching*) entre les CVs et les Missions s'appuyait initialement sur les mots-clés extraits par des modèles (LLMs) indépendants de manière asynchrone (via `cv_api` et `missions_api`). 
Le filtrage initial, réalisé avant le calcul de distance vectorielle (`pgvector`), utilisait un matching textuel strict (`AND` SQL) ou permissif (`ilike` textuel sur du JSONB) entre les mots extraits. 
Cependant, cette approche asymétrique créait de profonds désalignements sémantiques (ex: l'IA du CV produit `"Frontend"` alors que l'IA de la mission produit `"Front"` ou invente `"Développement Client"`). L'absence de référentiel strict générait un fort taux d'échecs (aucun candidat sélectionné), cassant le pipeline métier de "Staffing" RAG. De plus, la notion d'héritage de compétences (hiérarchie technologique) était manuellement traitée via des chaînes de caractères arbitraires, by-passant totalement le graphe canonique maintenu par le micro-service maître (`competencies_api`).

## Décision
À l'issue de plusieurs itérations, nous avons implémenté une **amélioration de l'intelligence taxonomique (LLM Grounding)** couplée à un **pré-filtrage textuel permissif (RAG Soft-Filtering)** afin de garantir un Matching fluide sans surcharger la base de données :

1. **Injection de Contexte Taxonomique (Mid-Parents) :** Avant d'analyser un texte, `cv_api` et `missions_api` interrogent le dictionnaire central (`competencies_api`). Cependant, pour éviter d'inonder Gemini avec des "Racines" trop générales (ex: "Informatique") ou des "Feuilles" trop nombreuses (ex: "S3", "Kubernetes"), le système isole dynamiquement et injecte **uniquement les catégories intermédiaires** (`parent_id != None` et possédant des enfants). Ce référentiel ciblé force l'IA à utiliser les terminologies officielles du métier (ex: "Frontend", "Cloud") lors de l'extraction, et réduit le nombre total de prompts générés.
2. **Abrogation du Hard-Filter SQL et Scalabilité :** La stratégie initiale de confier la pré-sélection à une stricte validation réseau et relationnelle (`IN (approved_user_ids)` en SQL sur base de résolution de graphe avec CTE récursive) a été supprimée suite à la constatation du syndrome "aucun CV ne correspond" (faux négatifs liés aux imperfections de l'IA lors de l'assignation asynchrone). Désormais, la résolution canonique inter-API est évitée au profit d'un filtrage purement intralocal dans la CV API.
3. **Pré-Filtrage Textuel Souple (OR Logic) :** `cv_api/search` emploie désormais une clause `OR` textuelle (`ilike`) sur le `JSONB` des compétences et le tableau de mots-clés (`competencies_keywords`). Cela retient asynchrone tout candidat "évoquant" le domaine technique, libérant la vraie puissance du calcul de `cosine_distance` (`pgvector`).

## Conséquences
- **Positives :**
  - **Fidélisation Sémantique :** L'ancre du prompt *mid-parent* supprime totalement les hallucinations technologiques de Gemini sans faire exploser la fenêtre de contexte.
  - **Limitation d'Appels Réseau/DB :** En gérant le pré-filtre localement dans PostgreSQL (`OR ilike`) pour la SPA de matching, on évite totalement d'inonder `competencies_api` avec des n+1 *query requests* pour résoudre l'arbre des consultants. Le temps d'exécution global de la route de Matching s'effondre.
  - **Permissivité Maximale :** Aucun CV contenant lexicalement et sémantiquement les concepts n'est injustement éliminé suite à une sous-structuration du graphe relationnel.
- **Négatives :** 
  - **Pression Query (Sequential Scan) :** Les requêtes reposent sur un `OR` textuel massif combiné à de l'`ilike('%...%')` sur des champs JSONB/Array stringifiés dans `cv_profiles`. Sur d'immenses bases de données (Big Data CVs), l'index B-Tree natif de PostgreSQL est inefficace pour ce type d'opérateur. La BD exécute de fait un filtre sémantique *Full Seq Scan* sur ces colonnes.
- **Risques :**
  - **Timeouts d'Indexation :** Au-delà d'un volume critique (50 000+ consultants), la recherche `ilike` asymétrique ralentira le temps de calcul du Vector Engine RAG, déclenchant des timeouts sur FastAPI.
  - **Mitigation (Roadmap) :** Remplacer le `cast(JSONB).ilike()` par un index textuel **GIN (`tsvector`)** Postgres très optimisé pour accélérer d'un facteur x100 la phase pré-filtre, avant transmission à pgvector.
