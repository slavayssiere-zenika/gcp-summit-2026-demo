# ADR-0014 — Pipeline d'import CV via Drive : statuts et contrôles opérationnels

- **Statut** : Accepté
- **Date** : 2026-04-22
- **Décideurs** : Équipe Platform Engineering
- **Services concernés** : `drive_api`, `cv_api`, `frontend` (DriveAdminPanel)

---

## Contexte

L'ingestion des CVs depuis Google Drive repose sur un pipeline asynchrone en plusieurs étapes :

1. `drive_api` scanne les dossiers configurés et découvre les fichiers
2. `drive_api` publie les fichiers dans Pub/Sub
3. `cv_api` reçoit les messages via push Pub/Sub et traite les CVs (LLM, compétences, missions)
4. `cv_api` notifie `drive_api` du résultat via `PATCH /files/{id}`

Chaque fichier est tracé dans la table `drive_sync_state` avec un champ `status` de type enum.
Le frontend (`DriveAdminPanel.vue`) expose des boutons de contrôle pour débloquer les états anormaux.

---

## Cycle de vie des statuts

```
                    ┌─────────────────────────────────────────────────┐
                    │              GOOGLE DRIVE                        │
                    │  Scan drive_api → fichier découvert              │
                    └────────────────────┬────────────────────────────┘
                                         │ POST /sync (drive_api)
                                         ▼
┌─────────┐    publish Pub/Sub   ┌──────────────┐
│ PENDING │ ──────────────────── │   QUEUED     │
│         │                      │              │
│ Prêt à  │                      │ Publié dans  │
│ envoyer │                      │ Pub/Sub, en  │
│ en P/S  │                      │ attente push │
└─────────┘                      └──────┬───────┘
     ▲                                  │ cv_api reçoit push Pub/Sub
     │                                  ▼
     │                         ┌──────────────────┐
     │                         │   PROCESSING     │
     │                         │                  │
     │                         │ cv_api en cours  │
     │                         │ (LLM + compét.   │
     │                         │  + missions)     │
     │                         └───────┬──────────┘
     │                                 │
     │              ┌──────────────────┼───────────────────────┐
     │              ▼                  ▼                        ▼
     │    ┌─────────────────┐  ┌──────────────┐    ┌──────────────────┐
     │    │  IMPORTED_CV    │  │    ERROR     │    │ IGNORED_NOT_CV   │
     │    │                 │  │              │    │                  │
     │    │ CV analysé,     │  │ Échec LLM,   │    │ Document non     │
     │    │ user créé,      │  │ timeout,     │    │ reconnu comme CV │
     │    │ compétences     │  │ 403, crash   │    │ (lettre de moti- │
     │    │ assignées       │  │ cv_api…      │    │  vation, etc.)   │
     │    └─────────────────┘  └──────┬───────┘    └──────────────────┘
     │                                │
     └────────────────────────────────┘
                   retry-errors → PENDING
```

### Détail de chaque statut

| Statut | Signification | État DB `last_processed_at` |
|---|---|---|
| `PENDING` | Découvert, prêt à être envoyé dans Pub/Sub lors du prochain `/sync` | Timestamp du reset |
| `QUEUED` | Message publié dans Pub/Sub, en attente de livraison push vers `cv_api` | Timestamp de la publication |
| `PROCESSING` | Message reçu par `cv_api`, ACK immédiat envoyé, pipeline en background task | Timestamp de l'ACK |
| `IMPORTED_CV` | Pipeline complet réussi : User créé/mis à jour, compétences et missions assignées, score IA déclenché | Timestamp fin de pipeline |
| `ERROR` | Le pipeline `cv_api` a échoué (LLM error, 403, crash). Détail dans `error_message` | Timestamp de l'échec |
| `IGNORED_NOT_CV` | `cv_api` a analysé le document et déterminé que ce n'est pas un CV (lettre de motivation, etc.) | Timestamp du rejet |

---

## Architecture du pipeline ACK immédiat

Depuis **2026-04-22**, le handler Pub/Sub dans `cv_api` utilise un ACK **immédiat** (< 1s) :

```
Pub/Sub push → handle_pubsub_cv_import
   │
   ├─ Validation OIDC + échange token (< 500ms)
   ├─ PATCH drive_api → PROCESSING
   ├─ background_tasks.add_task(_run_cv_pipeline_bg) ← pipeline LLM ici
   └─ return 202 {"status": "accepted"}  ← ACK Pub/Sub immédiat
```

**Pourquoi ?** L'algorithme *slow-start* de Pub/Sub calibre sa concurrence en fonction du temps de réponse de l'endpoint. Une réponse en 2 min → concurrence = 1-2. Une réponse en < 1s → concurrence = 10+.

**Tradeoff** : Pub/Sub n'assure plus le retry automatique (message déjà ACK). La durabilité est assurée par :
1. Le statut `PROCESSING` posé avant l'ACK → les "zombies" sont détectables
2. La Dead Letter Queue (DLQ) pour les messages ayant épuisé les 5 retries **avant** l'ACK

---

## Mécanisme de Retry

Pour les messages qui échouent **avant** l'ACK (validation OIDC échouée → retour 5xx), Pub/Sub retente automatiquement jusqu'à 5 fois. Après 5 échecs, le message est envoyé dans la **DLQ**.

Pour les échecs **après** l'ACK (dans la background task), l'état `ERROR` en base est le seul signal. Le replay est manuel via les boutons de l'Admin UI.

---

## Boutons de contrôle — Admin UI (`DriveAdminPanel.vue`)

### 1. 🔄 **Synchronisation** (`POST /api/drive/sync`)

**Quand l'utiliser** : Pour déclencher manuellement la publication dans Pub/Sub des fichiers en `PENDING`.

**Ce que ça fait** :
1. Scan Drive des dossiers configurés → nouveaux fichiers → insérés en `PENDING`
2. Tous les `PENDING` → publish Pub/Sub → passent en `QUEUED`

**Transition** : `PENDING` → `QUEUED`

**Visible** : Toujours (bouton principal de la section)

---

### 2. ⚡ **Forcer Déblocage** (`POST /api/drive/retry-errors?force=true`)

**Quand l'utiliser** : Quand des fichiers sont bloqués en `QUEUED` ou `PROCESSING` (zombies Pub/Sub — instance cv_api redémarrée, timeout, etc.).

**Ce que ça fait** :
1. Reset **immédiat** (sans attendre le seuil de 10 min) de **tous** les `QUEUED` et `PROCESSING` → `PENDING`
2. Appelle automatiquement `/sync` pour republier dans Pub/Sub
3. Met à jour `last_processed_at` pour réinitialiser le timer affiché en UI

**Transition** : `QUEUED` / `PROCESSING` → `PENDING` → (via sync) → `QUEUED`

**Visible** : Uniquement si `queued + processing > 0`

> **Note** : Sans `force=true`, `retry-errors` attend 10 minutes avant de considérer un `PROCESSING` comme zombie. Ce seuil est calibré pour ne pas interrompre un pipeline LLM en cours (durée typique : 1-5 min pour un CV).

---

### 3. 🔁 **Réessayer Tout** (Retry Errors) (`POST /api/drive/retry-errors`)

**Quand l'utiliser** : Quand des fichiers sont en `ERROR` après un échec du pipeline cv_api.

**Ce que ça fait** :
1. Reset de tous les `ERROR` → `PENDING` (avec `error_message=null`)
2. Reset des `QUEUED`/`PROCESSING` zombies (> 10 min) → `PENDING`
3. Appelle automatiquement `/sync` pour republier

**Transition** : `ERROR` → `PENDING` → (via sync) → `QUEUED`

**Visible** : Uniquement si `errorFiles.length > 0`

---

### 4. 🔶 **Rejouer DLQ** (`POST /api/drive/dlq/replay` + `POST /api/drive/sync`)

**Quand l'utiliser** : Quand des messages ont épuisé leurs 5 retries Pub/Sub et sont en Dead Letter Queue.

**Ce que ça fait** :
1. Pull de **tous** les messages de la subscription DLQ (`cv-import-events-dlq-sub-{env}`)
2. Extraction des `google_file_id` des payloads
3. Reset des `google_file_id` correspondants en base → `PENDING`
4. ACK de tous les messages DLQ (les supprime définitivement de la DLQ)
5. Appelle `/sync` pour republier dans le topic principal

**Transition** : Messages DLQ → `PENDING` → (via sync) → `QUEUED`

**Visible** : Seulement si `dlq.message_count > 0`

> **Note** : Les payloads illisibles (sans `google_file_id`) sont ACK'd (supprimés de la DLQ) mais ne peuvent pas être réinjectés — ils sont loggés avec un warning.

---

### 5. 🗑️ **Supprimer message DLQ** (`DELETE /api/drive/dlq/message`)

**Quand l'utiliser** : Pour supprimer un message DLQ individuel sans déclencher de replay (ex: fichier intentionnellement ignoré ou payload corrompu).

**Ce que ça fait** :
1. Stratégie 1 (rapide) : ACK direct via `ack_id` si fourni et encore valide (< 10 min)
2. Stratégie 2 (fallback) : Re-pull + match par `google_file_id` ou `pubsub_message_id` + ACK ciblé + NACK des autres

**Effet sur la DB** : Aucun — le statut drive_api du fichier est **inchangé**

**Transition** : Message DLQ → supprimé. Statut DB: inchangé.

---

### 6. 🔄 **Actualiser DLQ** (`GET /api/drive/dlq/status`)

**Ce que ça fait** :
- Pull sans ACK permanent (extend ack deadline à 600s pour stabilité)
- Croise les `google_file_id` avec `drive_sync_state` pour afficher les métadonnées
- Rafraîchi automatiquement toutes les 60s en polling silencieux (pour renouveler les ack_ids)

---

## Résumé des transitions par bouton

```
                    PENDING ←──── [Synchronisation] ← nouveaux fichiers Drive
                       │
                    QUEUED  │◄─── [Forcer Déblocage] (QUEUED/PROCESSING → PENDING → QUEUED)
                       │    │◄─── [Réessayer Tout]   (ERROR → PENDING → QUEUED)
                    PROCESSING   ◄─── [Rejouer DLQ]  (DLQ → PENDING → QUEUED)
                   ╱       ╲
            IMPORTED_CV   ERROR ←──── [Réessayer Tout]
                        IGNORED_NOT_CV  (pas de retry — rejet définitif)
```

---

## Zombie Detection

Un fichier est considéré "zombie" (processing fictif) si son statut reste `QUEUED` ou `PROCESSING` depuis plus de **10 minutes** sans transition vers `IMPORTED_CV` ou `ERROR`.

Causes typiques :
- Instance Cloud Run redémarrée après l'ACK Pub/Sub mais avant la fin du pipeline
- Crash de `cv_api` pendant la background task
- Bug non géré dans `_run_cv_pipeline_bg` sans catch final

La détection et le reset automatique des zombies sont effectués par :
- `POST /retry-errors` (seuil 10 min) — déclenché manuellement ou via Cloud Scheduler

---

## Décisions clés

| # | Décision | Justification |
|---|---|---|
| D1 | ACK Pub/Sub immédiat (< 1s) | Casse le slow-start → 10+ CVs traités en parallèle vs 1-2 |
| D2 | drive_api comme source de vérité du statut | Indépendant de Pub/Sub, consultable par le frontend en temps réel |
| D3 | Zombie threshold = 10 min (vs 30 min initial) | Pipeline LLM typique < 5 min ; 10 min = marge x2 suffisante |
| D4 | DLQ subscription dédiée | Capture les échecs avant ACK (OIDC invalide, 5xx répétés) sans les perdre |
| D5 | `IGNORED_NOT_CV` non retentable | Rejet définitif par décision LLM ; retry = gaspillage de quota Gemini |
