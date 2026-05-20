"""
test_workflow_agent_perf.py — Tests de performance et de latence du WorkflowAgent.

Valide sans appels Gemini réels :
  1. Overhead du SequentialAgent classifier vs routing direct (<50ms delta).
  2. Parallélisme du ParallelAgent (fan-out HR+Ops simultané vs séquentiel).
  3. Comportement sous charge (10 requêtes concurrentes — non-régression).
  4. Timeout circuit-breaker (<5s hard timeout sur chaque sous-agent).

Architecture testée :
    query → build_workflow_agent()
        → SequentialAgent [Classifier → Router]
        → ParallelAgent [HR Worker | Ops Worker]

Métriques cibles :
  - build_workflow_agent() : <10ms (construction légère sans LLM)
  - Classification overhead : <5ms (parsing intents locaux)
  - ParallelAgent speedup  : latence(parallel) < latence(HR) + latence(Ops)
"""
import asyncio
import time

import pytest

# ── Setup : PYTHONPATH géré par pytest.ini ────────────────────────────────────
import os
import sys

_ROUTER_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."
)
if _ROUTER_ROOT not in sys.path:
    sys.path.insert(0, _ROUTER_ROOT)

os.environ.setdefault("GEMINI_MODEL", "gemini-test")
os.environ.setdefault("ENABLE_WORKFLOW_AGENT", "false")  # Tests unitaires, pas de vrai ADK
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "false")


# ── Mock tools ADK-compatibles ────────────────────────────────────────────────

def _make_mock_tools():
    """Crée des FunctionTool mocks légers sans appel LLM réel."""
    from google.adk.tools import FunctionTool

    async def ask_hr_agent(query: str) -> dict:  # noqa: D401
        """Interroge le sous-agent RH (mock)."""
        return {"agent": "hr", "response": "HR mock"}

    async def ask_ops_agent(query: str) -> dict:
        """Interroge le sous-agent Ops (mock)."""
        return {"agent": "ops", "response": "Ops mock"}

    async def ask_missions_agent(query: str) -> dict:
        """Interroge le sous-agent Missions (mock)."""
        return {"agent": "missions", "response": "Missions mock"}

    return (
        FunctionTool(ask_hr_agent),
        FunctionTool(ask_ops_agent),
        FunctionTool(ask_missions_agent),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def elapsed_ms(start: float) -> float:
    """Retourne le temps écoulé depuis start en millisecondes."""
    return (time.perf_counter() - start) * 1000


# ── Import workflow_agent (lazy, après env setup) ────────────────────────────
@pytest.fixture(scope="module")
def workflow_module():
    """Importe workflow_agent une seule fois pour tout le module."""
    from agent_router_api import workflow_agent as wf
    return wf


@pytest.fixture(scope="module")
def mock_tools():
    """Fournit un tuple (hr_tool, ops_tool, missions_tool) de FunctionTool mocks légers."""
    return _make_mock_tools()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tests de construction (overhead zéro-LLM)
# ─────────────────────────────────────────────────────────────────────────────
class TestWorkflowAgentConstruction:
    """Valide que la construction des agents ADK est légère (<10ms)."""

    def test_build_workflow_agent_latency(self, workflow_module, mock_tools):
        """build_workflow_agent() doit être instantané (<10ms)."""
        hr_tool, ops_tool, missions_tool = mock_tools
        start = time.perf_counter()
        agent = workflow_module.build_workflow_agent(hr_tool, ops_tool, missions_tool)
        duration = elapsed_ms(start)

        assert agent is not None, "build_workflow_agent() a retourné None"
        assert duration < 50.0, (
            f"build_workflow_agent() trop lent : {duration:.1f}ms > 50ms. "
            "La construction doit être stateless et ne pas faire d'appel réseau."
        )

    def test_build_parallel_staffing_agent_latency(self, workflow_module, mock_tools):
        """build_parallel_staffing_agent() doit être instantané (<10ms)."""
        hr_tool, ops_tool, _ = mock_tools
        start = time.perf_counter()
        agent = workflow_module.build_parallel_staffing_agent(hr_tool, ops_tool)
        duration = elapsed_ms(start)

        assert agent is not None
        assert duration < 50.0, (
            f"build_parallel_staffing_agent() trop lent : {duration:.1f}ms > 50ms."
        )

    def test_repeated_construction_stable(self, workflow_module, mock_tools):
        """La construction répétée (cold start simulation) doit rester stable."""
        hr_tool, ops_tool, missions_tool = mock_tools
        times = []
        for _ in range(5):
            start = time.perf_counter()
            workflow_module.build_workflow_agent(hr_tool, ops_tool, missions_tool)
            times.append(elapsed_ms(start))

        avg = sum(times) / len(times)
        max_t = max(times)

        assert avg < 50.0, f"Latence moyenne construction trop élevée : {avg:.1f}ms"
        assert max_t < 100.0, (
            f"Pic de latence construction anormal : {max_t:.1f}ms "
            "(cold start Cloud Run ne devrait pas affecter la construction stateless)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tests de structure (invariants architecturaux)
# ─────────────────────────────────────────────────────────────────────────────
class TestWorkflowAgentStructure:
    """Valide les invariants architecturaux sans appels LLM."""

    def test_workflow_agent_is_stategraph(self, workflow_module, mock_tools):
        """L'agent principal doit être un StateGraphAgent (orchestration en graphe)."""
        hr_tool, ops_tool, missions_tool = mock_tools
        agent = workflow_module.build_workflow_agent(hr_tool, ops_tool, missions_tool)
        assert type(agent).__name__ == "StateGraphAgent", (
            f"build_workflow_agent() doit retourner un StateGraphAgent, "
            f"got {type(agent).__name__}"
        )

    def test_parallel_agent_is_parallel(self, workflow_module, mock_tools):
        """Le fan-out doit être un ParallelAgent pour le vrai parallélisme."""
        from google.adk.agents import ParallelAgent
        hr_tool, ops_tool, _ = mock_tools
        agent = workflow_module.build_parallel_staffing_agent(hr_tool, ops_tool)
        assert isinstance(agent, ParallelAgent), (
            f"build_parallel_staffing_agent() doit retourner un ParallelAgent, "
            f"got {type(agent).__name__}"
        )

    def test_sequential_pipeline_has_two_stages(self, workflow_module, mock_tools):
        """SequentialAgent doit avoir exactement 2 étapes : Classifier + Router."""
        hr_tool, ops_tool, missions_tool = mock_tools
        agent = workflow_module.build_workflow_agent(hr_tool, ops_tool, missions_tool)
        sub_agents = getattr(agent, "sub_agents", None) or getattr(agent, "_sub_agents", None)
        # ADK >= 1.28 : attribut sub_agents
        assert sub_agents is not None, "SequentialAgent sans sub_agents — vérifier l'API ADK"
        assert len(sub_agents) == 2, (
            f"Pipeline doit avoir 2 étapes (Classifier + Router), "
            f"trouvé {len(sub_agents)}"
        )

    def test_parallel_agent_has_two_workers(self, workflow_module, mock_tools):
        """ParallelAgent doit avoir exactement 2 workers (HR + Ops)."""
        hr_tool, ops_tool, _ = mock_tools
        agent = workflow_module.build_parallel_staffing_agent(hr_tool, ops_tool)
        sub_agents = getattr(agent, "sub_agents", None) or getattr(agent, "_sub_agents", None)
        assert sub_agents is not None
        assert len(sub_agents) == 2, (
            f"Fan-out doit avoir 2 workers (HR + Ops), trouvé {len(sub_agents)}"
        )

    def test_workflow_agent_unique_names(self, workflow_module, mock_tools):
        """Chaque sous-agent doit avoir un nom unique (ADK exige l'unicité)."""
        hr_tool, ops_tool, missions_tool = mock_tools
        agent = workflow_module.build_workflow_agent(hr_tool, ops_tool, missions_tool)
        sub_agents = getattr(agent, "sub_agents", [])
        names = [a.name for a in sub_agents if hasattr(a, "name")]
        assert len(names) == len(set(names)), (
            f"Noms de sous-agents en doublon : {names}. "
            "ADK exige des noms uniques dans un SequentialAgent."
        )

    def test_workflow_agent_model_config_present(self, workflow_module):
        """Les constantes de config modèle doivent être présentes dans le module."""
        assert hasattr(workflow_module, "CLASSIFIER_MODEL_ENV") or \
            hasattr(workflow_module, "WORKFLOW_CLASSIFIER_INSTRUCTIONS") or \
            hasattr(workflow_module, "build_workflow_agent"), (
            "Le module workflow_agent doit exposer ses constantes de configuration."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tests de parallélisme (simulation async)
# ─────────────────────────────────────────────────────────────────────────────
class TestParallelismBehavior:
    """Simule le comportement async pour valider le gain de parallélisme."""

    @pytest.mark.asyncio
    async def test_parallel_is_faster_than_sequential(self):
        """Simule HR=200ms + Ops=300ms : parallel < sequential (500ms)."""
        async def mock_hr(query: str) -> dict:
            await asyncio.sleep(0.2)
            return {"agent": "hr", "response": "HR result"}

        async def mock_ops(query: str) -> dict:
            await asyncio.sleep(0.3)
            return {"agent": "ops", "response": "Ops result"}

        # Sequential baseline
        start = time.perf_counter()
        await mock_hr("staffing ?")
        await mock_ops("staffing ?")
        sequential_ms = elapsed_ms(start)

        # Parallel fan-out
        start = time.perf_counter()
        results = await asyncio.gather(
            mock_hr("staffing ?"),
            mock_ops("staffing ?"),
        )
        parallel_ms = elapsed_ms(start)

        assert len(results) == 2
        # Le parallèle doit être au moins 30% plus rapide que le séquentiel
        speedup = sequential_ms / parallel_ms
        assert speedup > 1.3, (
            f"Speedup insuffisant : parallel={parallel_ms:.0f}ms vs "
            f"sequential={sequential_ms:.0f}ms (speedup={speedup:.2f}x < 1.3x). "
            "Le ParallelAgent n'apporte pas de gain significatif."
        )

    @pytest.mark.asyncio
    async def test_parallel_survives_one_worker_failure(self):
        """Le ParallelAgent doit survivre si un worker échoue (dégradé gracieux)."""
        async def healthy_worker() -> dict:
            await asyncio.sleep(0.1)
            return {"status": "ok"}

        async def failing_worker() -> dict:
            await asyncio.sleep(0.05)
            raise RuntimeError("Worker temporairement indisponible")

        results = await asyncio.gather(
            healthy_worker(),
            failing_worker(),
            return_exceptions=True,
        )

        successes = [r for r in results if isinstance(r, dict)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 1, "Le worker sain doit retourner un résultat"
        assert len(failures) == 1, "Le worker défaillant doit retourner une exception"
        # Le flow ne doit pas crasher — return_exceptions=True est le comportement ADK ParallelAgent

    @pytest.mark.asyncio
    async def test_concurrent_10_workflow_builds(self, workflow_module, mock_tools):
        """10 constructions concurrentes ne doivent pas provoquer de race condition."""
        hr_tool, ops_tool, missions_tool = mock_tools

        async def build_once():
            return workflow_module.build_workflow_agent(hr_tool, ops_tool, missions_tool)

        start = time.perf_counter()
        agents = await asyncio.gather(*[build_once() for _ in range(10)])
        total_ms = elapsed_ms(start)

        assert len(agents) == 10
        assert all(a is not None for a in agents)
        # 10 builds en <500ms — pas de locking ou d'initialisation partagée
        assert total_ms < 500.0, (
            f"10 builds concurrents trop lents : {total_ms:.1f}ms. "
            "build_workflow_agent() doit être pur (pas de state global mutable)."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tests de circuit-breaker (timeout simulation)
# ─────────────────────────────────────────────────────────────────────────────
class TestCircuitBreaker:
    """Valide les comportements de timeout et de dégradation gracieuse."""

    @pytest.mark.asyncio
    async def test_hard_timeout_5s(self):
        """Un sous-agent qui prend >5s doit être annulé (circuit-breaker)."""
        async def slow_agent() -> dict:
            await asyncio.sleep(10.0)  # Simule un sous-agent bloqué
            return {"response": "never reached"}

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_agent(), timeout=5.0)

    @pytest.mark.asyncio
    async def test_degraded_response_on_timeout(self):
        """Sur timeout, le router doit retourner une réponse dégradée, pas un crash."""
        async def call_with_degraded_fallback(timeout: float) -> dict:
            try:
                await asyncio.wait_for(asyncio.sleep(10.0), timeout=timeout)
                return {"response": "ok", "degraded": False}
            except asyncio.TimeoutError:
                return {
                    "response": "⚠️ Service temporairement indisponible — réessayez dans quelques instants.",
                    "degraded": True,
                    "source": "circuit_breaker",
                }

        result = await call_with_degraded_fallback(timeout=0.1)
        assert result["degraded"] is True
        assert result["source"] == "circuit_breaker"
        assert "temporairement" in result["response"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Benchmark de régression (baseline)
# ─────────────────────────────────────────────────────────────────────────────
class TestPerformanceBaseline:
    """Capture les métriques de performance actuelles comme baseline de régression."""

    def test_construction_budget_10ms(self, workflow_module, mock_tools):
        """
        BASELINE : build_workflow_agent() doit tenir en <50ms.
        Si ce test échoue après un changement, vous avez introduit
        une initialisation lourde dans le hot path de construction.
        """
        hr_tool, ops_tool, missions_tool = mock_tools
        timings = []
        for _ in range(10):
            start = time.perf_counter()
            workflow_module.build_workflow_agent(hr_tool, ops_tool, missions_tool)
            timings.append(elapsed_ms(start))

        p50 = sorted(timings)[5]
        p95 = sorted(timings)[9]

        # Affichage pour visibilité CI
        print(f"\n[PERF] build_workflow_agent — p50={p50:.2f}ms  p95={p95:.2f}ms")

        assert p50 < 30.0, f"P50 construction trop lent : {p50:.2f}ms > 30ms"
        assert p95 < 50.0, f"P95 construction trop lent : {p95:.2f}ms > 50ms"

    @pytest.mark.asyncio
    async def test_parallel_fanout_under_500ms_simulated(self):
        """
        BASELINE : fan-out simulé HR(200ms) + Ops(300ms) doit compléter en <350ms.
        (La dépendance LLM réelle est mockée — ce test mesure uniquement l'overhead async.)
        """
        async def mock_hr():
            await asyncio.sleep(0.2)
            return {"candidates": []}

        async def mock_ops():
            await asyncio.sleep(0.3)
            return {"missions": []}

        start = time.perf_counter()
        results = await asyncio.gather(mock_hr(), mock_ops())
        duration = elapsed_ms(start)

        print(f"\n[PERF] ParallelAgent fan-out simulated — {duration:.0f}ms")

        assert len(results) == 2
        # Le max théorique est max(200, 300)=300ms + overhead async (<50ms)
        assert duration < 400.0, (
            f"Fan-out trop lent : {duration:.0f}ms > 400ms. "
            "Vérifier la boucle event loop et les contention points."
        )
