---
description: Génère les données de test (Agences, CVs, Utilisateurs, Missions) pour la démo du GCP Summit avec attente d'ingestion.
---

Voici les étapes strictes à suivre pour l'exécution du workflow de génération de fausses données de démo GCP Summit :

### Pré-requis : Lecture des credentials

Ce workflow nécessite `ADMIN_PASSWORD` et `GCLOUD_BIN`. Ces valeurs sont lues automatiquement depuis `.antigravity_env`.

// turbo
```bash
[ -f .antigravity_env ] && cat .antigravity_env || echo "ANTIGRAVITY_ENV_NOT_FOUND"
```

Si le fichier **n'existe pas**, afficher ce message et **s'arrêter** :

```
❌ Fichier .antigravity_env manquant. Crée-le une fois depuis ton terminal :

  echo "GCLOUD_BIN=$(which gcloud)" > .antigravity_env
  echo "ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=admin-password-dev)" >> .antigravity_env

Ce fichier est gitignore — tes credentials ne seront pas commités.
```

Si `ADMIN_PASSWORD` est présent, procéder à l'étape suivante.

### Étape 1 : Lancement de l'orchestrateur de données

Le script lit automatiquement `.antigravity_env` pour `ADMIN_PASSWORD` et `GCLOUD_BIN`.
Il effectue un **health check** des services avant de démarrer. S'il y a un service unhealthy, il s'arrête immédiatement.

Le script est 100% **idempotent** : il ignorera les CVs et missions déjà créés.

// turbo
```bash
ADMIN_PASSWORD='<ADMIN_PASSWORD>' GCLOUD_BIN='<GCLOUD_BIN>' \
  python3 scripts/generate_gcp_summit_data.py
```

> **Durée estimée** : 10-30 min (génération Drive + ingestion CV + analyse IA missions).
> Un spinner de polling affiche la progression en temps réel.

### Étape 2 : Vérification post-génération

Vérifie que les données sont bien ingérées avant de lancer les tests :

// turbo
```bash
ADMIN_PASSWORD='<ADMIN_PASSWORD>' PYTHONPATH=/tmp/py_deps \
  /opt/homebrew/bin/python3.13 -c "
import httpx, os, json
base = 'https://dev.zenika.slavayssiere.fr'
pwd = os.environ['ADMIN_PASSWORD']
tok = httpx.post(f'{base}/api/auth/login', json={'email':'admin@zenika.com','password':pwd}).json()['access_token']
h = {'Authorization': f'Bearer {tok}'}
users = httpx.get(f'{base}/api/users/', headers=h).json()
missions = httpx.get(f'{base}/api/missions/missions', headers=h).json()
print(f'✅ Consultants : {users[\"total\"]}')
print(f'✅ Missions    : {len(missions)}')
"
```

### Étape 3 : Informer l'utilisateur

Une fois le script terminé sans erreur :
- ✅ Les agences (Saumur, Sèvres, Bizanos, Paris) ont leurs CVs sur Drive
- ✅ Les consultants sont ingérés et leurs compétences analysées par Gemini
- ✅ Les missions sont créées et leurs équipes staffées

L'environnement est prêt pour `/analyse-prompt`.
