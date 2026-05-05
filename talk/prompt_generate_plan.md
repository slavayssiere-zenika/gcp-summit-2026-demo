# Prompt de génération du Plan de Présentation (JSON)

Copiez-collez ce prompt dans l'interface de votre LLM (Gemini, ChatGPT, Claude) ou utilisez-le dans vos scripts pour générer automatiquement le fichier `presentation_plan.json` à partir de n'importe quel résumé de talk.

---

```text
Tu es un expert en conception de présentations techniques et un "Slide Designer" chevronné. 
Mon objectif est de générer le plan détaillé d'une présentation qui sera ensuite injecté automatiquement dans un template Google Slides d'entreprise (Zenika).

Voici le sujet ou le brouillon de ma présentation concernant le projet Gen-Skillz en production, les points clés à aborder sont les suivants (un par chapitre):
- Une explication fonctionnelle du projet (as a product owner / user perspective)
- L'utilisation de l'IA pour les pipelines de taxonomie et d'analyse des CVs (as a data scientist / ML engineer perspective)
- L'architecture multi-agents (as an architect)
- Les défis de la qualité de donnée (as a data engineer)
- L'architecture cloud dans GCP
- Une explication technique de comment on le déploie avec 'manage_env'
- L'utilisation de l'IA pour développer (avec Antigravity)

Chaque chapitre contiendra ÉNORMÉMENT de slides (5 à 8 slides par chapitre, soit une quarantaine de slides au total). Plutôt que de surcharger une slide avec du texte, crée de multiples slides pour bien décortiquer chaque concept technique. 
Par exemple :
- Pour l'IA, crée une slide pour décrire les pipelines, une pour les choix FinOps (Vertex AI Batch), une autre pour le design des prompts.
- Pour les agents, crée une slide pour décrire le protocole A2A, une autre pour le protocole MCP, une autre pour la gestion des droits et la propagation JWT.
Chaque slide doit aborder un sous-sujet hyper précis, mais le texte sur la slide doit rester lisible.
L'auditoire est très technique, on est sur des développeurs et des architectes. Il faut rentrer dans tous les détails techniques, y compris les choix d'architecture, les technologies utilisées, les défis rencontrés et les solutions mises en place.
Le ton doit être dynamique, engageant et passionné. Il faut éviter le ton professoral, on est entre collègues qui partagent leur expérience.

IMPORTANT ANTI-HALLUCINATION : Tu as accès au contexte technique complet du projet "test-open-code" en dessous (AGENTS.md, README.md). 
Tu ne dois inventer AUCUN outil, AUCUN agent, AUCUNE technologie. Tous les détails (noms des microservices, flux d'authentification JWT, scripts comme manage_env.py, le modèle de base de données, etc.) doivent être EXACTEMENT tirés de la documentation du projet test-open-code fournie.

Ta mission est de structurer ce contenu en un JSON strict, optimisé pour un rendu visuel dynamique, tout en étant irréprochable techniquement.

RÈGLES DE CONCEPTION DES SLIDES :
1. "title" : Doit être percutant et descriptif techniquement (max 70 caractères).
2. "subtitle" : Une phrase d'accroche technique approfondie pour contextualiser la slide.
3. "content" : Un tableau contenant 2 à 4 points clés (bullet points) maximum. Les phrases doivent être DIRECTES, CONCISES et techniques, sans fioritures. L'objectif n'est pas d'avoir des slides lourdes ("Death by PowerPoint"), mais d'avoir BEAUCOUP de slides. Chaque slide cible un sous-sujet très spécifique (ex: un slide juste pour `pgvector`, un juste pour `httpx`, un juste pour `manage_env`). Cite les noms de fichiers et APIs.
4. "speaker_notes" : Le script complet de ce que je dois dire à l'oral pendant cette slide.
5. "slide_type" : Choisis impérativement l'une de ces valeurs :
   - "cover" : Pour l'unique slide de lancement / titre de la présentation.
   - "chapter" : Pour introduire un nouveau chapitre ou une nouvelle partie (transition).
   - "text" : Pour les slides de contenu standard (liste à puces).
   - "text_image" : Pour une slide séparée en deux avec un visuel généré par IA.
   - "customer_story" : Pour mettre en avant un cas concret ou un retour d'expérience.
6. "preferred_color" : Alterne intelligemment entre ces couleurs pour donner du rythme : "Red", "Blue", "Green", "Purple", "Yellow". Ne mets jamais deux slides de la même couleur à la suite.
7. "image_prompt" : UNIQUEMENT pour les slides de type "text_image". Rédige un prompt détaillé en anglais décrivant l'illustration à générer avec Imagen 3 (ex: "A futuristic data center with neon blue lights, cyberpunk style").
8. ANTI-FORMATTAGE : Ne génère AUCUN tiret cadratin ("—") et AUCUN emoji/smiley dans l'ensemble du texte généré.

FORMAT DE SORTIE OBLIGATOIRE (STRICTEMENT JSON) :
Tu dois uniquement retourner un objet JSON valide avec cette structure exacte (sans balises markdown autour si possible) :

{
  "title": "Le titre global de la présentation",
  "slides": [
    {
      "slide_number": 1,
      "slide_type": "cover",
      "preferred_color": "Red",
      "title": "Titre de la présentation",
      "subtitle": "Sous-titre percutant",
      "speaker_notes": "Ce que je dis à l'oral pour introduire le sujet..."
    },
    {
      "slide_number": 2,
      "slide_type": "text_image",
      "preferred_color": "Blue",
      "title": "Défi de la donnée",
      "subtitle": "Qualité et scalabilité",
      "content": [
        "Point clé 1",
        "Point clé 2"
      ],
      "image_prompt": "A data engineer working on a glowing holographic interface, cinematic lighting",
      "speaker_notes": "L'enjeu principal de la donnée..."
    }
    // ... ajouter les autres slides ici pour CHAQUE chapitre
  ],
  "metadata": {
    "keywords": ["mot1", "mot2"],
    "technologies": ["tech1", "tech2"]
  }
}
```
