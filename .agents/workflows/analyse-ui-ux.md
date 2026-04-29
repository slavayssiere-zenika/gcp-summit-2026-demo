---
description: Analyse complète de l'UX et de l'UI du frontend Vue.js (contraste WCAG, lisibilité, responsive) et proposition d'améliorations concrètes.
---

# Workflow : Analyse UX/UI Complète (/analyse-ui-ux)

// turbo-all

Ce workflow réalise un audit statique approfondi du frontend Vue.js (`frontend/src/`) sur trois axes : **contraste et accessibilité visuelle**, **lisibilité et typographie**, et **responsive design**. L'agent inspecte le code source (pas le navigateur, conformément à la règle §13 de AGENTS.md) et produit un rapport actionnable avec des diffs correctifs.

---

## Étape 1 : Inventaire du Système de Design

### 1.1 Variables CSS globales
Lire `frontend/src/style.css` (et tout fichier `*.css` / `*.scss` dans `frontend/src/assets/`) pour extraire :
- La palette de couleurs déclarée en variables CSS (`--zenika-red`, `--bg-primary`, `--text-primary`, etc.)
- Les tailles de police de base (`font-size`, `line-height`) sur `:root` et `body`
- Les breakpoints responsive déclarés (`@media` queries)

```bash
# Extraire toutes les variables CSS déclarées
grep -rn "^\s*--" frontend/src/style.css frontend/src/assets/ 2>/dev/null | head -60
```

### 1.2 Inventaire des vues et composants
Lire la liste complète des fichiers `.vue` dans `frontend/src/views/` et `frontend/src/components/` (déjà connus : 25 vues, 10 composants). Identifier les fichiers les plus volumineux (> 20 Ko) comme cibles prioritaires d'audit : `DataQuality.vue`, `AdminReanalysis.vue`, `Home.vue`, `PromptsAdmin.vue`, `Profile.vue`.

```bash
# Trier par taille décroissante
find frontend/src -name "*.vue" | xargs wc -l | sort -rn | head -15
```

### 1.3 Détection des variables CSS dupliquées (nouveau ⚠️)
Le projet définit des blocs `:root` dans **deux endroits distincts** : `style.css` et le `<style>` de `App.vue`. Des variables aux noms proches mais différents (`--color-text-secondary` vs `--text-secondary`) créent des incohérences silencieuses. Détecter les doublons :

```bash
# Lister toutes les variables déclarées dans les .vue ET style.css
grep -roh "--[a-z][a-z0-9-]*" frontend/src/ --include="*.vue" --include="*.css" | \
  sed 's|.*:||' | sort | uniq -d

# Comparer les blocs :root de style.css vs App.vue spécifiquement
echo "=== style.css ==="
grep -n "^\s*--" frontend/src/style.css
echo "=== App.vue ==="
grep -n "^\s*--" frontend/src/App.vue
```

> **Règle** : Toute variable présente dans `App.vue <style>` et dans `style.css` avec un nom différent doit être consolidée dans `style.css` et référencée via `var(--nom-unique)`.

---

## Étape 2 : Audit de Contraste (WCAG 2.1 AA)

### 2.1 Règle de référence
La norme **WCAG 2.1 AA** exige :
- Ratio **4.5:1** minimum pour le texte normal (< 18pt / < 14pt bold)
- Ratio **3:1** minimum pour le texte large (≥ 18pt ou ≥ 14pt bold) et les composants UI (bordures, icônes actives)

### 2.2 Extraction des couples texte/fond à risque

Rechercher les patterns suivants dans tous les fichiers `.vue` et `.css` :

```bash
# Couleurs hardcodées (non-variables) — risque contraste non maîtrisé
grep -rn "#[0-9a-fA-F]\{3,6\}" frontend/src/ --include="*.vue" --include="*.css" | grep -v "\.svg\|<!--" | grep "color\|background\|border" | head -40

# Texte sur fond glassmorphism (rgba avec alpha < 0.7 = fond semi-transparent problématique)
grep -rn "rgba(" frontend/src/ --include="*.vue" --include="*.css" | grep "background\|backdrop" | head -20

# Couleur Zenika Red utilisée comme fond (contraste texte blanc critique)
grep -rn "zenika-red\|#E31937\|#e31937" frontend/src/ --include="*.vue" | head -20
```

### 2.3 Vérification manuelle des couples critiques connus
Pour chaque occurrence trouvée, calculer le ratio via la formule W3C (luminance relative). Les couples à risque identifiés dans l'architecture Zenika :

| Couple | Ratio estimé | Statut WCAG AA |
|--------|:------------:|:--------------:|
| Texte blanc `#FFF` sur fond Zenika Red `#E31937` | ~4.0:1 | ⚠️ Borderline |
| Texte gris `#9CA3AF` sur fond anthracite `#1A1A1A` | ~4.6:1 | ✅ Conforme |
| Texte gris `#9CA3AF` sur glassmorphism `rgba(255,255,255,0.1)` | ~2.5:1 | ❌ Non conforme |
| Texte `#6B7280` sur fond blanc `#FFFFFF` | ~4.6:1 | ✅ Conforme |
| Placeholder input `#9CA3AF` sur `#F3F4F6` | ~2.4:1 | ❌ Non conforme |

### 2.4 Vérification des états disabled et placeholder
```bash
# Placeholders (souvent oubliés — ratio requis 4.5:1)
grep -rn "::placeholder\|placeholder" frontend/src/ --include="*.vue" --include="*.css" | grep "color" | head -15

# États disabled (ratio requis 3:1 pour signifier l'état)
grep -rn ":disabled\|disabled" frontend/src/ --include="*.vue" | grep "color\|opacity" | head -15
```

---

## Étape 3 : Audit de Lisibilité et Typographie

### 3.1 Taille de police minimale
La taille de police lisible minimale est **14px** pour le corps de texte, **12px** pour les labels secondaires. Rechercher les valeurs inférieures :

> **⚠️ Attention base mobile** : `style.css` définit `html { font-size: 14px }` sous `@media (max-width: 768px)`. Sur mobile, **1rem = 14px**. Donc :
> - `0.68rem` → **9.5px** ❌ (ex: `.dropdown-section-label` dans `App.vue`)
> - `0.75rem` → **10.5px** ❌
> - `0.85rem` → **11.9px** ⚠️ borderline
> - `0.9rem` → **12.6px** ✅ minimum toléré pour labels
> - `1rem` → **14px** ✅ minimum pour corps de texte

```bash
# Tailles de police < 14px hardcodées (px)
grep -rn "font-size:\s*[0-9]\{1,2\}px" frontend/src/ --include="*.vue" --include="*.css" | \
  awk -F: '{match($0,/[0-9]+px/,a); if(a[0]+0 < 14) print}' | head -20

# Tailles en rem problématiques sur base mobile 14px (< 0.9rem)
grep -rn "font-size:\s*0\.[0-8][0-9]*rem" frontend/src/ --include="*.vue" --include="*.css" | head -20

# Cas concret connu : .dropdown-section-label (0.68rem = 9.5px mobile)
grep -rn "0\.68rem\|0\.7rem\|0\.72rem\|0\.75rem" frontend/src/ --include="*.vue" --include="*.css" | head -10
```

### 3.2 Line-height et espacement
Un `line-height` inférieur à `1.5` nuit à la lisibilité des blocs de texte. Vérifier :
```bash
grep -rn "line-height:\s*[01]\.[0-4]" frontend/src/ --include="*.vue" --include="*.css" | head -15
```

### 3.3 Longueur des lignes (mesure de colonne)
Les colonnes de texte dépassant **75 caractères** par ligne réduisent la lisibilité. Inspecter visuellement les conteneurs sans `max-width` sur les blocs prose :
```bash
# Blocs de texte sans contrainte de largeur (absence de max-width dans les conteneurs de paragraphes)
grep -rn "<p\|<li\|<span" frontend/src/views/Help.vue frontend/src/views/AgentsDocs.vue | grep -v "class\|:class" | head -20
```

### 3.4 Hiérarchie des titres (H1 unique par vue)
```bash
# Vérifier qu'une seule balise <h1> (ou équivalent .text-4xl / .title-primary) existe par vue
grep -rn "<h1\b" frontend/src/views/ --include="*.vue"
grep -rn "text-4xl\|\.page-title\|\.main-title" frontend/src/views/ --include="*.vue" | head -20
```

### 3.5 Polices de caractères
Vérifier que la police déclarée dans `style.css` est chargée depuis Google Fonts (ou bundlée localement) et que le `font-family` de fallback est défini :
```bash
grep -rn "font-family\|@import.*fonts\|googlefonts" frontend/src/style.css frontend/index.html 2>/dev/null
```

### 3.6 Contraste dans les icônes et boutons d'action
```bash
# Boutons sans texte explicite (icônes seules sans aria-label)
grep -rn "<button\|<IconButton" frontend/src/ --include="*.vue" -A 2 | grep -v "aria-label\|:aria-label\|title" | grep "<button" | head -20
```

> **⚠️ Limitation grep** : Les dimensions déclarées dans `<style>` non-scoped (ex: `.logout-pill { width: 36px }`) ne sont pas rattachées à un sélecteur `button` dans la même ligne — le grep naïf les rate. Utiliser la commande ciblée suivante :

```bash
# Taille des zones cliquables < 44px — recherche dans les blocs <style> complets
# Cas connu : .logout-pill = 36x36px dans App.vue (sous le seuil WCAG 44px)
grep -rn "width:\s*[0-3][0-9]px\|height:\s*[0-3][0-9]px" frontend/src/ --include="*.vue" | head -20

# Vérifier les sélecteurs associés (btn, pill, icon, action)
grep -B5 -A1 "width:\s*3[0-9]px" frontend/src/App.vue frontend/src/components/ -r --include="*.vue" 2>/dev/null | head -30
```

> **Cas connu à corriger** : `.logout-pill` dans `App.vue` fait **36×36px**. La correction WCAG impose au minimum `min-width: 44px; min-height: 44px` ou une zone de clic étendue via `padding`.

---

## Étape 4 : Audit Responsive Design

### 4.1 Identification des breakpoints définis
Lire `frontend/src/style.css` pour identifier les breakpoints media queries. Comparer avec les conventions Tailwind/Bootstrap standards si utilisés. Les breakpoints Zenika attendus : `640px` (sm), `768px` (md), `1024px` (lg), `1280px` (xl).

```bash
grep -rn "@media" frontend/src/ --include="*.vue" --include="*.css" | grep -v "prefers-color-scheme\|prefers-reduced-motion" | sed 's/.*@media//' | sort -u | head -30
```

### 4.2 Layouts rigides (px fixes sur largeur)
Les largeurs fixées en `px` sur des conteneurs principaux sont un anti-pattern responsive :
```bash
# Widths fixes > 600px (non-flexibles)
grep -rn "width:\s*[6-9][0-9][0-9]px\|width:\s*[0-9][0-9][0-9][0-9]px" frontend/src/ --include="*.vue" | head -20

# Grilles sans responsive (grid-template-columns fixes sans @media)
grep -rn "grid-template-columns" frontend/src/ --include="*.vue" --include="*.css" | grep -v "repeat\|auto\|fr\b" | head -15
```

### 4.3 Navigation mobile
Vérifier que `App.vue` ou le composant de navigation contient un mécanisme de menu hamburger ou de collapse pour les petits écrans :
```bash
grep -rn "hamburger\|mobile-menu\|sidebar.*collapsed\|@media.*768\|sm:\|md:" frontend/src/App.vue frontend/src/components/ --include="*.vue" | head -20
```

### 4.4 Tables non-scrollables
Les tableaux sans `overflow-x: auto` sur leur conteneur cassent le layout mobile :
```bash
grep -rn "<table\b" frontend/src/ --include="*.vue" -B 3 | grep -v "overflow-x\|table-responsive" | grep "<table" | head -15
```

### 4.5 Flex/Grid sans fallback
```bash
# Flex sans direction column sur mobile
grep -rn "display:\s*flex\b" frontend/src/ --include="*.vue" | head -10
# Vérifier si ces conteneurs ont un @media associé changeant flex-direction
```

### 4.6 Images et médias
```bash
# Images sans max-width: 100% (débordement sur mobile)
grep -rn "<img\b" frontend/src/ --include="*.vue" | grep -v "max-width\|w-full\|class.*img" | head -15
```

---

## Étape 5 : Audit Accessibilité Complémentaire (a11y)

### 5.1 Focus visible (keyboard navigation)
```bash
# Absence de :focus styles (navigation clavier impossible)
grep -rn ":focus\|focus-visible\|outline" frontend/src/ --include="*.vue" --include="*.css" | head -20

# outline: none — ATTENTION aux faux positifs
# outline: none est ACCEPTABLE si le même bloc :focus/:focus-visible
# définit un box-shadow ou border-color alternatif visible.
# Exemple conforme dans App.vue :
#   .header-search input:focus { outline: none; box-shadow: 0 0 0 4px rgba(...) } ✅
# Exemple NON conforme :
#   button:focus { outline: none; } (sans alternative) ❌
grep -rn "outline:\s*none\|outline:\s*0" frontend/src/ --include="*.vue" --include="*.css" | head -15

# Vérifier si chaque occurrence a un box-shadow ou border compensatoire dans le même bloc
# (inspection manuelle requise — chercher le contexte autour de chaque hit)
grep -rn -A5 "outline:\s*none" frontend/src/ --include="*.vue" --include="*.css" | \
  grep -v "box-shadow\|border-color\|border:" | grep -B1 "}" | head -20
```

> **Règle** : Un `outline: none` sans `box-shadow` ou `border` alternatif dans le **même sélecteur `:focus`** est une violation WCAG 2.1 SC 2.4.7. Signaler uniquement les cas sans compensation visuelle.

### 5.2 Attributs ARIA
```bash
# Éléments interactifs sans aria-label (boutons icônes)
grep -rn "<button" frontend/src/ --include="*.vue" | grep -v "aria-label\|:aria-label" | wc -l

# Modales sans role="dialog" ou aria-modal
grep -rn "modal\|dialog\|overlay" frontend/src/ --include="*.vue" | grep -v 'role=\|aria-modal' | head -15

# Listes déroulantes sans aria-expanded
grep -rn "dropdown\|v-if.*open\|v-show.*open" frontend/src/ --include="*.vue" | grep -v "aria-expanded" | head -10
```

### 5.3 Messages d'état dynamiques (aria-live)
Les notifications toast, les spinners et les messages d'erreur doivent utiliser `aria-live="polite"` pour les lecteurs d'écran :
```bash
grep -rn "toast\|notification\|alert\|spinner\|loading" frontend/src/ --include="*.vue" | grep -v "aria-live\|role=\"alert\"\|role=\"status\"" | head -15
```

### 5.4 Attributs `alt` sur les images
```bash
grep -rn "<img" frontend/src/ --include="*.vue" | grep -v " alt=" | head -10
```

---

## Étape 6 : Cohérence UI (Standards Zenika)

### 6.1 Charte graphique
```bash
# Couleurs hors-charte (ni rouge Zenika, ni anthracite, ni blanc, ni gris système)
grep -rn "#[0-9a-fA-F]\{6\}" frontend/src/ --include="*.vue" | grep -v "#E31937\|#1A1A1A\|#FFFFFF\|#F3F4F6\|#6B7280\|#9CA3AF\|#111827\|#374151\|#4B5563\|#D1D5DB\|#E5E7EB\|#EF4444\|#10B981\|#F59E0B\|#3B82F6" | head -20
```

### 6.2 Iconographie (lucide-vue-next exclusif)
```bash
# Usage de SVG bruts inline (interdit — utiliser lucide-vue-next)
grep -rn "<svg\b" frontend/src/ --include="*.vue" | grep -v "<!--\|lucide\|icon-component" | head -20

# Import depuis des librairies non-standard
grep -rn "from '@heroicons\|from 'vue-feather\|from 'font-awesome" frontend/src/ --include="*.vue" --include="*.ts" | head -10
```

### 6.3 Glassmorphism responsable
```bash
grep -rn "backdrop-filter\|glass\|blur(" frontend/src/ --include="*.vue" --include="*.css" | head -15
```

### 6.4 Anti-patterns CSS : `!important` (nouveau ⚠️)
Les déclarations `!important` brisent la cascade CSS et rendent impossible la surcharge responsive. Elles signalent souvent une mauvaise architecture de styles.

```bash
# Compter le nombre total de !important dans le frontend
echo "Nombre total de !important :"
grep -rn "!important" frontend/src/ --include="*.vue" --include="*.css" | grep -v "<!--" | wc -l

# Lister tous les cas pour review manuelle
grep -rn "!important" frontend/src/ --include="*.vue" --include="*.css" | grep -v "<!--" | head -30
```

> **Règle** : Zéro `!important` est l'objectif. Chaque occurrence doit être justifiée (override de librairie tierce uniquement). Les `!important` dans des composants maison (`.swagger-link`, `.hide-on-mobile`) doivent être refactorisés avec une spécificité CSS correcte ou des classes utilitaires dédiées.

---

## Étape 7 : Sécurité UI & Cohérence des Rôles (RBAC)

Vérifier que les actions sensibles ou réservées à l'administration sont correctement protégées dans l'interface (sécurité par l'UI, dite "Guardrails visuels"). Un utilisateur "normal" ne doit pas voir des boutons "Supprimer" ou "Admin" non fonctionnels.

### 7.1 Détection des gardes de rôles
Identifier les patterns de vérification de rôle utilisés dans le projet (`isAdmin`, `isRh`, `role === 'admin'`).
```bash
# Identifier les composants contenant des directives de rôle
grep -rn "v-if=\".*admin\|v-if=\".*rh\|isAdmin\|isRh" frontend/src/ --include="*.vue" | head -20
```

### 7.2 Actions sensibles non protégées
Vérifier si des boutons liés à des actions destructrices ou administratives sont présents sans garde de rôle visible dans le template.
```bash
# Rechercher des boutons d'actions sensibles sans v-if associé au rôle
grep -rn -B1 -A1 "Supprimer\|Delete\|Reset\|Clear\|Admin" frontend/src/ --include="*.vue" | grep -v "v-if=\".*admin\|role\|isRh\|isAdmin" | grep "<button" | head -20
```

### 7.3 Analyse Product Owner (PO) de l'UX des permissions
Au-delà de simplement cacher une action non autorisée via `v-if`, vérifier si ce choix offre le meilleur parcours utilisateur (User Journey). Dans de nombreux cas, masquer entièrement un bouton crée de la confusion ("Où est passée cette fonctionnalité ?").
- **Actions principales** : Faut-il plutôt afficher le bouton en état désactivé (`:disabled="!isAdmin()"`) avec une infobulle (tooltip) expliquant : *"Action réservée aux administrateurs"* ?
- **Pages restreintes** : Si l'utilisateur accède à une page où il n'a aucun droit, y a-t-il un *Empty State* (état vide) clair et bienveillant ("Vous n'avez pas accès à ce module") plutôt qu'une page blanche ou une erreur brute ?
- **Découverte (Discoverability)** : Le fait de montrer une fonctionnalité verrouillée (avec un cadenas ou grisée) informe l'utilisateur de son existence et de la structuration de la plateforme.

```bash
# Rechercher des boutons disabled liés au rôle (Bonne pratique UX pour la discoverability)
grep -rn ":disabled=\".*admin\|:disabled=\".*rh\|!isAdmin\|!isRh" frontend/src/ --include="*.vue" | head -15

# Rechercher des infobulles explicatives sur les droits
grep -rn "title=\".*admin\|title=\".*droit\|tooltip" frontend/src/ --include="*.vue" | grep -i "admin\|droit\|permission" | head -15
```

> **Règle PO** : Lors de l'audit, évaluez le choix UX entre *cacher* et *désactiver*. Les actions de destruction pure (ex: supprimer) doivent être cachées (`v-if`). Les fonctionnalités majeures ou points d'entrée de modules devraient être visibles mais désactivés avec une explication (`disabled` + `title`) pour ne pas désorienter l'utilisateur.

---

## Étape 8 : Génération du Rapport et Plan d'Action

À l'issue des étapes 1 à 7, créer un artefact **`ui_ux_analysis_report.md`** avec la structure suivante :

### Structure du Rapport

```markdown
# Rapport d'Audit UX/UI — [Date]

## Synthèse Exécutive
Score global UX/UI : [X/100]
| Axe | Score | Statut |
|-----|:-----:|:------:|
| Contraste WCAG AA | X/20 | 🔴/🟡/🟢 |
| Lisibilité & Typographie | X/20 | 🔴/🟡/🟢 |
| Responsive Design | X/20 | 🔴/🟡/🟢 |
| Accessibilité a11y | X/20 | 🔴/🟡/🟢 |
| Sécurité UI & RBAC | X/20 | 🔴/🟡/🟢 |

## Violations Bloquantes (P0 — Priorité critique)
[Liste des violations WCAG AA strictes — contraste < 3:1, boutons sans aria-label]

## Améliorations Importantes (P1 — À corriger ce sprint)
[Violations lisibilité, tables non-scrollables, outline: none]

## Suggestions UX (P2 — Backlog)
[Améliorations responsive, line-height, max-width prose]

## Plan de Correction Détaillé

### [Composant X] — [Type de violation]
**Fichier** : `frontend/src/views/X.vue`
**Problème** : [Description précise]
**Correction** :
\`\`\`diff
- color: #9CA3AF; /* ratio 2.4:1 — NON CONFORME */
+ color: #6B7280; /* ratio 4.6:1 — CONFORME WCAG AA */
\`\`\`

## Variables CSS Manquantes (à ajouter dans style.css)
\`\`\`css
:root {
  /* À ajouter pour centraliser les couleurs conformes */
  --text-secondary: #6B7280;    /* ratio 4.6:1 sur blanc */
  --text-disabled: #9CA3AF;     /* réservé aux éléments disabled uniquement */
  --focus-ring: 2px solid #E31937;
}
\`\`\`
```

## Variables CSS Orphelines

Vérifier que les variables déclarées dans `style.css` sont effectivement utilisées dans les composants. Les variables non référencées constituent de la dette CSS silencieuse.

```bash
# Détecter les variables CSS déclarées mais jamais utilisées (orphelines)
while IFS= read -r var; do
  count=$(grep -r "var($var)" frontend/src/ --include="*.vue" --include="*.css" 2>/dev/null | wc -l)
  [ "$count" -eq 0 ] && echo "ORPHAN: $var"
done < <(grep -oh "--[a-z][a-z0-9-]*" frontend/src/style.css | sort -u)
```

> Les variables orphelines candidates à suppression dans `style.css` (vérifiées sur le code actuel) : `--space-1`, `--space-3`, `--shadow-md`, `--radius-xl`, `--radius-full`. À confirmer avec la commande ci-dessus avant suppression.
```

### Règle de scoring
- **P0** : violation WCAG AA stricte (contraste < 3:1, bouton cliquable sans label) → **-5 pts chacune**
- **P1** : bonne pratique manquante (`outline: none` sans compensation, table sans overflow, aria-live manquant, `!important` hors librairie tierce) → **-2 pts chacune**
- **P2** : amélioration UX non bloquante (line-height, taille police borderline, variable orpheline) → **-1 pt chacune**

---

> **⚠️ RAPPEL RÈGLE §13 AGENTS.md** : Ce workflow n'utilise PAS le `browser_subagent`. Toute l'analyse est statique (code source uniquement). Pour valider visuellement les corrections, le développeur doit lancer `npm run dev` et inspecter manuellement avec les outils de contraste du navigateur (ex: Chrome DevTools → Accessibility → Color Contrast).
