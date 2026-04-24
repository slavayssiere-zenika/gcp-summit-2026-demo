#!/usr/bin/env python3
"""
Script one-shot — à supprimer après exécution.
Insère les validateurs de format UI et les cas de test ui-format dans agent_prompt_tests.py.
"""
import re

TARGET = "scripts/agent_prompt_tests.py"

# ─── Validateurs ──────────────────────────────────────────────────────────────

VALIDATORS = '''

# ---------------------------------------------------------------------------
# Validateurs de Format UI (Frontend Integration)
# Ces validators verifient que les donnees retournees par l'agent sont dans
# le format attendu par les composants Vue.js (CloudRunLogsViewer, DebugPromptCard).
# Source: frontend/src/stores/chatStore.ts -> isCloudRunLogs() + extractDebugPrompt()
# ---------------------------------------------------------------------------

def validate_cloudrun_logs_data(data: Any) -> list[str]:
    """
    Verifie que les donnees retournees par l\'agent ops pour une demande de logs
    sont compatibles avec le composant CloudRunLogsViewer.vue.

    Contrat attendu par isCloudRunLogs() dans chatStore.ts :
      - data est une liste
      - chaque element a : timestamp (str ISO 8601) + cloud_run_service (str)
      - chaque element a au moins l\'un de : severity, message

    Source: frontend/src/stores/chatStore.ts -> isCloudRunLogs()
            frontend/src/components/agent/CloudRunLogsViewer.vue
    """
    errors = []
    if data is None:
        return [_err("data", "data est None - aucun log retourne")]

    if not isinstance(data, list):
        return [_err("data", f"Attendu list pour CloudRunLogsViewer, got {type(data).__name__}")]

    if len(data) == 0:
        return []

    for i, entry in enumerate(data[:10]):
        path = f"data[{i}]"
        if not isinstance(entry, dict):
            errors.append(_err(path, f"Attendu dict, got {type(entry).__name__}"))
            continue

        # Champ obligatoire : timestamp
        if "timestamp" not in entry:
            errors.append(_err(f"{path}.timestamp", "Champ obligatoire manquant"))
        elif not isinstance(entry["timestamp"], str):
            errors.append(_err(f"{path}.timestamp",
                               f"Doit etre str ISO 8601, got {type(entry['timestamp']).__name__}"))
        else:
            if "T" not in entry["timestamp"] and "+" not in entry["timestamp"]:
                errors.append(_err(f"{path}.timestamp",
                                   f"Format ISO 8601 attendu, got \'{entry['timestamp'][:30]}\'"))

        # Champ obligatoire : cloud_run_service
        if "cloud_run_service" not in entry:
            errors.append(_err(f"{path}.cloud_run_service", "Champ obligatoire manquant"))
        elif not isinstance(entry["cloud_run_service"], str):
            errors.append(_err(f"{path}.cloud_run_service",
                               f"Doit etre str, got {type(entry['cloud_run_service']).__name__}"))
        elif len(entry["cloud_run_service"]) == 0:
            errors.append(_err(f"{path}.cloud_run_service", "cloud_run_service ne peut pas etre vide"))

        # Au moins l\'un de severity ou message doit etre present
        if "severity" not in entry and "message" not in entry:
            errors.append(_err(path, "Au moins l\'un de \'severity\' ou \'message\' doit etre present"))

        # Si message est un dict (structured log), verifie les champs HTTP standards
        if isinstance(entry.get("message"), dict):
            msg = entry["message"]
            if "http.status_code" in msg and not isinstance(msg["http.status_code"], (int, float)):
                errors.append(_err(f"{path}.message[\'http.status_code\']", "Doit etre numerique"))
            if "http.duration_s" in msg and not isinstance(msg["http.duration_s"], (int, float)):
                errors.append(_err(f"{path}.message[\'http.duration_s\']", "Doit etre numerique"))
            valid_methods = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")
            if "http.method" in msg and msg["http.method"] not in valid_methods:
                errors.append(_err(f"{path}.message[\'http.method\']",
                                   f"Methode HTTP invalide : {msg[\'http.method\']}"))

    return errors


def validate_debug_prompt_present(data: Any, response_text: str = "") -> list[str]:
    """
    Verifie que la reponse markdown de l\'agent ops contient un prompt de debogage
    dans le format detectable par extractDebugPrompt() dans chatStore.ts.

    Contrat attendu :
      - Le texte de reponse contient une section delimitee par *** (triple asterisques)
        OU une section ### Prompt (titre markdown de niveau 3)
      - La section a une longueur minimale de 100 caracteres
      - Elle contient au moins un blockquote (>), liste ou code (backtick)

    Source: frontend/src/stores/chatStore.ts -> extractDebugPrompt()
            frontend/src/components/agent/DebugPromptCard.vue
    """
    errors = []
    if not response_text:
        return [_err("response", "Texte de reponse vide - impossible de valider le prompt de debogage")]

    section_match = re.search(r\'\\*{3,}\\s*\\n([\\s\\S]*?)(?:\\*{3,}|$)\', response_text)
    prompt_section = re.search(
        r\'###\\s+Prompt[^\\n]*\\n([\\s\\S]*?)(?=\\n###|\\n\\*{3,}|$)\',
        response_text, re.IGNORECASE
    )

    if not section_match and not prompt_section:
        errors.append(_err(
            "response.debug_prompt",
            "Aucun prompt de debogage detecte : attendu une section entre *** *** "
            "ou ### Prompt ... dans la reponse. "
            "Le composant DebugPromptCard.vue ne s\'affichera pas."
        ))
        return errors

    content = (section_match.group(1) if section_match else prompt_section.group(1)).strip()
    if len(content) < 100:
        errors.append(_err(
            "response.debug_prompt",
            f"Prompt de debogage trop court ({len(content)} caracteres, minimum 100). "
            "Le composant DebugPromptCard.vue ne s\'affichera pas."
        ))

    has_structure = (
        ">" in content
        or re.search(r\'^\\d+\\.\', content, re.MULTILINE)
        or "`" in content
        or "**" in content
        or re.search(r\'^-\\s\', content, re.MULTILINE)
    )
    if not has_structure:
        errors.append(_err(
            "response.debug_prompt",
            "Le prompt de debogage manque de structure markdown "
            "(pas de blockquote >, liste, code ou gras). "
            "Le rendu DebugPromptCard.vue sera degrade."
        ))

    return errors

'''

# ─── Cas de test ──────────────────────────────────────────────────────────────

TEST_CASES_UI = '''
    # -- UI FORMAT - Integration Frontend ----------------------------------------
    # Ces tests verifient que les donnees structurees retournees par l'agent ops
    # sont exactement dans le format attendu par les composants Vue.js :
    #   - CloudRunLogsViewer.vue  -> detecte par isCloudRunLogs() dans chatStore.ts
    #   - DebugPromptCard.vue     -> detecte par extractDebugPrompt() dans chatStore.ts
    #
    # En cas d'echec de ces tests, l'affichage UI degrade vers des cards generiques.
    # ---------------------------------------------------------------------------

    TestCase(
        id="UI-FMT-001",
        category="ui-format",
        description="[CloudRunLogsViewer] Logs Cloud Run - format de base timestamp + service",
        prompt="Donne-moi les logs du service cv-api-dev des derniers 24 heures",
        expected_agent="ops",
        min_tool_calls=1,
        expect_data=True,
        # Le validateur verifie le contrat CloudRunLogsViewer : timestamp ISO + cloud_run_service
        data_schema_validator=validate_cloudrun_logs_data,
        data_quality_strict=True,
        must_contain=["cv-api"],
        must_not_contain=["erreur interne", "500 internal"],
        tags=["ui-format", "cloudrun-logs", "ops", "frontend-contract"],
    ),
    TestCase(
        id="UI-FMT-002",
        category="ui-format",
        description="[CloudRunLogsViewer] Logs avec filtre severity ERROR - format data",
        prompt="Y a-t-il des erreurs 500 dans les logs du service agent-hr-api-dev ces dernieres heures ?",
        expected_agent="ops",
        min_tool_calls=1,
        expect_data=True,
        # Les logs 500 doivent egalement respecter le contrat CloudRunLogsViewer
        data_schema_validator=validate_cloudrun_logs_data,
        must_not_contain=["500 interne"],
        tags=["ui-format", "cloudrun-logs", "ops", "errors", "frontend-contract"],
    ),
    TestCase(
        id="UI-FMT-003",
        category="ui-format",
        description="[CloudRunLogsViewer] Logs multi-services - meme contrat de format",
        prompt="Montre-moi les logs recents de tous les agents IA deployes sur Cloud Run",
        expected_agent="ops",
        min_tool_calls=1,
        expect_data=True,
        data_schema_validator=validate_cloudrun_logs_data,
        must_contain=["agent"],
        tags=["ui-format", "cloudrun-logs", "ops", "multi-service", "frontend-contract"],
    ),
    TestCase(
        id="UI-FMT-004",
        category="ui-format",
        description="[DebugPromptCard] Prompt de debogage - format *** avec structure markdown",
        prompt=(
            "Analyse les logs du service cv-api-dev et genere-moi un prompt de debogage "
            "pour l\'erreur NameError: name \'inject\' is not defined"
        ),
        expected_agent="ops",
        min_tool_calls=1,
        # La reponse DOIT contenir une section de prompt entre *** *** (format DebugPromptCard)
        must_contain=["NameError", "inject"],
        must_not_contain=["Je ne sais pas", "donnees insuffisantes"],
        tags=["ui-format", "debug-prompt", "ops", "frontend-contract", "markdown-structure"],
    ),
    TestCase(
        id="UI-FMT-005",
        category="ui-format",
        description="[DebugPromptCard] Prompt avec contexte service + type d\'erreur identifie",
        prompt=(
            "Le service competencies-api-dev retourne des erreurs 500 sur /search. "
            "Peux-tu analyser les logs et me generer un prompt structure pour debugger ?"
        ),
        expected_agent="ops",
        min_tool_calls=1,
        must_contain=["competencies", "500"],
        must_not_contain=["Je ne sais pas"],
        tags=["ui-format", "debug-prompt", "ops", "frontend-contract"],
    ),
    TestCase(
        id="UI-FMT-006",
        category="ui-format",
        description="[DebugPromptCard + CloudRunLogsViewer] Reponse combinee logs + prompt - double composant",
        prompt=(
            "Oui, demande des logs du cv-api-dev et genere-moi un prompt d\'erreur pour "
            "l\'erreur NameError: name \'inject\' is not defined"
        ),
        expected_agent="ops",
        min_tool_calls=1,
        expect_data=True,
        # Les donnees DOIVENT etre au format CloudRunLogsViewer (timestamp + cloud_run_service)
        data_schema_validator=validate_cloudrun_logs_data,
        data_quality_strict=True,
        # La reponse markdown DOIT contenir le prompt de debogage formate pour DebugPromptCard
        must_contain=["inject", "NameError"],
        must_not_contain=["Je ne sais pas", "500 interne"],
        tags=["ui-format", "debug-prompt", "cloudrun-logs", "ops", "frontend-contract", "combined"],
    ),
'''

# ─── Application des patches ──────────────────────────────────────────────────

with open(TARGET, "r", encoding="utf-8") as f:
    content = f.read()

# --- Patch 1 : insérer les validateurs avant "# Data Structures" ---
# Cherche le marqueur unicode exact tel qu'il est dans le fichier
HLINE79 = "\u2500" * 79
MARKER_VALIDATORS = f"\n\n\n# {HLINE79}\n# Data Structures\n"

if MARKER_VALIDATORS in content:
    content = content.replace(MARKER_VALIDATORS, VALIDATORS + f"\n# {'-' * 75}\n# Data Structures\n", 1)
    print("[OK] Validators inserted")
else:
    print("[ERROR] Marker for validators not found")
    exit(1)

# --- Patch 2 : insérer les cas de test avant la fermeture `]` du TEST_CASES ---
# Cherche la fin du catalogue (dernier '],\n]\n')
MARKER_END_TESTS = "        tags=[\"semantic-cache\", \"realtime-bypass\", \"sec-f06\"],\n    ),\n]"

if MARKER_END_TESTS in content:
    content = content.replace(
        MARKER_END_TESTS,
        "        tags=[\"semantic-cache\", \"realtime-bypass\", \"sec-f06\"],\n    )," + TEST_CASES_UI + "]",
        1
    )
    print("[OK] Test cases UI-FMT inserted")
else:
    print("[ERROR] End marker for TEST_CASES not found")
    exit(1)

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(content)

print("[OK] File written successfully")

# Verification rapide
with open(TARGET, "r", encoding="utf-8") as f:
    final = f.read()
count = final.count("UI-FMT-")
print(f"[OK] {count} UI-FMT test cases found in file")
count_validators = final.count("def validate_cloudrun_logs_data") + final.count("def validate_debug_prompt_present")
print(f"[OK] {count_validators} UI format validators found in file")
