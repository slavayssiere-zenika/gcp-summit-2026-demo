# ADR 0006 : Recherche Sémantique Hybride via RAG et PGVector

## Statut
Accepté

## Contexte
La console gère des compétences disparates et un annuaire lourd de CVs textuellement longs et désorganisés. Faire une correspondance stricte par mot clé (Elasticsearch `term`) lors de l'Assignation d'une mission à un dev engendrait trop de biais et rejetait des synonymes légitimes. Pour faire matcher des missions vastes ("Migration AWS serverless de vieux code Legacy") à des profils pertinents, il fallait une méthode de correspondance d'esprit (Embedded space).

## Décision
- Résolution architecturale RAG (Retrieval-Augmented Generation) sur-mesure.
- Les documents entrants se transforment en tableaux chiffrés (3072 dimensions) via `Gemini text-embedding`.
- Persistance et Recherche de plus proche voisin assurée par **l'extension `pgvector` dans PostgreSQL**. L'usage asymétrique de PostgreSQL garantit que nous conservons les jointures relationnelles aux entités réelles (User ID) tout en recherchant vectoriellement (la `cosine_distance`).
- L'approche est "Pré-filtrée". Au lieu d'abuser de la force brute géométrique dans d'énormes banques vectorielles : Le système exige dans un premier ordre l'extraction de Mots-Clés stricts (`ilike`) du problème, afin de réduire sous le socle base de données les correspondances possibles (Candidats techniques valides) AVANT de laisser la distance Cosinus trancher entre eux.

## Conséquences
- **Positives :**
  - Fin du lock-in fournisseur avec des bases vectorielles obscures ; on exploite pleinement l'écosystème Cloud SQL et ses sauvegardes standards.
  - Précision drastique de recherche, les réponses aberrantes se voient éliminées par l'approche hybride : SQL relationnel (filtrage) + géométrie.
- **Négatives :** 
  - La maintenance d'une migration Liquibase incluant `CREATE EXTENSION vector` ; incompatibilité de certaines bases locales.
- **Risques :** En l'absence de l'index optimal `ivfflat` ou `HNSW`, pgvector opère un scan séquentiel (table scan) sur les vecteurs, ralentissant gravement à l'échelle (+ de 100 000 entrées).
