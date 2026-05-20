"""
test_state_graph_agent.py — Tests unitaires pour StateGraphAgent et l'alignement en boucle fermée.
"""
import json
from unittest.mock import AsyncMock

import pytest

from workflow_agent import (
    StateGraphAgent,
    ask_missions_agent_with_hr_alignment, build_workflow_agent
)


@pytest.mark.asyncio
async def test_state_graph_agent_creation():
    """Vérifie la création et la configuration de StateGraphAgent."""
    def mock_tool():
        pass

    agent = build_workflow_agent(mock_tool, mock_tool, mock_tool)
    assert isinstance(agent, StateGraphAgent)
    assert len(agent.sub_agents) == 2
    assert agent.sub_agents[0].name == "query_domain_classifier"
    assert agent.sub_agents[1].name == "zenika_workflow_router"


@pytest.mark.asyncio
async def test_ask_missions_agent_alignment_nominal(mocker):
    """Vérifie le cas nominal de ask_missions_agent_with_hr_alignment sans alignement."""
    mock_missions = mocker.patch("workflow_agent.ask_missions_agent", new=AsyncMock())
    mock_hr = mocker.patch("workflow_agent.ask_hr_agent", new=AsyncMock())

    # Simulation d'une réponse nominale
    mock_missions.return_value = {
        "result": json.dumps({
            "agent": "missions_agent",
            "response": "La mission est validée avec succès.",
            "thoughts": "Tout est bon."
        })
    }

    res = await ask_missions_agent_with_hr_alignment("Valide le staffing", "user@zenika.com")

    # On vérifie que l'agent HR n'a pas été appelé
    mock_hr.assert_not_called()
    mock_missions.assert_called_once_with("Valide le staffing", "user@zenika.com")

    parsed = json.loads(res["result"])
    assert parsed["response"] == "La mission est validée avec succès."


@pytest.mark.asyncio
async def test_ask_missions_agent_alignment_closed_loop(mocker):
    """Vérifie la boucle fermée de résolution d'identifiant en cas de consultant manquant."""
    mock_missions = mocker.patch("workflow_agent.ask_missions_agent", new=AsyncMock())
    mock_hr = mocker.patch("workflow_agent.ask_hr_agent", new=AsyncMock())

    # Premier appel à Missions : signale un identifiant manquant
    # Deuxième appel à Missions (ré-exécution) : succès final
    mock_missions.side_effect = [
        {
            "result": json.dumps({
                "agent": "missions_agent",
                "response": "Identifiant manquant pour le consultant Alice."
            })
        },
        {
            "result": json.dumps({
                "agent": "missions_agent",
                "response": "Staffing d'Alice validé avec succès sur l'ID résolu."
            })
        }
    ]

    # Appel à HR : retourne l'identifiant
    mock_hr.return_value = {
        "result": json.dumps({
            "agent": "hr_agent",
            "response": "L'identifiant d'Alice est le suivant : 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
        })
    }

    res = await ask_missions_agent_with_hr_alignment("Valide le staffing pour Alice", "user@zenika.com")

    # Vérifications des appels
    assert mock_missions.call_count == 2
    mock_hr.assert_called_once_with("Donne-moi l'identifiant (UUID ou email) du consultant Alice", "user@zenika.com")

    # Vérification que le deuxième appel Missions a la requête enrichie avec l'ID
    mock_missions.assert_any_call("Valide le staffing pour Alice", "user@zenika.com")
    mock_missions.assert_any_call(
        "Valide le staffing pour Alice (avec l'identifiant du consultant Alice = 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d)",
        "user@zenika.com"
    )

    parsed = json.loads(res["result"])
    assert parsed["response"] == "Staffing d'Alice validé avec succès sur l'ID résolu."
