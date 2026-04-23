# Workflow d'Audit UX/UI & Cohérence Documentaire (/analyse-ux-ui)

Ce workflow est conçu pour réaliser un audit complet de la conformité du frontend Vue.js avec les **Golden Rules Zenika**, l'accessibilité web (WCAG) et garantir la synchronisation parfaite entre les microservices déployés et les dashboards de documentation interne.

## Étapes de l'Audit

### 1. Audit d'Accessibilité (a11y)
- **Aria-Labels** : Vérifiez que TOUS les éléments cliquables (`<button>`, `<a>`, icônes interactives) possèdent un attribut `aria-label` descriptif. (Recherche : `grep -r "<button" frontend/src` pour cibler les éléments sans `aria-label`).
- **Contrastes** : Assurez-vous que le ratio de contraste du texte par rapport au fond respecte la norme WCAG 2.1 AA (4.5:1), en particulier lors de l'utilisation du Zenika Red (`#E31937`) ou sur fonds glassmorphism.

### 2. Cohérence UI (Standards Zenika)
- **Charte Graphique** : Validez l'usage strict du Zenika Red (`#E31937`), de l'Anthracite (`#1A1A1A`) et du Blanc (`#FFFFFF`). Vérifiez la présence des variables CSS (ex: `var(--zenika-red)`).
- **Iconographie** : Vérifiez que l'importation de `<svg>` bruts est évitée au profit exclusif de la librairie `lucide-vue-next`.
- **Glassmorphism** : Validez l'utilisation responsable et esthétique des modales ou panels nécessitant l'attribut CSS `backdrop-filter: blur(...)`.

### 3. Cohérence UX
- **Performance & Lazy Loading** : Vérifiez l'utilisation de `defineAsyncComponent` dans le routage de l'UI pour réduire le Time To Interactive (TTI), surtout concernant les composants lourds (`Views/Modals`).
- **Gestion d'État** : Vérifiez que chaque action asynchrone dispose d'un *loading state* (ex: boutons avec spinner) et d'un *error state* clair pour l'utilisateur.

### 4. Cohérence Technique de la Documentation Intégrée
Assurez-vous que l'UI de la Console Zenika reflète très exactement la topologie backend :

- **MCP Technical Registry** (`frontend/src/views/Registry.vue` et `agent_router_api/main.py`) :
  - Comparez les dossiers API/MCP locaux (`*_api`, `*_mcp`) avec la configuration `MCP_SERVICES_CONFIG` du backend, ainsi que le mapping des APIs dans le Registry frontend.
- **Documentation des Agents IA** (`frontend/src/views/AgentsDocs.vue`) :
  - Vérifiez la présence de chaque agent (ex: `Router`, `Agent HR`, `Agent Missions`, `Agent Ops`) dans le composant `AgentsDocs.vue`.
- **Specs & Manifestes API** (`frontend/src/views/Specs.vue`) :
  - Contrôlez la présence de chaque service sans exception dans `tabs: SpecTab[]`.

### 5. Accessibilité OpenAPI (`/docs`)
- **Validation Zero-Trust** : En vous référant aux Golden Rules, vérifiez que le `/docs` n'est pas entravé par la sécurité (les routes Swagger ne doivent pas avoir le validateur JWT) pour tous les services distants sur GCP. Vous pouvez observer l'instanciation de `FastAPI(docs_url="/docs")` dans les `main.py`.

---

**Instruction pour l'IA** : Pour déclencher ce Workflow, créez un artefact intitulé `ux_ui_analysis_report.md` et présentez les résultats de chaque section susmentionnée avec un focus sur les **violation**. Utilisez des diffs ou des listes d'actions concrètes pour que le développeur puisse immédiatement résoudre les points bloquants.
