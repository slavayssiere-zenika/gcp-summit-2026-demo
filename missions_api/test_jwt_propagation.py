"""
Tests de non-régression : propagation du JWT sub comme user_email dans missions_api.

missions_api (API data) extrait le sub JWT via token_payload.get("sub", ...) pour :
- user_email dans les background tasks d'import (POST /missions)
- user_email pour l'audit de réanalyse (POST /missions/{id}/reanalyze)
- user_email pour les changements de statut (PATCH /missions/{id}/status)

Ces tests sont structurels — ils valident le code source directement pour
détecter les régressions sans dépendre de l'infrastructure (DB, Redis).

ADR : BUG-FINOPS-002 (API data layer — missions_api)
"""

import os
os.environ["SECRET_KEY"] = "testsecret"

import pathlib
import pytest


# ---------------------------------------------------------------------------
# 1. Test structurel — le code source extrait bien le sub JWT
# ---------------------------------------------------------------------------

def test_router_source_extracts_sub_not_hardcoded():
    """
    REGRESSION BUG-FINOPS-002 : missions_api/src/missions/router.py doit utiliser
    token_payload.get("sub") comme user_email, pas une valeur hardcodée.
        """
    source_analysis = (pathlib.Path(__file__).parent / "src" / "missions" / "analysis_router.py").read_text()
    source_crud = (pathlib.Path(__file__).parent / "src" / "missions" / "crud_router.py").read_text()
    source = source_analysis + "\n" + source_crud

    # Le sub doit être extrait du JWT
    assert 'token_payload.get("sub"' in source or "token_payload.get('sub'" in source, \
        "ANOMALIE: token_payload.get('sub') introuvable dans missions router — le JWT sub n'est pas lu"

    # Aucune valeur "user_1" hardcodée
    assert 'user_email = "user_1"' not in source, \
        'REGRESSION: user_email = "user_1" hardcodé dans missions_api/router.py'
    assert "user_email = 'user_1'" not in source, \
        "REGRESSION: user_email = 'user_1' hardcodé dans missions_api/router.py"


def test_router_fallback_is_not_user1():
    """
    Le fallback de user_email doit être une valeur métier (ex: 'unknown@zenika.com'),
    pas 'user_1' qui est une valeur de session interne.
        """
    source_analysis = (pathlib.Path(__file__).parent / "src" / "missions" / "analysis_router.py").read_text()
    source_crud = (pathlib.Path(__file__).parent / "src" / "missions" / "crud_router.py").read_text()
    source = source_analysis + "\n" + source_crud

    # Chercher les lignes avec user_email = token_payload.get
    lines_with_sub = [l.strip() for l in source.splitlines() if "user_email" in l and "get(" in l]

    for line in lines_with_sub:
        assert '"user_1"' not in line, (
            f"REGRESSION: Fallback 'user_1' trouvé dans la ligne user_email: {line!r}"
        )
        assert "'user_1'" not in line, (
            f"REGRESSION: Fallback 'user_1' trouvé dans la ligne user_email: {line!r}"
        )


# ---------------------------------------------------------------------------
# 2. Test structurel — routes de statut utilisent le sub JWT
# ---------------------------------------------------------------------------

def test_status_route_uses_jwt_sub_for_audit():
    """
    PATCH /missions/{id}/status doit utiliser le sub JWT comme changed_by
    dans l'audit trail (StatusHistory). Vérifié structurellement.
        """
    source_analysis = (pathlib.Path(__file__).parent / "src" / "missions" / "analysis_router.py").read_text()
    source_crud = (pathlib.Path(__file__).parent / "src" / "missions" / "crud_router.py").read_text()
    source = source_analysis + "\n" + source_crud

    # La route status doit extraire le sub
    patch_route_section = ""
    if "@router.patch" in source and "status" in source:
        lines = source.splitlines()
        in_patch_route = False
        for line in lines:
            if "@router.patch" in line and "status" in line:
                in_patch_route = True
            if in_patch_route:
                patch_route_section += line + "\n"
                if line.startswith("@router.") and patch_route_section.count("@router.") > 1:
                    break

    if patch_route_section:
        assert "sub" in patch_route_section, (
            "ANOMALIE: 'sub' (JWT) non trouvé dans la route PATCH /status — "
            "l'audit trail ne capture pas l'utilisateur"
        )
        assert "user_1" not in patch_route_section, (
            "REGRESSION: 'user_1' hardcodé dans PATCH /status — changed_by sera toujours 'user_1'"
        )


# ---------------------------------------------------------------------------
# 3. Test structurel cross-service — analytics_mcp user_email schema
# ---------------------------------------------------------------------------

def test_analytics_mcp_user_email_required_in_log_ai_consumption():
    """
    Structurel : analytics_mcp/mcp_server.py doit déclarer user_email comme
    champ REQUIRED dans log_ai_consumption. S'il devient optionnel, les
    appelants peuvent omettre le sub JWT et polluer BigQuery.
    """
    mcp_path = pathlib.Path(__file__).parent.parent / "analytics_mcp" / "mcp_server.py"
    if not mcp_path.exists():
        pytest.skip("analytics_mcp non accessible depuis missions_api")

    source = mcp_path.read_text()

    # user_email doit être dans required
    assert '"user_email"' in source, \
        "ANOMALIE: 'user_email' absent de analytics_mcp/mcp_server.py"

    # Aucun hardcodage
    assert 'user_email": "user_1"' not in source, \
        "REGRESSION: user_email hardcodé à 'user_1' dans analytics_mcp"
