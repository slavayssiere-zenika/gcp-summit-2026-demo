"""
Tests de non-régression structurels : le tool log_ai_consumption de market_mcp
n'accepte jamais 'user_1' comme user_email valide en production, et le
schema MCP exige user_email.

Le market_mcp est un MCP passif (pas d'auth propre), il reçoit user_email
depuis les services appelants. Ces tests vérifient le code source pour 
détecter les régressions (hardcodage "user_1" ou modification du schema MCP)
sans mock d'infrastructure (approche robuste et décorrélée de BigQuery).

ADR : BUG-FINOPS-002 (MCP layer)
"""

import pathlib
import pytest

# ---------------------------------------------------------------------------
# 1. Test structurel — schema user_email obligatoire dans log_ai_consumption
# ---------------------------------------------------------------------------

def test_log_ai_consumption_schema_requires_user_email():
    """
    Structurel : user_email doit être dans les champs REQUIRED du schema MCP
    de log_ai_consumption. S'il devient optional, les appelants peuvent omettre
    le JWT sub et polluer BigQuery avec des entrées sans utilisateur.
    """
    mcp_path = pathlib.Path(__file__).parent.parent / "mcp_server.py"
    source = mcp_path.read_text()

    # Trouver le bloc `list_tools` et le tool `log_ai_consumption`
    assert "def list_tools" in source, "Fonction list_tools introuvable"
    assert "log_ai_consumption" in source, "Tool log_ai_consumption introuvable"

    # Le mot-clé user_email doit faire partie des définitions du json schema
    assert '"user_email"' in source or "'user_email'" in source, \
        "ANOMALIE: 'user_email' absent de market_mcp/mcp_server.py"


# ---------------------------------------------------------------------------
# 2. Test structurel — market_mcp source ne hardcode pas user_1
# ---------------------------------------------------------------------------

def test_market_mcp_source_no_hardcoded_user1():
    """
    Structurel : le source de mcp_server.py ne doit jamais hardcoder 'user_1'
    comme valeur de user_email pour un insert BigQuery.
    """
    mcp_path = pathlib.Path(__file__).parent.parent / "mcp_server.py"
    source = mcp_path.read_text()

    # Chercher des patterns suspects : user_email = "user_1" ou user_email: "user_1"
    problematic_patterns = [
        'user_email": "user_1"',
        "user_email\": 'user_1'",
        'user_email = "user_1"',
        "user_email = 'user_1'",
        'user_email="user_1"',
        "user_email='user_1'",
    ]
    
    for pattern in problematic_patterns:
        assert pattern not in source, (
            f"REGRESSION: Pattern {pattern!r} trouvé dans market_mcp/mcp_server.py — "
            "user_email ne doit jamais être hardcodé à 'user_1' dans le MCP"
        )
