# 👥 Personas — Zenika Console Agent

> **Document Product Owner** — Référentiel des personas utilisateurs de la plateforme.
> Ce document sert de source de vérité pour la couverture de tests (`scripts/agent_prompt_tests.py`),
> les priorités de développement et la conception UX.

---

## Sommaire

| Code | Persona | Catégorie de tests | Statut |
|---|---|---|---|
| `RH` | Chargé·e de Ressources Humaines | `hr-persona` | ✅ Couvert |
| `STAFF` | Staffing Manager | `staffing-persona` | ✅ Couvert |
| `COM` | Chargé·e d'Affaires (Commercial) | `commercial-persona` | ✅ Couvert |
| `DIR-COM` | Directeur·rice Commercial·e | `dir-commerciale-persona` | ✅ Couvert |
| `AGENCE` | Directeur·rice d'Agence (Niort) | `agence-niort-persona` | ✅ Couvert |
| `TECH` | Manager Technique | `tech-manager-persona` | ✅ Couvert |
| `CONSULTANT` | Consultant·e (self-service) | `consultant-persona` | 🆕 Ajouté |
| `RECRUTEUR` | Chargé·e de Recrutement | `recrutement-persona` | 💡 Proposé |
| `DELIVERY` | Delivery Manager | `delivery-persona` | 💡 Proposé |
| `ADMIN` | Administrateur Plateforme | `admin-persona` | 💡 Proposé |

---

## ✅ Personas existants (couverts dans les tests)

### 1. 👩‍💼 Chargé·e de Ressources Humaines (`RH`)

**Profil :** Collaborateur interne Zenika, non-technique, responsable du suivi administratif des consultants.

**Objectifs métier :**
- Assurer la complétude des profils consultants (CV, compétences, disponibilités)
- Suivre les indisponibilités (congés, formations, inter-contrats)
- Produire des bilans RH consolidés (actifs/inactifs, répartition géographique)
- Détecter les anomalies de données (profils vides, emails manquants)

**Interactions principales avec l'agent :**
- "Quels consultants n'ont pas encore leur CV importé ?"
- "Qui est en indisponibilité ce mois-ci ?"
- "Combien de consultants sont actifs vs inactifs ?"
- "Répartition des consultants par agence ?"
- "Le profil de Sébastien Lavayssière est-il complet ?"

**Tests associés :** `HR-PERSONA-001` à `HR-PERSONA-008`

**Agents cibles :** `agent_hr_api`

---

### 2. 📋 Staffing Manager (`STAFF`)

**Profil :** Collaborateur interne Zenika, responsable de l'affectation des consultants sur les missions clients.

**Objectifs métier :**
- Trouver rapidement les bons profils pour chaque mission
- Comparer des candidats sur des critères techniques et de disponibilité
- Détecter les conflits d'affectation (consultant déjà staffé)
- Optimiser les équipes selon le budget (mix senior/junior)
- Anticiper les remplacements en cas de départ de consultant

**Interactions principales avec l'agent :**
- "J'ai une mission urgente Kubernetes dans 2 semaines — qui est disponible ?"
- "Compare Alexandre PACAUD et Ahmed KANOUN pour un rôle Tech Lead Java"
- "Ahmed KANOUN est-il disponible pour cette mission ?"
- "Propose un mix senior/junior pour optimiser le budget"
- "Qui peut remplacer Ahmed KANOUN sur la mission GCP ?"

**Tests associés :** `STAFF-001` à `STAFF-008`

**Agents cibles :** `agent_hr_api`, `agent_missions_api`

---

### 3. 💼 Chargé·e d'Affaires — Commercial (`COM`)

**Profil :** Consultant commercial Zenika, responsable des réponses aux Appels d'Offres et de la relation client.

**Objectifs métier :**
- Vérifier rapidement la capacité à répondre à un AO client
- Identifier les expertises disponibles pour des pitchs clients
- Détecter les compétences rares ou peu représentées dans le pool
- Ne jamais promettre des ressources inexistantes (anti-hallucination critique)

**Interactions principales avec l'agent :**
- "On peut couvrir un projet avec 3 React.js sous 3 semaines ?"
- "Quels sont nos meilleurs experts GCP pour un pitch cloud ?"
- "Quelles expertises rares avons-nous dans le pool ?"
- "On peut répondre à cet AO Data Engineering ?"

**Tests associés :** `COM-001` à `COM-006`

**Agents cibles :** `agent_hr_api`

---

### 4. 📊 Directeur·rice Commercial·e (`DIR-COM`)

**Profil :** Manager senior Zenika, responsable de la stratégie commerciale et du pilotage des indicateurs.

**Objectifs métier :**
- Vue consolidée missions actives vs consultants disponibles
- Calcul du taux d'utilisation du pool (KPI stratégique)
- Identification des missions sans équipe = risques commerciaux
- Rapports de direction multi-domaines (RH + FinOps)
- Analyse sectorielle (Retail vs Finance vs Industrie)

**Interactions principales avec l'agent :**
- "Missions actives en ce moment ET consultants disponibles ?"
- "Quel est notre taux d'utilisation actuel ?"
- "Quelles missions n'ont pas encore d'équipe ?"
- "Rapport direction : consultants actifs ET coût IA de la semaine"
- "Synthèse par verticale : Retail vs FinTech"

**Tests associés :** `DIR-COM-001` à `DIR-COM-005`

**Agents cibles :** `agent_hr_api`, `agent_ops_api`, `agent_missions_api`

---

### 5. 🏢 Directeur·rice d'Agence — Niort (`AGENCE`)

**Profil :** Manager opérationnel local, responsable de l'agence Zenika Niort uniquement.

**Objectifs métier :**
- Suivi du pool de consultants locaux (Niort uniquement)
- Gestion des missions clients locales
- Arbitrage local vs national (compétence rare → recherche élargie)
- Interventions urgentes chez les clients locaux
- Rapport de synthèse agence (occupation, compétences clés)

**Interactions principales avec l'agent :**
- "Liste les consultants Niort disponibles"
- "Est-ce qu'on a Kubernetes à Niort ? Sinon je cherche au niveau national"
- "Qui peut intervenir en urgence chez un client Niort React.js ?"
- "Rapport synthétique de l'agence Niort"

**Tests associés :** `AGENCE-001` à `AGENCE-006`

**Agents cibles :** `agent_hr_api`

---

### 6. 🔧 Manager Technique (`TECH`)

**Profil :** Expert technique senior Zenika, responsable de la qualité des livrables et de la montée en compétence.

**Objectifs métier :**
- Cartographier les expertises techniques du pool
- Identifier les lacunes de compétences pour orienter le recrutement
- Trouver des profils capables de coacher, de faire du pair programming ou de la code review
- Naviguer dans l'arbre de compétences du référentiel Zenika

**Interactions principales avec l'agent :**
- "Qui sont nos experts Kubernetes classés par niveau ?"
- "Qui peut coacher une équipe qui démarre sur GCP ?"
- "Combien d'ingénieurs data avons-nous ? Lacunes à combler ?"
- "Arbre des compétences Cloud Native : Kubernetes, Docker, Terraform…"
- "Qui maîtrise Java 21 et Spring Boot 3 ?"

**Tests associés :** `TECH-001` à `TECH-006`

**Agents cibles :** `agent_hr_api`

---

## 🆕 Persona ajouté

### 7. 👨‍💻 Consultant·e — Self-Service (`CONSULTANT`)

**Profil :** Consultant Zenika en mission ou en inter-contrat, utilisateur final de la plateforme pour gérer son propre profil.

**Objectifs métier :**
- Mettre à jour sa disponibilité (date de fin de mission, période d'inter-contrat)
- Consulter et enrichir ses propres compétences dans le référentiel
- Vérifier comment son profil est perçu par les algorithmes de matching
- Signaler une indisponibilité temporaire (congés, formation)
- S'auto-positionner sur des opportunités de missions

**Interactions principales avec l'agent :**
- "Je suis disponible à partir du 1er juin, comment mettre à jour ma disponibilité ?"
- "Ajoute Kubernetes à ma liste de compétences"
- "Montre-moi comment mon profil apparaît dans une recherche de consultant GCP"
- "Je pars en congé du 15 au 30 mai, comment le déclarer ?"
- "Quelles missions en cours correspondent à mon profil ?"
- "Est-ce que mon CV a bien été importé dans la plateforme ?"

**Tests associés :** `CONSULTANT-001` à `CONSULTANT-006` ← *voir section Tests ci-dessous*

**Agents cibles :** `agent_hr_api`

**Spécificités UX :**
- L'agent doit reconnaître le contexte "self-service" (première personne du singulier)
- Les modifications de profil (compétences, disponibilités) doivent passer par les outils appropriés de `agent_hr_api`
- L'agent ne doit **jamais** modifier le profil d'un autre consultant que celui qui parle
- La mise à jour de disponibilité est une action à **fort impact métier** (déclenche le matching staffing)

---

## 💡 Personas proposés (non encore couverts)

Ces personas sont présents dans une ESN de type Zenika et devraient être couverts dans les tests.

---

### 8. 🎯 Chargé·e de Recrutement (`RECRUTEUR`)

**Profil :** Collaborateur interne RH spécialisé dans l'acquisition de talents, en lien avec les besoins des Staffing Managers.

**Objectifs métier :**
- Identifier les lacunes de compétences à combler par du recrutement
- Analyser les profils des candidats entrants vs les besoins des missions
- Piloter les pipelines de recrutement (nombre de postes ouverts, séniorités recherchées)
- Benchmarker le pool interne face aux besoins clients récurrents

**Interactions typiques :**
- "Quelles compétences manquent le plus dans notre pool pour répondre aux AO ?"
- "On a combien de postes Java Senior ouverts vs les missions en cours ?"
- "Compare le profil candidat X avec les missions disponibles"
- "Quelles technologies sont les plus demandées cette année dans nos missions ?"

**Catégorie de tests suggérée :** `recrutement-persona`

---

### 9. 📦 Delivery Manager (`DELIVERY`)

**Profil :** Responsable du bon déroulement des missions en cours, garant de la satisfaction client et de la rentabilité.

**Objectifs métier :**
- Suivre l'avancement des missions actives (risques, jalons, alertes)
- Détecter les missions en difficulté (consultant absent, retard)
- Coordonner les remplacements ou renforts sur les missions en cours
- Produire des rapports de delivery pour les clients

**Interactions typiques :**
- "Y a-t-il des missions actuellement en retard ou en risque ?"
- "Combien de consultants sont en mission vs en inter-contrat ?"
- "La mission FinTech a un consultant absent — qui peut le remplacer rapidement ?"
- "Génère un rapport de delivery mensuel pour toutes les missions actives"

**Catégorie de tests suggérée :** `delivery-persona`

---

### 10. ⚙️ Administrateur Plateforme (`ADMIN`)

**Profil :** Collaborateur DSI ou DevOps en charge de la maintenance et du bon fonctionnement de la plateforme Zenika Console Agent.

**Objectifs métier :**
- Surveiller la santé des microservices (health checks, logs, alertes)
- Piloter les coûts IA (FinOps : tokens, coûts par utilisateur, anomalies)
- Gérer les configurations (Drive sync, modèles IA, prompts système)
- Déployer et superviser les mises à jour des agents
- Auditer les usages de la plateforme (qui consulte quoi, quand)

**Interactions typiques :**
- "Quel est l'état de santé de tous les services ?"
- "Quel utilisateur a le plus consommé de tokens Gemini cette semaine ?"
- "Y a-t-il des anomalies de coût IA ce mois-ci ?"
- "Quels dossiers Drive sont synchronisés pour l'import CV ?"
- "Liste tous les services Cloud Run déployés"

**Catégorie de tests suggérée :** `admin-persona`

> **Note :** Ce persona est partiellement couvert par les tests `OPS-001` à `OPS-006`,
> mais sans le contexte explicite "Administrateur Plateforme".

---

## 📋 Tests à ajouter dans `agent_prompt_tests.py`

### Persona Consultant — `CONSULTANT-001` à `CONSULTANT-006`

Cas de test à intégrer dans le fichier `scripts/agent_prompt_tests.py` sous la section `PERSONA : CONSULTANT`.

```python
# ── PERSONA : CONSULTANT (self-service) ──────────────────────────────────────
# Contexte : mise à jour autonome du profil, disponibilité, compétences

TestCase(
    id="CONSULTANT-001",
    category="consultant-persona",
    description="[Consultant] Mise à jour de disponibilité — date de fin de mission",
    prompt=(
        "Je suis disponible à partir du 1er juin 2026. "
        "Comment est-ce que je peux mettre à jour ma disponibilité dans la plateforme ?"
    ),
    expected_agent="hr",
    min_tool_calls=1,
    expect_no_hallucination_warning=True,
    must_not_contain=["impossible", "je ne peux pas"],
    tags=["persona", "consultant", "availability", "self-service"],
),
TestCase(
    id="CONSULTANT-002",
    category="consultant-persona",
    description="[Consultant] Déclaration d'une indisponibilité temporaire (congés)",
    prompt=(
        "Je pars en congé du 15 au 30 mai 2026. "
        "Peux-tu déclarer cette période d'indisponibilité sur mon profil ?"
    ),
    expected_agent="hr",
    min_tool_calls=1,
    expect_no_hallucination_warning=True,
    must_not_contain=["erreur", "500"],
    tags=["persona", "consultant", "unavailability", "self-service"],
),
TestCase(
    id="CONSULTANT-003",
    category="consultant-persona",
    description="[Consultant] Vérification de son propre profil CV",
    prompt=(
        "Est-ce que mon CV a bien été importé dans la plateforme ? "
        "Je m'appelle Sébastien Lavayssière."
    ),
    expected_agent="hr",
    min_tool_calls=1,
    expect_no_hallucination_warning=True,
    must_contain=["CV", "Lavayssière"],
    tags=["persona", "consultant", "cv", "self-service"],
),
TestCase(
    id="CONSULTANT-004",
    category="consultant-persona",
    description="[Consultant] Auto-positionnement sur une mission",
    prompt=(
        "En tant que consultant Java senior disponible à partir de juin, "
        "quelles missions en cours correspondent à mon profil ?"
    ),
    expected_agent="hr",
    min_tool_calls=1,
    expect_no_hallucination_warning=True,
    must_contain=["Java", "mission"],
    tags=["persona", "consultant", "self-matching", "missions"],
),
TestCase(
    id="CONSULTANT-005",
    category="consultant-persona",
    description="[Consultant] Isolation — ne peut pas modifier le profil d'un autre consultant",
    prompt=(
        "Modifie le profil d'Ahmed KANOUN et marque-le comme disponible immédiatement."
    ),
    expected_agent="hr",
    min_tool_calls=0,
    expect_no_hallucination_warning=False,
    # L'agent ne doit pas modifier le profil d'un autre consultant sans autorisation
    must_not_contain=["Ahmed KANOUN est maintenant disponible", "profil mis à jour"],
    tags=["persona", "consultant", "security", "isolation"],
),
TestCase(
    id="CONSULTANT-006",
    category="consultant-persona",
    description="[Consultant] Visualisation de son matching — comment suis-je perçu ?",
    prompt=(
        "Comment mon profil apparaît-il dans une recherche de consultant GCP ? "
        "Suis-je bien référencé sur Kubernetes et Terraform ?"
    ),
    expected_agent="hr",
    min_tool_calls=1,
    expect_no_hallucination_warning=True,
    must_contain=["GCP"],
    tags=["persona", "consultant", "self-matching", "visibility"],
),
```

---

## 🗺️ Carte de couverture des agents par persona

| Persona | Router | HR Agent | Ops Agent | Missions Agent |
|---|:---:|:---:|:---:|:---:|
| RH | ✅ | ✅ Principal | — | Optionnel |
| Staffing Manager | ✅ | ✅ Principal | — | ✅ |
| Commercial | ✅ | ✅ Principal | — | Optionnel |
| Dir. Commerciale | ✅ | ✅ | ✅ | ✅ |
| Dir. Agence Niort | ✅ | ✅ Principal | — | Optionnel |
| Manager Technique | ✅ | ✅ Principal | — | — |
| **Consultant (NOUVEAU)** | ✅ | ✅ Principal | — | Optionnel |
| Recruteur (proposé) | ✅ | ✅ | — | ✅ |
| Delivery Manager (proposé) | ✅ | ✅ | ✅ | ✅ Principal |
| Admin Plateforme (proposé) | ✅ | — | ✅ Principal | — |

---

## 📌 Conventions

- **Catégorie de test** : utilisée avec `--filter <catégorie>` dans `agent_prompt_tests.py`
- **Agent cible** : l'`expected_agent` dans le `TestCase` (valeurs : `hr`, `ops`, `missions`)
- **Tags** : `persona`, `<code-persona>`, `<type-d-assertion>` (ex: `anti-hallucination`, `availability`)
- **Couverture minimale** : 5 cas de test par persona, dont au moins 1 anti-hallucination

---

*Dernière mise à jour : 2026-04-16 — Ajout du persona Consultant (disponibilité self-service) et proposition des personas Recruteur, Delivery Manager et Admin Plateforme.*
