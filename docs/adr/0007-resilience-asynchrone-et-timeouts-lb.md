# ADR 0007 : Résilience Asynchrone et Gestion Sécurisée des Timeouts

## Statut
Accepté

## Contexte
Avec l'intégration de technologies gourmandes telles que LLM Generative AI (Gemini) et la lecture OCR de PDF lourds (Document AI), l'application a rapidement été mise sous pression au niveau des contraintes temporelles des protocoles réseaux asynchrones. De fortes latences causaient l'écroulement des services non par manque d'entrainements CPU, mais par de multiples coupures intermédiaires (`httpx.ReadTimeout`, `502 Bad Gateway`).

## Décision
- **Couche Cloud (Load Balancer) :** Le plafond systémique implicite de 30 secondes a été réécrit manuellement dans Terraform à `timeout_sec = 300` pour l'entièreté des composants internes (`lb-internal.tf`) et externes interrogeables via Internet (`lb.tf`).
- **Couche Applicative (Delegation Python) :** Les dépendances SDK synchrones Google fournies bloquant les co-routines asynchrones ont été encapsulées nativement avec `await asyncio.to_thread()`, repoussant le travail dans un thread-pool externe pour maintenir Uvicorn hautement en vie, même sous la contrainte réseau la plus ardue.
- **Comportement Réseau Apparié :** Limitation globale de la tolérance du constructeur `httpx.AsyncClient` ajusté sur le même barème que l'architecture (`300.0s`), tout en remplaçant au niveau du protocole HTTP les appels en cascades temporelles par un patron multi-threads : `asyncio.gather()`.

## Conséquences
- **Positives :**
  - Alignement déterministe entre le code Client et la Topologie réseau. Les tâches lourdes comme DocumentAI peuvent sereinement aboutir de bout-en-bout.
- **Négatives :** 
  - La mise en sursis trop longue d'une requête inaboutie gèle des connecteurs, augmentant le coût au temps CPU des nœuds Cloud Run sans-état.
- **Risques :** Le Thread-pool de Python risque d'être saturé si un grand nombre de requêtes requérant le `process_document` sont réceptionnées simultanément par conteneur.
