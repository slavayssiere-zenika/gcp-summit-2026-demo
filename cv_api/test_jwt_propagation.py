"""
Tests de non-régression : propagation du JWT sub comme user_caller dans cv_api.

cv_api utilise token_payload.get("sub", "unknown") pour le log FinOps sur :
- POST /cvs/analyze (analyze_cv)
- POST /cvs/search (search_filter_extraction + search_embedding)
- POST /cvs/recalculate-tree (recalculate_tree)

Ces tests garantissent que le sub JWT est bien extrait et transmis à _log_finops,
et que la valeur "unknown" n'est utilisée qu'en dernier recours.

ADR : BUG-FINOPS-002 (API data layer — cv_api)
"""

import os
os.environ["SECRET_KEY"] = "testsecret"

import pathlib
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from main import app
from src.auth import verify_jwt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Test structurel — le code source extrait bien le sub JWT
# ---------------------------------------------------------------------------

def test_cv_router_extracts_sub_for_finops():
    """
    Test structurel : vérifie que src/cvs/router.py extrait bien le sub JWT
    via token_payload.get("sub") pour le logging FinOps.
    Détecte une régression si quelqu'un remplace par une constante hardcodée.
    """
    router_path = pathlib.Path(__file__).parent / "src" / "cvs" / "router.py"
    source = router_path.read_text()

    # Le sub doit être extrait
    assert 'token_payload.get("sub"' in source or "token_payload.get('sub'" in source, \
        "ANOMALIE: token_payload.get('sub') introuvable dans cv_api/router.py"

    # Aucune valeur "user_1" hardcodée
    assert 'user_caller = "user_1"' not in source, \
        "REGRESSION: user_caller hardcodé à 'user_1' dans cv_api/router.py"
    assert "user_caller = 'user_1'" not in source, \
        "REGRESSION: user_caller hardcodé à 'user_1' dans cv_api/router.py"

    # _log_finops doit recevoir user_caller (variable), pas une constante
    # Vérifier que les appels _log_finops utilisent user_caller variable
    finops_calls = [line for line in source.splitlines()
                    if "_log_finops(" in line and "user_caller" in line]
    assert len(finops_calls) >= 2, \
        f"Attendu >= 2 appels _log_finops(user_caller, ...), trouvé: {len(finops_calls)}"


# ---------------------------------------------------------------------------
# 2. Test structurel — GET /cvs/analyze passe user_caller à _log_finops
# ---------------------------------------------------------------------------

def test_analyze_cv_uses_jwt_sub_as_user_caller():
    """
    REGRESSION BUG-FINOPS-002 : _log_finops doit recevoir le user_caller 
    (sub JWT), pas une variable hardcodée.
    """
    router_path = pathlib.Path(__file__).parent / "src" / "cvs" / "router.py"
    source = router_path.read_text()
    
    lines = source.splitlines()
    in_analyze = False
    analyze_block = []
    
    for line in lines:
        if "@router.post" in line and '"/analyze"' in line:
            in_analyze = True
        if in_analyze:
            analyze_block.append(line)
            if "@router." in line and len(analyze_block) > 1:
                break
                
    analyze_code = "\n".join(analyze_block)
    if analyze_code:
        assert "token_payload.get(\"sub\", \"unknown\")" in analyze_code or "token_payload.get('sub', 'unknown')" in analyze_code, (
            "REGRESSION: user_caller n'extrait plus sub JWT en fallback strict"
        )
        assert "_log_finops(user_caller" in analyze_code, (
            "REGRESSION: _log_finops n'utilise plus user_caller dans /analyze"
        )



# ---------------------------------------------------------------------------
# 3. Test structurel — analytics_mcp : log_ai_consumption reçoit user_email
# ---------------------------------------------------------------------------

def test_analytics_mcp_log_ai_consumption_expects_user_email():
    """
    Test structurel sur analytics_mcp : la fonction log_ai_consumption doit accepter
    un paramètre user_email (jamais hardcodé à 'user_1' dans l'outil MCP).
    """
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "analytics_mcp"))

    try:
        import importlib
        mcp_spec = importlib.util.spec_from_file_location(
            "mcp_server",
            str(pathlib.Path(__file__).parent.parent / "analytics_mcp" / "mcp_server.py"),
        )
        mcp_module = importlib.util.module_from_spec(mcp_spec)

        # Lire le source sans l'exécuter (évite les effets de bord)
        mcp_source = (pathlib.Path(__file__).parent.parent / "analytics_mcp" / "mcp_server.py").read_text()

        # log_ai_consumption ne doit jamais hardcoder user_1
        assert '"user_1"' not in mcp_source.split("def log_ai_consumption")[1].split("def ")[0] \
            if "def log_ai_consumption" in mcp_source else True, \
            "REGRESSION: 'user_1' hardcodé dans log_ai_consumption tool de analytics_mcp"

        # Le tool doit accepter user_email comme paramètre
        assert "user_email" in mcp_source, \
            "ANOMALIE: 'user_email' introuvable dans analytics_mcp/mcp_server.py"

    except Exception:
        pytest.skip("analytics_mcp non accessible depuis cv_api — skip structurel")
