"""batch_parsers.py — Fonctions pures de parsing et normalisation pour le pipeline batch taxonomie.

Ce module isole toute la logique de transformation de données (parsing JSONL Vertex AI,
normalisation des noms, collecte récursive) afin de la rendre testable sans dépendances
vers GCS, Redis, HTTP ou Vertex AI.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)


def strip_json_fences(text: str) -> str:
    """Retire les balises Markdown ```json ... ``` ou ``` ... ``` d'une chaîne LLM.

    Args:
        text: Réponse brute du LLM pouvant contenir des balises de code.

    Returns:
        Chaîne nettoyée, prête pour json.loads().

    Examples:
        >>> strip_json_fences('```json\\n{"a": 1}\\n```')
        '{"a": 1}'
        >>> strip_json_fences('{"a": 1}')
        '{"a": 1}'
    """
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def normalize_pillar_name(name: str | None) -> str:
    """Normalise un nom de pilier pour comparaison fuzzy insensible à la casse et aux caractères spéciaux.

    Remplace '&' par 'et', supprime tout caractère non alphanumérique, met en minuscules.

    Args:
        name: Nom brut du pilier (peut être None).

    Returns:
        Chaîne normalisée (uniquement lettres minuscules et chiffres).

    Examples:
        >>> normalize_pillar_name("Cloud & DevOps")
        'cloudetdevops'
        >>> normalize_pillar_name("IA / ML")
        'iaml'
        >>> normalize_pillar_name(None)
        ''
        >>> normalize_pillar_name("")
        ''
    """
    return re.sub(r'[^a-z0-9]', '', (name or '').lower().replace('&', 'et'))


def get_all_used_names(node, used: set | None = None) -> set:
    """Collecte récursivement tous les noms de compétences référencés dans un arbre taxonomique.

    Parcourt les dictionnaires, listes et chaînes de l'arbre pour extraire :
    - Les valeurs "name"
    - Les éléments de "merge_from"
    - Les clés de premier niveau (piliers) qui ne sont pas des champs de métadonnées

    Args:
        node: Nœud courant (dict, list ou str).
        used: Ensemble accumulateur (None = départ récursion).

    Returns:
        Ensemble de tous les noms trouvés dans l'arbre.

    Examples:
        >>> tree = {"Kubernetes": {"name": "Kubernetes", "merge_from": ["K8s", "k8s"]}}
        >>> names = get_all_used_names(tree)
        >>> "Kubernetes" in names and "K8s" in names
        True
    """
    if used is None:
        used = set()

    if isinstance(node, dict):
        if "name" in node:
            used.add(node["name"])
        if "merge_from" in node and isinstance(node["merge_from"], list):
            for m in node["merge_from"]:
                used.add(m)
        for k, v in node.items():
            if isinstance(k, str) and k not in (
                "sub", "sub_competencies", "description", "aliases", "name", "merge_from"
            ):
                used.add(k)
            if k not in ("description", "aliases"):
                get_all_used_names(v, used)

    elif isinstance(node, list):
        for item in node:
            get_all_used_names(item, used)

    elif isinstance(node, str):
        used.add(node)

    return used


def parse_jsonl_map_result(file_content: str) -> tuple[dict, dict]:
    """Parse le contenu JSONL d'un batch Map Vertex AI.

    Chaque ligne est un objet JSON de réponse Vertex AI batch. Extrait les groupes
    compétences par pilier et agrège les métadonnées de tokens.

    Args:
        file_content: Contenu brut du fichier JSONL téléchargé depuis GCS.

    Returns:
        Tuple (map_result, usage_stats) où :
        - map_result: dict {pillar: [skill1, skill2, ...]}
        - usage_stats: dict {"prompt_token_count": int, "candidates_token_count": int}

    Notes:
        - Les chunks non parsables sont ignorés avec log d'erreur (comportement tolérant).
        - Un chunk vide ou invalide n'interrompt pas le parsing global.
    """
    map_result: dict = {}
    total_prompt_tokens = 0
    total_candidates_tokens = 0

    for i, line in enumerate(file_content.splitlines()):
        if not line.strip():
            continue

        try:
            resp = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f"[batch_parsers] Ligne JSONL {i} invalide (ignorée): {e}")
            continue

        # Accumulation des tokens
        usage_meta = resp.get("response", {}).get("usageMetadata", {})
        total_prompt_tokens += usage_meta.get("promptTokenCount", 0)
        total_candidates_tokens += usage_meta.get("candidatesTokenCount", 0)

        # Extraction du texte de réponse
        candidates = resp.get("response", {}).get("candidates", [])
        if not candidates:
            continue
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            continue
        text = parts[0].get("text", "")
        if not text:
            continue

        # Parsing JSON avec nettoyage des balises Markdown
        try:
            cleaned = strip_json_fences(text)
            raw_map, _ = json.JSONDecoder().raw_decode(cleaned)

            if isinstance(raw_map, dict) and "items" in raw_map:
                raw_map = raw_map["items"]

            parsed_chunk: dict = {}
            if isinstance(raw_map, list):
                for item in raw_map:
                    if isinstance(item, dict):
                        parsed_chunk.update(item)
            elif isinstance(raw_map, dict):
                parsed_chunk.update(raw_map)

            for pillar, skills in parsed_chunk.items():
                if not isinstance(skills, list):
                    continue
                if pillar not in map_result:
                    map_result[pillar] = []
                map_result[pillar].extend(skills)

        except Exception as e:
            logger.error(f"[batch_parsers] Erreur parsing chunk Map {i} (ignoré): {e}")
            continue

    usage_stats = {
        "prompt_token_count": total_prompt_tokens,
        "candidates_token_count": total_candidates_tokens,
    }
    return map_result, usage_stats


def check_missing_pillars(
    expected_pillars: list[dict],
    actual_tree: dict,
) -> list[str]:
    """Vérifie que tous les piliers attendus sont présents dans l'arbre Reduce résultant.

    Utilise une normalisation fuzzy pour comparer les noms (insensible à la casse,
    aux accents et aux caractères spéciaux).

    Args:
        expected_pillars: Liste de dicts {"name": str, ...} des piliers attendus (output Deduplicate).
        actual_tree: Arbre résultant du Reduce (clés = noms de piliers).

    Returns:
        Liste des noms originaux manquants (vide = tous les piliers sont présents).

    Examples:
        >>> check_missing_pillars([{"name": "Cloud & DevOps"}], {"cloudetdevops": {}})
        []  # normalisations identiques → OK
        >>> check_missing_pillars([{"name": "Security"}], {"Cloud": {}})
        ['Security']
    """
    expected_names = {p.get("name") for p in expected_pillars if p.get("name")}
    actual_names = set(actual_tree.keys())

    expected_norm = {normalize_pillar_name(n): n for n in expected_names}
    actual_norm = {normalize_pillar_name(n): n for n in actual_names}
    missing_norm = set(expected_norm.keys()) - set(actual_norm.keys())

    return [expected_norm[k] for k in missing_norm]


def has_unsubstituted_placeholders(tree: dict) -> bool:
    """Détecte si l'arbre contient des placeholders non substitués (bug de template).

    Un arbre corrompu contient des clés comme '{{CURRENT_PILLAR}}' ou '{{PILLAR_NAME}}'
    qui auraient dû être remplacées par le prompt Reduce.

    Args:
        tree: Arbre résultant du Reduce Vertex AI.

    Returns:
        True si des placeholders non substitués sont détectés.

    Examples:
        >>> has_unsubstituted_placeholders({"{{CURRENT_PILLAR}}": {}})
        True
        >>> has_unsubstituted_placeholders({"Kubernetes": {}})
        False
    """
    return "{{CURRENT_PILLAR}}" in tree or "{{PILLAR_NAME}}" in tree
