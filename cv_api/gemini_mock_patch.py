"""
gemini_mock_patch.py — Monkeypatch google-genai pour les tests de performance locaux.

Ce module DOIT etre importe EN PREMIER dans main.py (avant tout import de src.*
qui transitoirement importe config.py, lequel cree genai.Client() a l'import).

Activation : variable d'environnement GEMINI_API_BASE_URL=http://mock_gemini:8099.
Inactif en production (variable absente -> aucune modification du comportement SDK).

Pattern identique a agent_commons/__init__.py :
  - env var lue a CHAQUE creation de client (pas a l'import) -> robuste aux races
  - patch toujours applique, redirection conditionnelle a l'existence de la var
  - baseUrl (alias camelCase Pydantic) = meme convention que agent_commons
"""
import logging
import os

logger = logging.getLogger(__name__)


try:
    from google import genai
    from google.genai import types

    _original_genai_init = genai.Client.__init__

    def _patched_genai_init(self, *args, **kwargs):
        """Intercepte genai.Client.__init__ pour forcer base_url vers mock_gemini.

        Lit GEMINI_API_BASE_URL a chaque appel (pas a l'import) pour eviter
        les problemes de race condition au demarrage du conteneur.
        """
        gemini_base = os.getenv("GEMINI_API_BASE_URL")
        vertex_base = os.getenv("VERTEX_API_BASE_URL")

        is_vertex = kwargs.get("vertexai") or (len(args) > 0 and args[0] is True)
        base_url = vertex_base if (is_vertex and vertex_base) else gemini_base

        # Zero-Trust Production Guardrail (bypasses local mocks in GCP environments)
        if base_url:
            is_gcp_run = os.getenv("K_SERVICE") is not None
            is_local_mock = any(mock in base_url for mock in ["mock_gemini", "localhost", "127.0.0.1"])
            if is_gcp_run and is_local_mock:
                logger.warning(
                    "[gemini_mock] ALERTE SECURITE : tentative de redirection vers un mock local (%s) "
                    "ignoree en production GCP.", base_url
                )
                base_url = None

        if base_url:
            http_opts = kwargs.get("http_options")
            if not http_opts:
                http_opts = types.HttpOptions()
            elif isinstance(http_opts, dict):
                http_opts = types.HttpOptions(**http_opts)
            http_opts.base_url = base_url
            kwargs["http_options"] = http_opts

            if not is_vertex and not kwargs.get("api_key"):
                kwargs["api_key"] = "mock-key-local"

            logger.info("[gemini_mock] genai.Client redirige vers %s", base_url)

        _original_genai_init(self, *args, **kwargs)

    genai.Client.__init__ = _patched_genai_init
    logger.debug("[gemini_mock] Monkeypatch applique (activation conditionnelle via GEMINI_API_BASE_URL)")

except (ImportError, AttributeError):
    # ImportError   : google-genai non installe (environnement minimal)
    # AttributeError: genai.Client est deja un MagicMock (contexte test_e2e_stateless)
    #                 -> unittest.mock refuse qu'on set __init__ sur un Mock
    logger.warning("[gemini_mock] google-genai non disponible ou deja mocke — patch ignore")
