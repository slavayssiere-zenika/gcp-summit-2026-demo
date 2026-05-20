---
description: Analyse complète de l'UX, de l'UI, de l'Accessibilité et de la Réactivité du frontend Vue.js (contraste WCAG, lisibilité, responsive, micro-interactions, fuites mémoire Vue 3) et proposition d'améliorations concrètes.
---

# Workflow : Analyse UX/UI & Accessibilité Complète (/analyse-ui-ux)

// turbo-all

Ce workflow réalise un audit statique approfondi et outillé du frontend Vue.js (`frontend/src/`) sur quatre axes fondamentaux : **contraste et accessibilité (WCAG 2.1 AA)**, **performance de rendu et réactivité Vue 3**, **lisibilité et responsive design**, et **micro-interactions (Design Émotionnel)**. L'agent inspecte le code source et exécute un script d'audit automatisé de structure (pas de navigateur, conformément à la règle §13 de AGENTS.md) puis produit un rapport actionnable.

---

## Étape 1 : Inventaire & Dépendances de Design

### 1.1 Variables CSS globales & Résolution des conflits :root
Lire `frontend/src/style.css` (et tout fichier `*.css` / `*.scss` dans `frontend/src/assets/`) pour extraire :
- La palette de couleurs déclarée en variables CSS (`--zenika-red`, `--bg-primary`, etc.)
- Les tailles de police de base (`font-size`, `line-height`) sur `:root` et `body`
- Les breakpoints responsive déclarés (`@media` queries)

```bash
# Extraire toutes les variables CSS déclarées
grep -rn "^\s*--" frontend/src/style.css frontend/src/assets/ 2>/dev/null | head -60
```

Le projet définit parfois des blocs `:root` dans **deux endroits distincts** : `style.css` et le `<style>` de `App.vue`. Des variables aux noms proches mais différents créent des incohérences silencieuses. Détecter les doublons de déclaration de variables :

```bash
# Lister toutes les déclarations de variables de manière robuste (se terminant par un deux-points)
grep -roh "^\s*--[a-z0-9-]*:" frontend/src/ --include="*.vue" --include="*.css" | \
  sed 's/://g; s/^\s*//' | sort | uniq -d
```

### 1.2 Inventaire des vues et composants
Lire la liste complète des fichiers `.vue` dans `frontend/src/views/` et `frontend/src/components/`. Identifier les fichiers les plus volumineux (> 20 Ko) comme cibles prioritaires d'audit : `DataQuality.vue`, `AdminReanalysis.vue`, `Home.vue`, `PromptsAdmin.vue`, `Profile.vue`.

```bash
# Trier par taille décroissante
find frontend/src -name "*.vue" | xargs wc -l | sort -rn | head -15
```

---

## Étape 2 : Audit de Réactivité & Rendu Vue.js 3

### 2.1 Anti-patterns de réactivité (Props destructurées)
En Vue 3 Composition API (Script Setup), destructurer directement les props (ex : `const { user } = defineProps(...)`) brise la réactivité. L'UI ne se met plus à jour lors des mutations de données.
```bash
# Détecter les destructurations directes de defineProps
grep -rn "const {.*} = defineProps" frontend/src/ --include="*.vue"
```
*Correction standard* : Utiliser `toRefs(props)` ou accéder aux valeurs via `props.user`.

### 2.2 Fuites de mémoire et listeners non nettoyés
L'usage de `addEventListener` globaux (`window` ou `document`) sans appel correspondant à `removeEventListener` dans le hook `onUnmounted` provoque d'importantes fuites de mémoire.
```bash
# Détecter les écouteurs d'événements globaux
grep -rn "window\.addEventListener\|document\.addEventListener" frontend/src/ --include="*.vue" --include="*.ts"

# S'assurer de la présence du hook de nettoyage
grep -rn "onUnmounted\|onBeforeUnmount" frontend/src/ --include="*.vue"
```

### 2.3 Clés de boucle instables (`:key`)
Utiliser l'index de boucle (`:key="index"`) sur un `v-for` contenant des éléments dynamiques (tri, suppression, insertion) force Vue à ré-instancier le DOM inutilement. Cela dégrade les performances UX et casse le focus des inputs.
```bash
# Détecter les v-for utilisant l'index comme clé
grep -rn "v-for=" frontend/src/ --include="*.vue" | grep "index\|idx" | grep -v "key="
```

---

## Étape 3 : Audit Accessibilité & Formulaires (WCAG 2.1 AA)

### 3.1 Règle de référence de contraste
La norme **WCAG 2.1 AA** exige :
- Ratio **4.5:1** minimum pour le corps de texte normal (< 18pt / < 14pt bold)
- Ratio **3:1** minimum pour le texte large (≥ 18pt ou ≥ 14pt bold) et les composants interactifs (bordures, icônes)

```bash
# Couleurs hardcodées (non-variables) — risque contraste non maîtrisé
grep -rn "#[0-9a-fA-F]\{3,6\}" frontend/src/ --include="*.vue" --include="*.css" | grep -v "\.svg\|<!--" | grep "color\|background\|border" | head -40

# Texte sur fond glassmorphism (rgba avec alpha < 0.7 = fond semi-transparent à risque)
grep -rn "rgba(" frontend/src/ --include="*.vue" --include="*.css" | grep "background\|backdrop" | head -20
```

### 3.2 Accessibilité des formulaires et liaisons labels/inputs
Chaque `<input>`, `<textarea>` et `<select>` doit être lié explicitement à un élément `<label>` via un `id` correspondant pour être vocalisable par les lecteurs d'écran.
```bash
# Rechercher les inputs sans ID (qui ne peuvent donc pas être liés à un label)
grep -rn "<input" frontend/src/ --include="*.vue" | grep -v "id=" | grep -v "type=\"hidden\""
```

### 3.3 Liens d'évitement (Skip links)
Sur une application à barre latérale complexe comme la Console Zenika, la présence d'un lien d'évitement invisible permettant de sauter la navigation et d'aller directement au contenu principal au clavier est requise.
```bash
# Vérifier la présence de la classe de lien d'évitement
grep -rn "skip-link\|skip-to-content" frontend/src/App.vue
```

### 3.4 États disabled et placeholders
```bash
# Placeholders (ratio de contraste requis : 4.5:1)
grep -rn "::placeholder\|placeholder" frontend/src/ --include="*.vue" --include="*.css" | grep "color" | head -15

# États disabled (ratio requis : 3:1 pour signifier l'inactivité sans masquer l'élément)
grep -rn ":disabled\|disabled" frontend/src/ --include="*.vue" | grep "color\|opacity" | head -15
```

---

## Étape 4 : Audit de Lisibilité et Typographie

### 4.1 Taille de police minimale et base mobile
La taille minimale lisible pour le corps de texte est **14px** (ou **1rem** sur mobile base 14px), et **12px** (**0.85rem**) pour les labels secondaires.
```bash
# Tailles de police < 14px hardcodées (px)
grep -rn "font-size:\s*[0-9]\{1,2\}px" frontend/src/ --include="*.vue" --include="*.css" | \
  awk -F: '{match($0,/[0-9]+px/,a); if(a[0]+0 < 14) print}' | head -20

# Tailles de police en rem problématiques sur mobile (< 0.85rem)
grep -rn "font-size:\s*0\.[0-7][0-9]*rem" frontend/src/ --include="*.vue" --include="*.css" | head -20
```

### 4.2 Hauteur de ligne (`line-height`) et longueur de ligne
Un `line-height` inférieur à `1.5` sur les blocs de texte nuit à la lecture. Les colonnes dépassant **75 caractères** fatiguent l'œil (absence de `max-width` sur les conteneurs de prose).
```bash
grep -rn "line-height:\s*[01]\.[0-4]" frontend/src/ --include="*.vue" --include="*.css" | head -15
```

### 4.3 Taille physique des zones cliquables (WCAG 2.5.5)
Les éléments interactifs (boutons, icônes, liens) doivent présenter une zone de clic d'au moins **44×44px** pour être facilement sélectionnables sur mobile ou par des utilisateurs souffrant de tremblements.
```bash
# Identifier les hauteurs/largeurs de boutons/pills trop petites (< 44px) dans les <style>
grep -rn "width:\s*[0-3][0-9]px\|height:\s*[0-3][0-9]px" frontend/src/ --include="*.vue" | head -20
```

---

## Étape 5 : Audit Responsive & Fallbacks Résilients

### 5.1 Breakpoints et layouts rigides (Largeurs fixes en px)
Les largeurs fixées en `px` (ex: `width: 800px`) sur les conteneurs principaux cassent le responsive.
```bash
# Largeurs fixes absolues > 480px
grep -rn "width:\s*[4-9][0-9][0-9]px\|width:\s*[0-9][0-9][0-9][0-9]px" frontend/src/ --include="*.vue" | head -20
```

### 5.2 Cumulative Layout Shift (CLS)
L'absence de dimensions explicites sur les ressources médias (`<img>` sans `width` et `height`) provoque des sursauts désagréables et dégradent le score de stabilité visuelle de l'UX.
```bash
# Détecter les images sans taille explicite
grep -rn "<img" frontend/src/ --include="*.vue" | grep -v "width=" | grep -v "height="
```

### 5.3 Mouvements réduits
Vérifier la présence de media queries désactivant ou adoucissant les transitions pour les utilisateurs préférant des mouvements réduits.
```bash
grep -rn "prefers-reduced-motion" frontend/src/ --include="*.css" --include="*.vue"
```

---

## Étape 6 : Micro-interactions & Design Émotionnel

### 6.1 Skeleton Screens & Loading States
Vérifier si l'application met en place des squelettes de chargement progressifs sur les composants lourds (`Profile.vue`, `DataQuality.vue`) pour apaiser la perception du temps d'attente utilisateur.
```bash
find frontend/src -name "*Skeleton*" -o -name "*Loader*"
```

### 6.2 Empty States qualitatifs
Chaque rendu conditionnel de liste (`v-if="items.length"`) doit comporter une clause `v-else` structurée proposant un message explicite, une illustration, et un bouton d'action.
```bash
grep -rn "v-if=" frontend/src/views/ --include="*.vue" -A 10 | grep -E "v-else|length === 0|length == 0"
```

---

## Étape 7 : Exécution de l'Audit Automatisé Outillé (AST)

Pour éviter les limitations et faux-positifs des regex bash sur des fichiers multi-lignes, exécutez le script d'audit automatisé centralisé. Ce script analyse l'AST HTML des templates Vue ainsi que les variables CSS orphelines.

```bash
# Lancer le script d'audit statique UX/UI
python3 scripts/audit_templates.py
```

---

## Étape 8 : Sécurité UI & Cohérence des Rôles (RBAC)

Vérifier que les actions sensibles ou d'administration sont protégées par des guardrails d'UI.
- **Règle PO (Product Owner)** : Les actions destructrices (ex: Supprimer) doivent être masquées (`v-if`). Les actions de navigation majeure ou d'accès à des modules doivent être affichées sous forme désactivée (`:disabled="!isAdmin"`) avec une infobulle explicative (`title`) pour ne pas désorienter l'utilisateur et guider son parcours (Discoverability).

```bash
# Détecter les boutons désactivés par rôle (discoverability)
grep -rn ":disabled=\".*admin\|:disabled=\".*rh\|!isAdmin\|!isRh" frontend/src/ --include="*.vue" | head -15
```

---

## Étape 9 : Cohérence Frontend ↔ MCP (Traçabilité technique)

Vérifier que chaque widget d'interface déclenchant une action IA est correctement câblé à un store Pinia gérant les erreurs, et que le store communique avec un tool MCP actif de l'agent.

```bash
# 1. Stores sans gestion d'erreur try/catch sur les appels IA
grep -rn "/query\|/api/agent" frontend/src/stores/ --include="*.ts" -A 5 | grep -v "catch\|error\|try\|finally" | grep -B3 "}" | head -30

# 2. Détection des variables CSS orphelines (dette CSS style.css)
# Le script python scripts/audit_templates.py réalise cette vérification de manière exhaustive
```

---

## Étape 10 : Génération du Rapport d'Audit & Plan d'Action

À l'issue de l'audit statique et de l'exécution du script, créer l'artefact **`ui_ux_analysis_report.md`** :

### Barème de Scoring du Rapport
* **P0 : Violation Bloquante (Priorité critique)** $\rightarrow$ **-5 pts chacune**
  * Violation WCAG AA de contraste strict (< 3:1).
  * Bouton interactif sans texte et sans `aria-label` ou `title`.
  * Input de formulaire orphelin (sans ID/label associé).
  * Faille de sécurité UI (absence de garde de rôle sur action d'administration).
* **P1 : Amélioration Importante (À corriger rapidement)** $\rightarrow$ **-2 pts chacune**
  * `outline: none` sur focus sans compensation visuelle alternative (`box-shadow` ou `border`).
  * Destruction de réactivité Vue 3 (destructuration directe de `defineProps`).
  * Utilisation de `:key="index"` sur une boucle dynamic réordonnable.
  * CLS potentiel (images/médias sans hauteur/largeur explicite).
  * Absence d'état alternatif Empty State soigné sur les structures de listes.
* **P2 : Suggestion UX (Backlog & Confort)** $\rightarrow$ **-1 pt chacune**
  * Taille de police inférieure aux seuils sur mobile (< 12px label, < 14px corps).
  * Line-height insuffisant (< 1.5 sur les paragraphes).
  * Variable CSS orpheline.
  * Absence de transitions fluides sur les volets ou chargements.

> **⚠️ RAPPEL CONFORMITÉ §13 AGENTS.md** : Ce workflow réalise uniquement un audit statique du code source. Pour valider visuellement les corrections et inspecter les rendus, le développeur doit lancer `npm run dev` localement et utiliser les outils de contraste de Chrome/Firefox DevTools.
