# Spécifications Techniques : Platform Engineering

Ce module gère le déploiement et le cycle de vie **dynamique et isolé** de nos différents environnements de test / pré-production / production de la **Zenika Console**. 
L'isolation entre les environnements se fait via l'usage natif de la variable `terraform.workspace`.

## Approche et Spécificités Architecturales

### 1. Script d'Orchestration Automatisé (`manage_env.py`)
Un wrapper Python sur-couche la complexité du workflow Terraform natif.
- **Dry-run :** `python manage_env.py plan --env [ENV]` évalue sans impacter.
- **Gestion des workspaces :** Le script interroge, bascule ou crée un nouveau "Workspace Terraform" selon le paramètre fourni (dev, uat, prd). Cela assure implicitement que l'état stocké sur GCS gère des isolats parfaits (ex : `env.d/dev/default.tfstate`).
- **Gestion intelligente de Destruction :** Les éléments sensibles du DNS et l'obtention des certificats SSL (qui nécessitent parfois du temps ou doivent survivre à un redéploiement) ont le flag `prevent_destroy = true`. Lors d'un `manage_env.py destroy`, le script "éjecte" astucieusement ces ressources de son `state` afin de détruire le reste sans échouer, et se charge de les ré-importer au prochain déploiement de cet environnement.

### 2. Réseau & Sécurité Ciblée
- **Cloud Armor / WAF :** Le Load Balancer de l'environnement est protégé contre le flood en amont via une security-policy (modèle Rate-Limiting : 1000 connexions/min).
- **Private Services Access (VPC) :** Pour durcir l'infrastructure, la base de données AlloyDB ne dispose **d'aucune IP Publique**. Elle est accessible localement par les Cloud Run grâce au `vpc_access.network_interfaces` (Direct VPC egress), rendant toutes communications BDD strictement intérieures au sous-réseau.

### 3. Compute (Cloud Run) - Le "Sidecar Pattern"
Tous les processus applicatifs sont hébergés sur des instances Cloud Run invisibles depuis l'extérieur (`INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`).

**Particularité Majeure :** Pour factoriser les instances et lier directement un microservice à son interface RAG, l'Agent MCP tourne sous la forme d'un **Sidecar (Multi-Container Cloud Run)** aux coté du conteneur API.
- `container[0] "api"` : Héberge l'API standard exposant le port `8080`. Se charge des extractions vers AlloyDB et des injections depuis Secret Manager.
- `container[1] "mcp"` : Héberge le connecteur Model Context Protocol appelant implicitement la logique locale (`http://localhost:8080`) au sein du même node CPU/RAM.

### 4. Routing "API Gateway" (External HTTPS Load Balancer)
N'utilisant pas Nginx, tout le routage par `path`/chemin est intégré as-code au Load Balancer L7 applicatif via le bloc `google_compute_url_map` et les `Serverless NEGs`.
- Le DNS (ex: `dev.slavayssiere-zenika.com`) pointe vers l'IP Publique globale.
- **Règles :** Tout préfixe typique (`/auth/*`, `/items-api/*`, etc) est capté, réécrit via la stratégie `route_action.url_rewrite`, puis distribué au bucket NEG Cloud Run approprié. Les autres flux atterrissent intrinsèquement sur le bucket de frontend unifié GCS.

### 5. Composants Applicatifs Complémentaires
- **Observabilité :** L'écosystème Grafana / Tempo / Loki utilise ses backends en stockage froid au sein de pures buckets GCS dynamiques.  
- **Secrets IAM :** Les Cloud Run consomment dynamiquement les dernières `versions` de secrets encapsulées plus tôt par l'étape du Bootstrapping. Un *Service Account* dédié est provisionné et apposé à chaque cloud run, permettant de verrouiller finement les privilèges.
