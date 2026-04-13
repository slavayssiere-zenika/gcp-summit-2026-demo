# ADR 0008 : Serveur Frontend SPA Vue.js

## Statut
Accepté

## Contexte
L'interface de l'agent requiert une interactivité poussée (chat en mode streaming asynchrone, micro-animations, gestion contextuelle de l'historique et des métadonnées comme les "thoughts" de l'Agent) ainsi que plusieurs tableaux de bord décisionnels pour l'administration RH et missions.
Un rendu serveur traditionnel (ex: Django ou Jinja) forcerait chaque question IA à rafraichir entièrement le contexte du navigateur web, cassant la fluidité attendue des expériences dites de génération dynamique.

## Décision
- Architecture **Single Page Application (SPA)** propulsée par le Framework moderne **Vue.js 3** (Composition API).
- Les assets construits (HTML/JS/CSS statiques) perdent leur notion de route via un routeur `vue-router` en History Mode.
- Le déploiement ne s'effectue pas sur un serveur de calcul NodeJS, mais repose sur **un simple Container NGINX** (en version `unprivileged`) agissant tant comme un distributeur de fichiers statiques que comme un **Reverse Proxy** masquant `/api` pour router le trafic de la SPA vers l'orchestrateur de l'Agent de façon intra-réseau.
- Le design s'appuie sur une esthétique minimaliste via des choix "Vanilla CSS" assumés (`Glassmorphism`, `Lucide Icons`).

## Conséquences
- **Positives :**
  - Chargement instantané: une fois téléchargée, l'UI navigue en local memory limitant les transferts de réseau aux stricts payloads JSON des appels REST.
  - La SPA est encapsulée de la même façon que les microservices backend, ce qui lui permet d'être balancée par Cloud Run comme un service banal.
- **Négatives :** 
  - Effort requis pour gérer les erreurs CORS : bien que le Nginx mitige cela par du proxying.
  - Le référencement (SEO) est affaibli, mais cette application est intrinsèquement privée et sécurisée.
- **Risques :** Si des paquets ou des ressources trop lourdes sont compilés (`bundle size`), le client subira un temps d'initialisation désagréable.
