# Guide de Tests — Agents Zenika Platform

## Stratégie globale

Les agents IA ne se testent pas comme des APIs classiques. Il faut distinguer **3 niveaux** :

| Niveau | Ce qu'on teste | Outil |
|--------|---------------|-------|
| **Contrat MCP** | Les tools répondent au bon format | `pytest` dans chaque service |
| **Intégration comportementale** | L'agent appelle les bons tools dans le bon ordre | `agent_prompt_tests.py` |
| **Qualité des prompts** | La réponse finale est pertinente, non hallucinée | `agent_prompt_tests.py` + review manuelle |

---

## Lancer la suite de tests

```bash
# Installation des dépendances (une seule fois)
pip3 install httpx

# Test complet sur la plateforme de dev
python3 scripts/agent_prompt_tests.py

# Avec token explicite (si tu l'as déjà)
python3 scripts/agent_prompt_tests.py --token eyJhbGci...

# Filtrer par catégorie
python3 scripts/agent_prompt_tests.py --filter hr
python3 scripts/agent_prompt_tests.py --filter ops
python3 scripts/agent_prompt_tests.py --filter anti-hallucination

# Lancer un seul test précis
python3 scripts/agent_prompt_tests.py --id HR-006

# Mode verbose (voir les tool calls et extraits de réponse)
python3 scripts/agent_prompt_tests.py --verbose --filter routing

# Générer un rapport JSON
python3 scripts/agent_prompt_tests.py --output results/report_$(date +%Y%m%d).json
```

---

## Catégories de tests

### `routing` — Tests de routage du Router Agent
Valide que le `agent_router_api` dispatche vers le bon sous-agent.

**Ce qu'on vérifie :**
- Question RH → délégation à `agent_hr_api`
- Question Ops → délégation à `agent_ops_api`
- Question ambiguë → comportement déterministe

### `hr` — Tests de l'Agent RH
Valide les capacités de l'agent `agent_hr_api`.

**Ce qu'on vérifie :**
- Appel aux bons tools MCP (`list_users`, `search_best_candidates`, etc.)
- Absence du guardrail anti-hallucination (signe que des tools ont été appelés)
- Pertinence des données retournées

### `ops` — Tests de l'Agent Ops
Valide les capacités de `agent_ops_api` : health, logs, FinOps, Drive.

### `anti-hallucination` — Tests de robustesse
Pousse l'agent à halluciner et vérifie qu'il ne le fait pas (ou que le guardrail se déclenche).

**Questions types :**
- Profil consultant inexistant
- Mission inexistante
- Question hors scope (recette de cuisine...)

### `multi-domain` — Tests de décomposition
Valide que le Router décompose les requêtes bi-domaines en 2 appels séquentiels (Règle 2 du system prompt).

### `edge-cases` — Robustesse technique
- Prompt vide / très court
- Injection de prompt
- Prompt très long

### `finops` — Traçabilité des coûts
Vérifie que le BigQuery tracking fonctionne sur chaque appel.

---

## Interprétation des résultats

### ✅ Test passé
Toutes les assertions sont satisfaites.

### ❌ Test échoué
Au moins une assertion critique a échoué :
- `HTTP 5xx` → service down ou bug API
- `Trop peu de tool calls` → l'agent répond de mémoire (hallucination potentielle)
- `Mot interdit détecté` → l'agent a inventé de la donnée
- `Guardrail déclenché` → 0 tool appelé sur une question métier valide → revoir le system prompt

### ⚠️ Warning
Assertions non-bloquantes :
- Tool attendu non appelé (nom du tool peut avoir changé, à vérifier)
- Champ `data` absent (peut être normal selon la question)

---

## Ajouter un nouveau test

Dans `scripts/agent_prompt_tests.py`, ajouter un `TestCase` dans la liste `TEST_CASES` :

```python
TestCase(
    id="HR-009",                        # ID unique dans la catégorie
    category="hr",                       # catégorie
    description="Recherche par compétence Python",
    prompt="Quels consultants maîtrisent Python ?",
    expected_tools=["search_best_candidates"],  # tools attendus
    min_tool_calls=1,                    # minimum d'appels tools
    expect_no_hallucination_warning=True, # le guardrail NE doit PAS se déclencher
    must_contain=["Python"],             # mots attendus dans la réponse
    must_not_contain=["⚠️ ATTENTION"],   # mots interdits
    expect_data=True,                    # la réponse doit avoir un champ data
),
```

---

## Intégration CI/CD

Le script retourne un exit code non-zéro si des tests échouent, ce qui le rend compatible avec les pipelines CI.

```bash
# Dans deploy.sh, après le déploiement :
python3 scripts/agent_prompt_tests.py --filter routing --filter hr
if [ $? -ne 0 ]; then
    echo "❌ Tests d'intégration agents échoués — rollback"
    exit 1
fi
```

---

## Roadmap des améliorations

- [ ] **Score de similarité sémantique** : au lieu de chercher des mots-clés, utiliser un embedding pour comparer la réponse attendue avec la réponse obtenue
- [ ] **Tests de régression** : sauvegarder les réponses de référence (`golden responses`) et comparer à chaque déploiement
- [ ] **Dashboard Grafana** : injecter les métriques de test dans Prometheus (pass rate by category)
- [ ] **Tests de charge** : envoyer N requêtes simultanées et mesurer la dégradation (latence, hallucination rate)
- [ ] **LLM-as-judge** : utiliser un LLM séparé pour évaluer la qualité de la réponse (pertinence, factualité, ton Zenika)
