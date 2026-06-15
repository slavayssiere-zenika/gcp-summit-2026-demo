# Rapport SRE — 2026-06-11 16:16

**Source** : `prompts_api` & `monitoring_mcp` (Cloud Logging) | **Total Anomalies** : 15

## 🤖 Erreurs Applicatives (Agents)

*Aucune erreur d'agent active (prompts).* 

## 🚨 Erreurs HTTP 5xx Récentes (Infrastructure / Pipelines)

### [1] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:03:55.904177+00:00` | **Trace ID** : `9dc701d48d90423bbd01650766ab1dbc`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [2] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:03:46.923521+00:00` | **Trace ID** : `16693f9e3c25395b35343f3bd05ce447`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [3] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:03:45.905712+00:00` | **Trace ID** : `df3266a0a1647ef14c68cdf2f5da88cf`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [4] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:03:37.909139+00:00` | **Trace ID** : `ae6ce12604dac2fb4c68cdf2f5da8016`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [5] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:03:35.891494+00:00` | **Trace ID** : `d5cf869bcd0afa53a2f7cc7d575381ab`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [6] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:02:51.843221+00:00` | **Trace ID** : `28cf82f8cc797a9526ac5be807779c5a`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [7] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:02:43.796672+00:00` | **Trace ID** : `7881e11f00687a50429b259f58a16366`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [8] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:02:42.732006+00:00` | **Trace ID** : `c5fbc1e1f19dc4c7429b259f58a163f3`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [9] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:02:41.823256+00:00` | **Trace ID** : `8347251de0d7a362429b259f58a16bff`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [10] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:02:27.752087+00:00` | **Trace ID** : `337736d53522965e83e818b7558b23e5`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [11] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:01:57.676084+00:00` | **Trace ID** : `e6ce3ef4cef25f29af2bbe05e709484d`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [12] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:01:55.651485+00:00` | **Trace ID** : `6cb7d230bd36d675fa7871c2475a7682`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [13] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:01:50.607704+00:00` | **Trace ID** : `2b62e9fb4bfb7ce9af2bbe05e7094662`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [14] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:01:45.612347+00:00` | **Trace ID** : `2e4b72c5e9988c107b66401a3cfaa225`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

### [15] `cv-api-prd` — HTTP 500 sur `POST https://prd.zenika.slavayssiere.fr/pubsub/import-cv`

**Date** : `2026-06-11T13:01:41.658846+00:00` | **Trace ID** : `b1462d6d09e0e19f7b66401a3cfaa673`

**Message d'erreur / Contexte** :
```
Erreur HTTP 5xx
```

## Plan de remédiation

> Analyse des erreurs ci-dessus et propositions de correction.

#### `cv-api-prd` — Échec d'authentification sur pubsub/import-cv

**Cause probable** : Validation de token JWT échouée lors du push Pub/Sub.
Vérifier si SECRET_KEY est vide suite à une purge de sécurité (main.py) ou si les secrets
ne correspondent pas entre users-api et cv-api.

**Actions** :
- Importer la SECRET_KEY depuis `shared.auth.jwt` au lieu de `os.getenv`.
- Relancer la remédiation en remettant en `PENDING` les fichiers impactés.
