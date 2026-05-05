# ADR-0015 — Contrats d'interface inter-services : `shared/schemas/` Pydantic + Fail-Fast

- **Statut** : Accepté
- **Date** : 2026-05-05
- **Décideurs** : Équipe Platform Engineering
- **Services concernés** : Tous les services du monorepo (`*_api`, `agent_*`, `frontend`)
- **ADRs liés** : ADR-0001 (microservices), ADR-0002 (MCP), ADR-0003 (Zero-Trust)

---

## Contexte

La plateforme Zenika est composée de 14+ microservices qui s'appellent mutuellement via HTTP. Historiquement, chaque consommateur parsait les réponses JSON avec des appels `.get("clé", [])` — une pratique qui :

1. **Avale silencieusement les ruptures de contrat** : si l'API productrice renomme `"items"` en `"missions"`, le consommateur retourne `[]` sans erreur.
2. **Rend les régressions indétectables** : aucun test ne capture le problème avant la production.
3. **Empêche la traçabilité** : pas de log structuré, pas d'alerte sur la nature du problème.

**Cas déclencheur (2026-05)** : La clé `"missions"` a été renommée en `"items"` dans `cv_api` pour respecter le standard de pagination. `competencies_api` continuait de faire `.get("missions", [])` — silencieusement, tout scoring IA échouait avec `0 mission trouvée`.

---

## Décision

### 1. Source de Vérité Unique : `shared/schemas/`

Un dossier `shared/` à la racine du monorepo contient les **DTOs Pydantic** représentant les contrats d'interface entre services :

```
shared/
├── __init__.py
├── schemas/
│   ├── __init__.py
│   ├── pagination.py     # PaginationResponse[T] — enveloppe standard toutes listes
│   ├── missions.py       # MissionItem, MissionsResponse
│   ├── users.py          # UserItem, UsersResponse
│   ├── cv_profiles.py    # CvProfileItem, CvProfilesResponse
│   └── mcp.py            # McpToolResult — protocole MCP sidecar
└── tests/
    ├── __init__.py
    └── test_contract_schemas.py   # 17 tests de contrat — exécutés dans le CI
```

**Principe de conception** : les DTOs sont des **projections minimales** — ils contiennent uniquement les champs réellement consommés par les clients. Pas de copie des modèles producteurs.

### 2. Validation Fail-Fast : `model_validate()` obligatoire

Toute réponse HTTP paginée ou MCP doit être validée via `model_validate()` avec gestion explicite de `ValidationError` :

```python
# ✅ CORRECT — pattern obligatoire pour toute réponse inter-service
from pydantic import ValidationError
from shared.schemas.missions import MissionsResponse

res = await client.get(f"{CV_API_URL}/user/{user_id}/missions", headers=headers)
if res.status_code == 200:
    try:
        data = MissionsResponse.model_validate(res.json())
    except ValidationError as ve:
        logger.error(
            "[service] Rupture de contrat API missions",
            extra={"user_id": user_id, "error": str(ve), "raw_keys": list(res.json().keys())},
        )
        break  # ou return — stopper proprement
    missions.extend([m.model_dump() for m in data.items])

# ❌ INTERDIT — parsing silencieux
batch = res.json().get("items", [])   # Ne détecte pas le renommage de clé
missions.extend(batch)                # Retourne [] sans erreur → bug silencieux
```

### 3. Frontend : `parsePaginated<T>()`

Le helper TypeScript `frontend/src/utils/apiContract.ts` implémente l'équivalent pour le frontend :

```typescript
// ✅ CORRECT
import { parsePaginated } from '@/utils/apiContract';
const page = parsePaginated<Mission>(res.data, 'missions', '/user/1/missions');
// → page.items / page.total — log console.error() si clé absente

// Mode strict (pour les cas critiques)
const page = parsePaginated<Mission>(res.data, 'missions', '/user/1/missions', true);
// → lève ContractError si le contrat est brisé

// ❌ INTERDIT — parsing silencieux
const missions = res.data.missions || [];   // Ne détecte pas les ruptures de contrat
const missions = res.data?.items ?? [];     // Idem — retourne [] silencieusement
```

### 4. Build Docker depuis la racine (Root Context)

Pour que `shared/` soit accessible dans chaque image Docker, tous les services utilisent un **build depuis la racine du monorepo** :

```bash
# deploy.sh — contexte = racine du monorepo
docker build --platform linux/amd64 \
  -t "${IMAGE_NAME}:${TAG}" \
  -f "./${SERVICE}/Dockerfile" .   # point final = racine
```

Chaque Dockerfile copie explicitement `shared/` avant le code du service :

```dockerfile
FROM python:3.11-slim
COPY --from=builder /app/wheels /wheels
COPY shared/ /app/shared/    # ← schémas partagés
COPY <service>/ .             # ← code du service
```

### 5. Hash Sélectif : Rebuild automatique des consumers

`deploy.sh` intègre `shared/` dans le hash de **tous** les services. Toute modification de `shared/` déclenche le rebuild de l'ensemble des consumers :

```bash
check_shared_changed  # Compare shared/HASH avec le hash courant
# → si différent : expansion automatique vers tous les SHARED_CONSUMERS
save_shared_hash      # Mis à jour seulement si 0 build en échec
```

---

## Conséquences

### Positives ✅
- **Détection immédiate** : tout renommage de clé API lève une `ValidationError` loggée avec les clés reçues vs attendues.
- **Tests de régression automatiques** : `shared/tests/test_contract_schemas.py` détecte les ruptures **avant** le déploiement.
- **Traçabilité** : les logs structurés incluent `raw_keys` pour diagnostiquer rapidement.
- **Source unique** : modifier `MissionsResponse` met à jour tous les consommateurs en un commit.

### Négatives / Tradeoffs ⚠️
- **Couplage fort sur `shared/`** : un changement de DTO nécessite de mettre à jour tous les consommateurs simultanément. C'est voulu — c'est précisément ce qu'on veut forcer.
- **Context Docker légèrement plus grand** : compensé par un `.dockerignore` strict excluant `.git/`, `test_env/`, `platform-engineering/` → contexte < 100 MB.
- **Latence de build** : un changement de `shared/` rebuild ~14 services. Ce coût est acceptable et tracé dans le deploy summary.

---

## Cas spéciaux documentés

### Token JWT (`Authorization: Bearer ...`)
Les `res.json().get("access_token", ...)` dans `cv_api` ou `users_api` sont des **fallbacks intentionnels** sur des endpoints non-paginés. Ils sont annotés `# Fallback intentionnel` et ne doivent pas être migrés vers `model_validate()`.

### Endpoint `/missions/user/{id}/active`
L'endpoint retourne `{"active_missions": [...]}` — format non-standard non-paginé. Le `.get("active_missions", [])` est annoté `# Contrat intentionnel` et documenté ici.

---

## Règles d'évolution

1. **Tout nouveau endpoint retournant une liste** → wrapper dans `PaginationResponse[T]` et ajouter un DTO dans `shared/schemas/`.
2. **Tout renommage de champ** → mettre à jour le DTO **et** tous les consommateurs dans le même PR. Le build bloquera si `shared/HASH` change sans rebuild complet.
3. **Tout ajout de service consommateur** → s'abonner à `shared/` dans `SHARED_CONSUMERS` de `deploy.sh`.
4. **Tout endpoint non-paginé** → annoter `# Contrat intentionnel: <explication>` et ajouter ici en section "Cas spéciaux".
