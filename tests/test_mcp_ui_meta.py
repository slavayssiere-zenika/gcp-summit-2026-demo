"""
test_mcp_ui_meta.py — Vérifie que les MCP tools annotés avec meta.ui.resourceUri
utilisent des URIs valides de la taxonomie sémantique UiWidget.

Ces tests sont des tests de contrat : ils garantissent qu'aucune URI invalide
ou mal typée ne peut être injectée dans le système de dispatch frontend.
"""
import json
import pytest

# Registre des URIs sémantiques valides (taxonomie officielle)
VALID_UI_URIS = {
    "ui://consultant",
    "ui://consultants",
    "ui://candidate",
    "ui://candidates",
    "ui://mission",
    "ui://missions",
    "ui://item",
    "ui://items",
    "ui://availability",
    "ui://availabilities",
    "ui://competency",
    "ui://competencies",
    "ui://evaluation",
    "ui://evaluations",
    "ui://tree",
    "ui://health",
    "ui://empty",
}

# === Fixtures de data extraites statiquement des mcp_server.py ===
# (évite de charger le module avec ses dépendances GCP/HTTP au test time)

USERS_API_EXPECTED = {
    "list_users": "ui://consultants",
    "get_users_bulk": "ui://consultants",
    "search_users": "ui://consultants",
    "search_anonymous_users": "ui://consultants",
    "get_users_availability_bulk": "ui://availabilities",
}

CV_API_EXPECTED = {
    "search_best_candidates": "ui://candidates",
}

COMPETENCIES_API_EXPECTED = {
    "list_competencies": "ui://competencies",
    "search_competencies": "ui://competencies",
    "find_similar_consultants": "ui://candidates",
    "get_user_competency_evaluations": "ui://evaluations",
}

MISSIONS_API_EXPECTED = {
    "list_missions": "ui://missions",
}

ITEMS_API_EXPECTED = {
    "list_items": "ui://items",
    "search_items": "ui://items",
    "get_items_by_user": "ui://items",
}


def _extract_ui_uri_from_file(filepath: str, tool_name: str) -> str | None:
    """Extrait statiquement la resourceUri d'un tool depuis le fichier mcp_server.py."""
    with open(filepath, "r") as f:
        content = f.read()

    # Cherche le pattern: name="<tool_name>", ..., meta={"ui": {"resourceUri": "ui://..."}}
    import re
    # Cherche le bloc Tool() contenant le nom exact
    pattern = rf'name="{re.escape(tool_name)}".*?meta\s*=\s*(\{{[^}}]+\}}[^)]*)'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return None

    # Extrait la resourceUri
    uri_match = re.search(r'"resourceUri"\s*:\s*"(ui://[^"]+)"', match.group(0))
    if uri_match:
        return uri_match.group(1)
    return None


class TestUsersApiUiMeta:
    FILEPATH = "../users_api/src/mcp_tools/tools_registry.py"

    @pytest.mark.parametrize("tool_name,expected_uri", USERS_API_EXPECTED.items())
    def test_tool_has_valid_uri(self, tool_name, expected_uri):
        uri = _extract_ui_uri_from_file(self.FILEPATH, tool_name)
        assert uri is not None, f"Tool '{tool_name}' n'a pas de meta.ui.resourceUri"
        assert uri == expected_uri, f"Tool '{tool_name}': attendu {expected_uri!r}, obtenu {uri!r}"
        assert uri in VALID_UI_URIS, f"URI '{uri}' n'est pas dans la taxonomie valide"


class TestCvApiUiMeta:
    FILEPATH = "../cv_api/mcp_server.py"

    @pytest.mark.parametrize("tool_name,expected_uri", CV_API_EXPECTED.items())
    def test_tool_has_valid_uri(self, tool_name, expected_uri):
        uri = _extract_ui_uri_from_file(self.FILEPATH, tool_name)
        assert uri is not None, f"Tool '{tool_name}' n'a pas de meta.ui.resourceUri"
        assert uri == expected_uri, f"Tool '{tool_name}': attendu {expected_uri!r}, obtenu {uri!r}"
        assert uri in VALID_UI_URIS


class TestCompetenciesApiUiMeta:
    FILEPATH = "../competencies_api/mcp_server.py"

    @pytest.mark.parametrize("tool_name,expected_uri", COMPETENCIES_API_EXPECTED.items())
    def test_tool_has_valid_uri(self, tool_name, expected_uri):
        uri = _extract_ui_uri_from_file(self.FILEPATH, tool_name)
        assert uri is not None, f"Tool '{tool_name}' n'a pas de meta.ui.resourceUri"
        assert uri == expected_uri, f"Tool '{tool_name}': attendu {expected_uri!r}, obtenu {uri!r}"
        assert uri in VALID_UI_URIS


class TestMissionsApiUiMeta:
    FILEPATH = "../missions_api/mcp_server.py"

    @pytest.mark.parametrize("tool_name,expected_uri", MISSIONS_API_EXPECTED.items())
    def test_tool_has_valid_uri(self, tool_name, expected_uri):
        uri = _extract_ui_uri_from_file(self.FILEPATH, tool_name)
        assert uri is not None, f"Tool '{tool_name}' n'a pas de meta.ui.resourceUri"
        assert uri == expected_uri, f"Tool '{tool_name}': attendu {expected_uri!r}, obtenu {uri!r}"
        assert uri in VALID_UI_URIS


class TestItemsApiUiMeta:
    FILEPATH = "../items_api/mcp_server.py"

    @pytest.mark.parametrize("tool_name,expected_uri", ITEMS_API_EXPECTED.items())
    def test_tool_has_valid_uri(self, tool_name, expected_uri):
        uri = _extract_ui_uri_from_file(self.FILEPATH, tool_name)
        assert uri is not None, f"Tool '{tool_name}' n'a pas de meta.ui.resourceUri"
        assert uri == expected_uri, f"Tool '{tool_name}': attendu {expected_uri!r}, obtenu {uri!r}"
        assert uri in VALID_UI_URIS


class TestUriTaxonomyContract:
    """Tests de gouvernance du registre d'URIs."""

    def test_all_expected_uris_start_with_ui_scheme(self):
        """Toute URI dans le registre doit commencer par 'ui://'."""
        for uri in VALID_UI_URIS:
            assert uri.startswith("ui://"), f"URI invalide (pas de schème ui://): {uri}"

    def test_all_expected_uris_are_non_empty_slugs(self):
        """Toute URI doit avoir un slug non vide après 'ui://'."""
        for uri in VALID_UI_URIS:
            slug = uri[5:]  # après "ui://"
            assert slug, f"URI avec slug vide: {uri}"
            assert " " not in slug, f"URI avec espace: {uri}"

    def test_plural_forms_have_singular_counterpart(self):
        """Chaque forme plurielle doit avoir une forme singulière correspondante."""
        plural_map = {
            "ui://consultants": "ui://consultant",
            "ui://candidates": "ui://candidate",
            "ui://missions": "ui://mission",
            "ui://items": "ui://item",
            "ui://availabilities": "ui://availability",
            "ui://competencies": "ui://competency",
            "ui://evaluations": "ui://evaluation",
        }
        for plural, singular in plural_map.items():
            assert plural in VALID_UI_URIS, f"Forme plurielle manquante: {plural}"
            assert singular in VALID_UI_URIS, f"Forme singulière manquante: {singular}"
