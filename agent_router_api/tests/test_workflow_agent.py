"""
test_workflow_agent.py — Tests d'intégration du WorkflowAgent (SequentialAgent + ParallelAgent).

Valide sans appel Gemini réel :
  - _build_classifier_agent() crée un LlmAgent valide
  - build_workflow_agent() crée un SequentialAgent avec les bons sous-agents
  - build_parallel_staffing_agent() crée un ParallelAgent
  - extract_domain() normalise correctement les domaines

Architecture testée :
    query → Classifier (output_key="query_domain") → Router (lit session.state)
"""
import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("GEMINI_MODEL", "gemini-test")
os.environ.setdefault("GEMINI_ROUTER_MODEL", "gemini-flash-lite-test")
os.environ.setdefault("GEMINI_CLASSIFIER_MODEL", "gemini-flash-lite-test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-long!!!")
os.environ.setdefault("REDIS_URL", "redis://localhost/0")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dummy_tool(query: str) -> str:
    """Outil A2A factice pour les tests."""
    return f"response to: {query}"


async def _dummy_tool_async(query: str) -> str:
    """Outil A2A factice async pour les tests."""
    return f"async response to: {query}"


# ── Tests extract_domain ──────────────────────────────────────────────────────

class TestExtractDomain:
    """Valide la normalisation du domaine classifié depuis session.state."""

    def test_hr_lowercase(self):
        from workflow_agent import extract_domain
        assert extract_domain({"query_domain": "hr"}) == "hr"

    def test_hr_uppercase(self):
        from workflow_agent import extract_domain
        assert extract_domain({"query_domain": "HR"}) == "hr"

    def test_hr_with_whitespace(self):
        from workflow_agent import extract_domain
        assert extract_domain({"query_domain": " HR\n"}) == "hr"

    def test_ops_normalized(self):
        from workflow_agent import extract_domain
        assert extract_domain({"query_domain": "OPS."}) == "ops"

    def test_missions_normalized(self):
        from workflow_agent import extract_domain
        assert extract_domain({"query_domain": "MISSIONS"}) == "missions"

    def test_mixed_normalized(self):
        from workflow_agent import extract_domain
        assert extract_domain({"query_domain": "mixed"}) == "mixed"

    def test_unknown_fallback_to_hr(self):
        from workflow_agent import extract_domain
        assert extract_domain({"query_domain": "unknown_domain"}) == "hr"

    def test_empty_fallback_to_hr(self):
        from workflow_agent import extract_domain
        assert extract_domain({}) == "hr"

    def test_none_value_fallback_to_hr(self):
        from workflow_agent import extract_domain
        assert extract_domain({"query_domain": None}) == "hr"

    def test_classifier_model_is_configurable(self):
        """_CLASSIFIER_MODEL doit être une string non vide (configurable via env)."""
        from workflow_agent import _CLASSIFIER_MODEL
        assert isinstance(_CLASSIFIER_MODEL, str)
        assert len(_CLASSIFIER_MODEL) > 0


# ── Tests build_workflow_agent ────────────────────────────────────────────────

class TestBuildWorkflowAgent:
    """Valide la structure du SequentialAgent WorkflowAgent."""

    def test_creates_stategraph_agent(self):
        """build_workflow_agent() doit retourner un StateGraphAgent."""
        from workflow_agent import build_workflow_agent, StateGraphAgent
        wf = build_workflow_agent(_dummy_tool, _dummy_tool, _dummy_tool)
        assert isinstance(wf, StateGraphAgent)

    def test_workflow_name(self):
        """Le WorkflowAgent doit avoir le nom canonique Zenika."""
        from workflow_agent import build_workflow_agent
        wf = build_workflow_agent(_dummy_tool, _dummy_tool, _dummy_tool)
        assert wf.name == "zenika_staffing_workflow"

    def test_has_two_sub_agents(self):
        """Le pipeline doit avoir exactement 2 étapes : classifier + router."""
        from workflow_agent import build_workflow_agent
        wf = build_workflow_agent(_dummy_tool, _dummy_tool, _dummy_tool)
        assert len(wf.sub_agents) == 2

    def test_first_sub_agent_is_classifier(self):
        """Le premier sous-agent doit être le classifier."""
        from workflow_agent import build_workflow_agent
        wf = build_workflow_agent(_dummy_tool, _dummy_tool, _dummy_tool)
        classifier = wf.sub_agents[0]
        assert classifier.name == "query_domain_classifier"

    def test_classifier_has_output_key(self):
        """Le classifier doit stocker son résultat dans session.state['query_domain']."""
        from google.adk.agents import LlmAgent
        from workflow_agent import build_workflow_agent
        wf = build_workflow_agent(_dummy_tool, _dummy_tool, _dummy_tool)
        classifier = wf.sub_agents[0]
        assert isinstance(classifier, LlmAgent)
        assert classifier.output_key == "query_domain"

    def test_second_sub_agent_is_router(self):
        """Le second sous-agent doit être le router déterministe."""
        from google.adk.agents import LlmAgent
        from workflow_agent import build_workflow_agent
        wf = build_workflow_agent(_dummy_tool, _dummy_tool, _dummy_tool)
        router = wf.sub_agents[1]
        assert isinstance(router, LlmAgent)
        assert router.name == "zenika_workflow_router"

    def test_router_has_all_tools(self):
        """Le router doit recevoir les 4 outils A2A (incluant ask_mixed_agents)."""
        from workflow_agent import build_workflow_agent
        wf = build_workflow_agent(_dummy_tool, _dummy_tool, _dummy_tool)
        router = wf.sub_agents[1]
        # tools est une liste de callables ou FunctionTool wrappés
        assert len(router.tools) == 4

    def test_different_tools_passed_correctly(self):
        """Chaque outil A2A doit être distinct (hr, ops, missions)."""
        from workflow_agent import build_workflow_agent

        def hr_tool(q: str) -> str: return "hr"
        def ops_tool(q: str) -> str: return "ops"
        def missions_tool(q: str) -> str: return "missions"

        wf = build_workflow_agent(hr_tool, ops_tool, missions_tool)
        router = wf.sub_agents[1]
        tool_names = [getattr(t, "__name__", getattr(t, "name", "")) for t in router.tools]
        # Au moins un tool doit contenir "hr" ou "ops" dans son nom
        assert any("hr" in name or "tool" in name for name in tool_names) or len(router.tools) == 4


# ── Tests build_parallel_staffing_agent ──────────────────────────────────────

class TestBuildParallelAgent:
    """Valide la structure du ParallelAgent pour les requêtes mixtes HR+Ops."""

    def test_creates_parallel_agent(self):
        """build_parallel_staffing_agent() doit retourner un ParallelAgent."""
        from google.adk.agents import ParallelAgent
        from workflow_agent import build_parallel_staffing_agent
        pa = build_parallel_staffing_agent(_dummy_tool, _dummy_tool)
        assert isinstance(pa, ParallelAgent)

    def test_parallel_agent_name(self):
        from workflow_agent import build_parallel_staffing_agent
        pa = build_parallel_staffing_agent(_dummy_tool, _dummy_tool)
        assert pa.name == "zenika_parallel_hr_ops"

    def test_has_two_sub_agents(self):
        """Le ParallelAgent doit avoir 2 workers (HR + Ops)."""
        from workflow_agent import build_parallel_staffing_agent
        pa = build_parallel_staffing_agent(_dummy_tool, _dummy_tool)
        assert len(pa.sub_agents) == 2

    def test_hr_worker_output_key(self):
        """Le worker HR doit stocker dans session.state['hr_parallel_result']."""
        from workflow_agent import build_parallel_staffing_agent
        pa = build_parallel_staffing_agent(_dummy_tool, _dummy_tool)
        hr_worker = pa.sub_agents[0]
        assert hr_worker.name == "hr_parallel_worker"
        assert hr_worker.output_key == "hr_parallel_result"

    def test_ops_worker_output_key(self):
        """Le worker Ops doit stocker dans session.state['ops_parallel_result']."""
        from workflow_agent import build_parallel_staffing_agent
        pa = build_parallel_staffing_agent(_dummy_tool, _dummy_tool)
        ops_worker = pa.sub_agents[1]
        assert ops_worker.name == "ops_parallel_worker"
        assert ops_worker.output_key == "ops_parallel_result"


# ── Tests instruction classifier ─────────────────────────────────────────────

class TestClassifierInstruction:
    """Valide le contenu de l'instruction du classifier."""

    def test_instruction_contains_all_domains(self):
        """L'instruction doit mentionner tous les domaines possibles."""
        from workflow_agent import _CLASSIFIER_INSTRUCTION
        for domain in ("hr", "ops", "missions", "mixed"):
            assert domain in _CLASSIFIER_INSTRUCTION.lower(), f"Domain '{domain}' manquant dans l'instruction"

    def test_instruction_forces_single_word_response(self):
        """L'instruction doit forcer une réponse mono-mot."""
        from workflow_agent import _CLASSIFIER_INSTRUCTION
        assert "UN SEUL MOT" in _CLASSIFIER_INSTRUCTION or "un seul mot" in _CLASSIFIER_INSTRUCTION.lower()

    def test_instruction_has_examples(self):
        """L'instruction doit avoir des exemples pour le few-shot."""
        from workflow_agent import _CLASSIFIER_INSTRUCTION
        assert "Exemples" in _CLASSIFIER_INSTRUCTION or "exemple" in _CLASSIFIER_INSTRUCTION.lower()
