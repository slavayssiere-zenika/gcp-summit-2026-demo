# ADR 0004 : Observabilité Centralisée par OpenTelemetry

## Statut
Accepté

## Contexte
Dans une architecture asynchrone multi-services (qui plus est exploitée par une Intelligence Artificielle non déterministe qui initie les requêtes et appels MCP aléatoirement), il devenait pratiquement impossible d'ausculter l'empreinte d'une exécution de bouton dans les Logs bruts. Sans corrélation, déceler où une erreur de "timeout" réseau s'était induite était insurmontable.

## Décision
- Déploiement systématique et omniprésent de **OpenTelemetry (OTel)** dans le code source de tous les APIs (via `Instrumentator`).
- Utilisation de `B3 Propagator / W3C TraceHeaders` pour greffer l'identifiant initial du bot UI jusqu'au creuset des requêtes de bases de données ou de Gemini API (`inject(headers)`).
- Visualisation asymétrique construite sur la Stack **Prometheus + TEMPO + Grafana** en environnement de monitoring local, et **Google Cloud Trace** en production.
- Filtrage des heuristiques bruyantes liées au `health_check` pour purger la carte de Topologie Réseau construite par le MCP de l'infrastructure.

## Conséquences
- **Positives :**
  - Visualisation en cascade (Waterfall) permettant une détermination au quart de seconde des latences liées au NLP ou bases de données.
  - La Topology Map permet au robot LLM de comprendre de lui-même quelle dépendance a chuté dans le réseau (via le diagnostic automatique).
- **Négatives :** 
  - Fragilité conceptuelle: Si le code d'un proxy intermédiaire omet de copier et propager les variables OTel de la requête web à l'appel `httpx` distant, l'arborescence de la trace est définitivement scindée.
- **Risques :** Volume considérable de cardinalités si on trace chaque appel mineur (ex: Redis get). Filtrages avancés nécessaires.
