# frontend

## Rôle
SPA Vue.js 3 exposée via Nginx, interfaçant avec `agent_router_api` via un proxy `/api/`. Fournit l'interface utilisateur complète : chat avec l'agent, administration, profils consultants, dashboards FinOps et Data Quality.

## Type
🎨 Frontend (Vue.js 3 + Vite + Pinia)

## Structure
```
src/
├── views/           # Pages (lazy loading obligatoire)
├── stores/          # Pinia (chatStore.ts, uxStore.ts)
├── components/      # Composants réutilisables
├── router/          # Vue Router (guards JWT)
└── assets/          # Assets statiques
```

## Fichiers clés (vues principales)
| Fichier | Lignes | État |
|---|---|---|
| `src/views/AdminBulkImport.vue` | 1227 | ⚠️ Zone alerte |
| `src/views/PromptsAdmin.vue` | 1222 | ⚠️ Zone alerte |
| `src/views/Home.vue` | 1131 | ⚠️ Zone alerte |
| `src/views/DataQuality.vue` | 1114 | ⚠️ Zone alerte |

## Stores Pinia
| Store | Responsabilité |
|---|---|
| `chatStore.ts` | Historique de conversation, appels `/api/query`, parsing réponses agent |
| `uxStore.ts` | État UI global (sidebar, thème, notifications toast) |

## Variables d'environnement (build-time)
| Var | Valeur |
|---|---|
| `VITE_API_BASE_URL` | `/api` (proxy Nginx vers `agent_router_api`) |

## Charte graphique
- Zenika Red : `#E31937`
- Anthracite : `#1A1A1A`
- White : `#FFFFFF`
- Icônes : **`lucide-vue-next` exclusivement**
- Style : Glassmorphism + transitions douces

## Périmètre d'intervention agent
| Fichier | Agent peut modifier ? |
|---|---|
| `src/views/*.vue` | ✅ Oui — lazy loading `defineAsyncComponent` obligatoire |
| `src/components/*.vue` | ✅ Oui — charte graphique + lucide-vue-next |
| `src/stores/*.ts` | ✅ Oui — un store par domaine, logique HTTP dans le store |
| `src/router/index.ts` | ✅ Oui — guards JWT sur toute nouvelle route |
| `vite.config.ts` | ⚠️ Validation user requise |
| `nginx.conf` | ⚠️ Validation user requise |
| `Dockerfile` | ⚠️ Validation user requise |

## Gotchas connus
- Les réponses de l'agent (JSON structuré) sont parsées dans `chatStore.ts` — la logique `isEvaluationObj` distingue les listes de consultants des tableaux de compétences pour choisir le rendu adapté
- Le proxy Nginx `/api/` → `agent_router_api` — modifier `nginx.conf` sans test provoque un 502 en prod
- `Home.vue` est en zone alerte (1131L) — extraire les sous-composants avant d'ajouter des features
- Toutes les pages admin (`Admin*.vue`) nécessitent le rôle `admin` dans le JWT

## Dernière modification
2026-04-29 — v0.0.181 — Data Quality dashboard + UI improvements
