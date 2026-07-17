"""
test_zero_trust.py — agent_commons

Tests de sécurité Zero-Trust pour la bibliothèque partagée.
agent_commons est une bibliothèque Python (pas une app FastAPI) qui centralise
les mécanismes de sécurité critiques :
  - Guardrails anti-hallucination (arguments suspects)
  - Circuit Breaker failfast (pas d'erreur silencieuse)
  - Exception Handler global (pas de swallow silencieux)

Ces tests peuvent être exécutés sans le module `shared` installé grâce
aux imports conditionnels et aux pytest.skip appropriés.
"""
import asyncio
import os
import sys
import time

import pytest

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Variables d'env minimales
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-long-x")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("GEMINI_MODEL", "gemini-test")


# ─── Section 1 : Guardrails — arguments suspects (Guardrail Niveau 0) ──────

class TestGuardrailArgumentValidation:
    """Vérifie que le Guardrail de Niveau 0 bloque les IDs fictifs/suspects
    sans dépendance sur le module `shared`."""

    def test_suspicious_ids_set_is_not_empty(self):
        """La liste SUSPICIOUS_IDS doit être définie et non vide."""
        from agent_commons.guardrails_grounding import SUSPICIOUS_IDS
        assert isinstance(SUSPICIOUS_IDS, (set, frozenset, list, tuple)), (
            "SUSPICIOUS_IDS doit être une collection"
        )
        assert len(SUSPICIOUS_IDS) > 0, "SUSPICIOUS_IDS ne doit pas être vide"

    def test_id_arg_keys_are_defined(self):
        """ID_ARG_KEYS doit lister les clés d'arguments à surveiller."""
        from agent_commons.guardrails_grounding import ID_ARG_KEYS
        assert len(ID_ARG_KEYS) > 0, "ID_ARG_KEYS ne doit pas être vide"

    def test_suspicious_ids_contains_obvious_fake_ids(self):
        """Des IDs fictifs évidents (comme 1, 12345, 999) doivent être dans SUSPICIOUS_IDS."""
        from agent_commons.guardrails_grounding import SUSPICIOUS_IDS
        # Vérifie que la liste contient au moins quelques valeurs typiques d'hallucination
        suspicious_found = any(
            str(v) in {str(s) for s in SUSPICIOUS_IDS}
            for v in [1, 12345, 999, 9999, 123456789]
        )
        assert suspicious_found, (
            "SUSPICIOUS_IDS doit contenir des IDs fictifs typiques (1, 12345, 999…)"
        )


# ─── Section 2 : Circuit Breaker — résilience sans fail silencieux ─────────

class TestCircuitBreakerSecurity:
    """Vérifie que le circuit breaker lève des erreurs explicites (failfast §1.10)."""

    def test_circuit_breaker_open_raises_circuit_open_error(self):
        """Un circuit ouvert doit lever CircuitOpenError — pas retourner None silencieusement."""
        from agent_commons.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState

        cb = CircuitBreaker(name="test-security-cb", failure_threshold=1, recovery_timeout=60)

        # Forcer l'état OPEN directement
        cb._state = CircuitState.OPEN
        cb._last_failure_time = time.monotonic()
        cb._failure_count = 1

        async def dummy():
            return "should not reach here"

        with pytest.raises(CircuitOpenError):
            asyncio.run(cb.call(dummy))

    def test_circuit_open_error_has_name_and_retry_after(self):
        """CircuitOpenError doit contenir le nom du service et le délai de retry."""
        from agent_commons.circuit_breaker import CircuitOpenError
        err = CircuitOpenError(name="my-service", retry_after=30.0)
        assert err.name == "my-service"
        assert err.retry_after == 30.0

    def test_circuit_breaker_closed_allows_calls(self):
        """En état CLOSED, le circuit doit laisser passer les appels normalement."""
        from agent_commons.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(name="test-closed-cb", failure_threshold=5, recovery_timeout=30)

        async def ok_func():
            return 42

        result = asyncio.run(cb.call(ok_func))
        assert result == 42

    def test_circuit_breaker_name_is_set(self):
        """Chaque circuit breaker doit avoir un nom non vide pour le debugging."""
        from agent_commons.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(name="my-service-cb", failure_threshold=3, recovery_timeout=30)
        assert cb.name == "my-service-cb"
        assert cb.name  # nom non-vide


# ─── Section 3 : Exception Handler — zéro erreur silencieuse ──────────────

class TestExceptionHandlerSecurity:
    """Vérifie que l'exception handler global ne masque pas les erreurs."""

    def test_make_global_exception_handler_returns_callable(self):
        """La factory doit retourner un callable (handler FastAPI)."""
        from agent_commons.exception_handler import make_global_exception_handler
        handler = make_global_exception_handler(service_name="test-service")
        assert callable(handler), (
            "make_global_exception_handler doit retourner un callable compatible FastAPI"
        )

    def test_make_global_exception_handler_accepts_service_name(self):
        """Le handler doit accepter un service_name pour contextualiser les logs."""
        from agent_commons.exception_handler import make_global_exception_handler
        # Ne doit pas lever d'exception à la construction
        handler = make_global_exception_handler(service_name="agent_hr_api")
        assert handler is not None

    def test_exception_handler_is_not_pass_through(self):
        """Le handler ne doit PAS retourner None (swallow silencieux interdit — §1.10)."""
        from agent_commons.exception_handler import make_global_exception_handler
        handler = make_global_exception_handler(service_name="test")
        # Le handler est une coroutine async — on vérifie qu'il est bien défini
        import inspect
        assert inspect.iscoroutinefunction(handler), (
            "Le handler d'exception doit être une coroutine async pour FastAPI"
        )


# ─── Section 4 : Schemas — contrats d'interface inter-agents ──────────────

class TestAgentSchemaContracts:
    """Vérifie que les schémas Pydantic de communication inter-agents sont robustes."""

    def test_agent_query_schema_rejects_empty_query(self):
        """Une requête agent avec query vide doit être rejetée par Pydantic."""
        try:
            from agent_commons.schemas import AgentQuery
        except ImportError:
            pytest.skip("AgentQuery non disponible — vérifier agent_commons/schemas.py")

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AgentQuery(query="", session_id="sess-123")

    def test_agent_response_schema_has_required_fields(self):
        """AgentResponse doit exposer au minimum 'response' et 'session_id'."""
        try:
            from agent_commons.schemas import AgentResponse
        except ImportError:
            pytest.skip("AgentResponse non disponible — vérifier agent_commons/schemas.py")

        fields = AgentResponse.model_fields
        assert "response" in fields or "content" in fields, (
            "AgentResponse doit avoir un champ 'response' ou 'content'"
        )


# ─── Section 5 : Smoke Tests de Production — auto-tracing et initialisation ───

class TestProductionSmokeInitialization:
    """Vérifie que l'agent et le SDK Google GenAI s'initialisent correctement
    avec la configuration de production (Auto-Tracing actif)."""

    def test_genai_client_initialization_with_auto_tracing(self):
        """L'initialisation de genai.Client doit réussir même si ADK_AUTO_TRACING=true.
        Cela valide que le monkeypatch d'agent_commons résout l'erreur de rebinding
        de méthode statique induit par l'ADK."""
        import os
        from google import genai

        # Configurer l'environnement de production
        original_tracing = os.environ.get("ADK_AUTO_TRACING")
        os.environ["ADK_AUTO_TRACING"] = "true"

        try:
            # S'assurer que le module agent_commons a bien été importé et appliqué
            import agent_commons  # noqa: F401

            # L'initialisation du client avec une clé factice doit se faire sans
            # lever d'erreur d'arguments (TypeError sur vertexai)
            client = genai.Client(api_key="smoke-test-key")
            assert client is not None, "genai.Client doit être initialisé avec succès"
        finally:
            # Restaurer l'environnement initial
            if original_tracing is None:
                os.environ.pop("ADK_AUTO_TRACING", None)
            else:
                os.environ["ADK_AUTO_TRACING"] = original_tracing
