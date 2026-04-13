# ADR 0003 : Sécurité Zero-Trust et JWT Épars

## Statut
Accepté

## Contexte
La console, étant composée d'un tissu de services asynchrones Cloud Run, posait le défi de l'authentification et de l'autorisation d'un appel réseau circulant de service en service (ex: Agent -> Missions -> CV -> Users). Confier l'identité au Load Balancer uniquement n'était pas satisfaisant dans une vision "Zero-Trust" puisque toute exploitation d'un serveur métier interne pouvait déclencher un appel latéral ouvert et anonyme. De plus, l'isolation requérait un tracking des acteurs pour le modèle FinOps.

## Décision
- Application d'un paradigme **Zero-Trust interne**.
- Chaque service doit réclamer et valider cryptographiquement un Jeton JWT asymétrique (RSA) délivré par `users_api` au point d'entrée Frontend de l'utilisateur ou par le compte de service Google (Identity Tokens).
- La propagation est obligatoire : tout composant A appelant un composant B doit capturer `Authorization: Bearer <Token>` et le positionner statiquement (ou implicitement par un proxy de composition) dans la requête sortante `httpx`.
- Le token inclut l'appartenance (`roles`) et les droits pour limiter son exécution (Administrateur, RH, ou système).

## Conséquences
- **Positives :**
  - **Identité Auditable :** Les span de tracing OTel ou les écritures FinOps en base portent l'utilisateur certifié au cœur de l'infrastructure asynchrone.
  - Aucun périmètre réseau "protégé par magie" ; un tunnel interne corrompu se heurtera au manque de validateur cryptographique.
- **Négatives :** 
  - Surcharge de boilerplate dans le code Python : interdiction d'oublier de propager les `Headers` du client vers les composants avals.
- **Risques :** Expiration du Token (15m) lors de parcours longs asynchrones entrainant l'interruption des processus de bout de chaîne.
