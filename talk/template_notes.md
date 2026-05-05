# Notes d'Analyse du Template Zenika
**Template ID** : `1pxgzUdmW2Nx5G7mVj5tbP69fBaGblZ1v9EhZh_1lE8o`

## 1. Structure Générale
- **Slides existantes** : Le template contient initialement 34 slides d'exemples. Pour créer une présentation propre, il faudra d'abord supprimer ces 34 slides originaux de la copie.
- **Layouts (Mises en page)** : Le template propose une taxonomie très précise de layouts basés sur des codes couleurs et des usages.

## 2. Taxonomie des Layouts
Les layouts suivent une nomenclature claire : `<ID>. <Couleur> - <Type>`.
*Les Placeholders disponibles sont généralement `TITLE`, `SUBTITLE`, `BODY`, `SLIDE_NUMBER`.*

**Couleurs disponibles :**
- Yellow (10, 11, 12)
- Red (20, 21, 22, 61)
- Blue (30, 31, 32)
- Purple (40, 41)
- Green (50, 51, 52, 62)

**Types de slides :**
- `header` : Slide de titre/transition (Uniquement TITLE et SUBTITLE).
- `text` : Slide classique avec un grand bloc de texte (TITLE, SUBTITLE, BODY).
- `text+img` : Slide séparé avec un bloc texte et un espace pour une image (TITLE, SUBTITLE, BODY).
- `Blank` / `Blank with background` : Slides vides.
- `copyright bottom` / `customer story` : Formats spécifiques.

## 3. Stratégie de Génération
Puisque le plan (`presentation_plan.json`) contient principalement des tableaux de puces (`content`), il faut :
1. **Nettoyage** : Faire une copie du template et envoyer une requête `deleteObject` pour chaque slide d'exemple.
2. **Choix du Layout** : Utiliser un LLM (Gemini) pour choisir la meilleure couleur/type pour chaque slide du `presentation_plan.json` et lier chaque texte au bon placeholder.
   - Les titres de section -> `header`
   - Les listes à puces -> `text` (et on insérera les puces dans le `BODY`).
3. **Création** : Envoyer une série de `createSlide` avec les `layoutId` choisis.
4. **Injection** : Envoyer des requêtes `insertText` dans les bons objectIds pour remplir les placeholders.
