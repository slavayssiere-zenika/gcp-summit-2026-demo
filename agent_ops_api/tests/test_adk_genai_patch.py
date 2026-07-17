# Copyright 2026 Zenika — Golden Rules Compliance Test
import os
import pytest
from opentelemetry import trace


try:
    from google.adk.plugins.auto_tracing_plugin import AutoTracingPlugin
    HAS_AUTO_TRACING_PLUGIN = True
except ImportError:
    HAS_AUTO_TRACING_PLUGIN = False


@pytest.mark.skipif(not HAS_AUTO_TRACING_PLUGIN, reason="AutoTracingPlugin non disponible dans cette version de l'ADK")
def test_adk_genai_patch_validation_in_agent_ops():
    """Vérifie que le correctif d'agent_commons sur BaseApiClient._ensure_httpx_ssl_ctx
    intercepte le rebinding défectueux de l'ADK et permet l'instanciation de genai.Client()
    dans le contexte d'exécution de l'agent_ops.
    """
    # 0. Importer agent_commons pour appliquer activement les monkeypatches du projet
    import agent_commons  # noqa: F401

    # 1. Configurer un environnement avec une clé d'API factice
    os.environ["ADK_AUTO_TRACING"] = "true"
    os.environ["GEMINI_API_KEY"] = "fake-api-key-for-test-validation"

    # 2. Importer les modules requis après l'application du patch
    from google import genai
    from google.genai._api_client import BaseApiClient

    # 3. Simuler le rebinding de l'ADK qui détruit le descripteur staticmethod
    tracer = trace.get_tracer("test-tracer")
    plugin = AutoTracingPlugin(tracer=tracer)

    current_method = BaseApiClient._ensure_httpx_ssl_ctx

    plugin._rebind(BaseApiClient, "_ensure_httpx_ssl_ctx", current_method)

    # 4. Tenter l'instanciation du client
    # Si le patch fonctionne, cela réussit. S'il ne fonctionne pas, cela lève un TypeError.
    try:
        client = genai.Client()
        assert client is not None
    except TypeError as e:
        pytest.fail(f"Le correctif d'auto-tracing ADK a échoué. TypeError : {e}")
