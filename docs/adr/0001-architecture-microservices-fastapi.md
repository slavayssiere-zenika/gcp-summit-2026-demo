# ADR 0001 : Architecture Microservices avec FastAPI

## Statut
Accepté

## Contexte
La console Zenika Cloud Run Agent nécessite d'intégrer des fonctionnalités hétérogènes (gestion des utilisateurs, annuaire de CVs complexes, gestion multimodale des missions, traçage des coûts). Construire un monolithe risquerait de lier fortement des modèles de données distincts tout en empêchant la scalabilité asymétrique (le parsing de mission demande plus de ressources CPU que la gestion des items).

De plus, l'adoption d'un paradigme de développement full-python orienté machine learning et intelligence artificielle (GenAI) imposait un framework web réactif, robuste et hautement typé.

## Décision
- Nous avons abandonné les architectures monolithiques traditionnelles en faveur d'une séparation en de multiples **Microservices métiers** indépendants : `users_api`, `items_api`, `competencies_api`, `cv_api`, `missions_api`, `prompts_api`, etc.
- Le framework choisi pour exposer l'ensemble de ces couches HTTP est **FastAPI**.
- Chaque service dispose de sa propre dépendance (`Dockerfile`), de ses dépendances propres sans friction, et s'isole du reste de la logique via des contrats d'interfaces inter-API (REST JSON ou MCP).
- FastAPI Pydantic est imposé pour valider strict le schéma des entrées asynchrones (via Uvicorn).

## Conséquences
- **Positives :**
  - **Scalabilité asymétrique :** Les routes couteuses (ex: `missions_api` chargeant DocumentAI) scalent de façon indépendante dans le Cloud.
  - **Auto-documentation :** OpenAPI génère directement la topologie visible pour l'agent IA.
  - **Async/Await natif :** L'IO HTTP ne bloque pas le thread central pour les appels IA.
- **Négatives :** 
  - Exigence absolue de propager les en-têtes (Token d'Authentification) lors des dialogues entre APIs.
  - Le déploiement s'alourdit.
- **Risques :** Redondance et double requête de réseau si `cv_api` et `missions_api` n'intègrent pas un "Composition Pattern".
