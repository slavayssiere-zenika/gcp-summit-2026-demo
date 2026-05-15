"""Tests de la middleware ContentLengthSanitizerASGIMiddleware.

Vérifie que la middleware corrige silencieusement les headers Content-Length
vides — comportement observé sur certains clients HTTP (notamment curl et
certains proxies) qui envoient `Content-Length: ` (vide) au lieu de `0`.
"""
import pytest

from shared.middlewares import ContentLengthSanitizerASGIMiddleware


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_scope(headers: list[tuple[bytes, bytes]], scope_type: str = "http") -> dict:
    """Construit un scope ASGI minimal pour les tests."""
    return {"type": scope_type, "headers": list(headers)}


async def _noop_app(scope, receive, send):
    """Application ASGI no-op pour capturer l'état du scope après middleware."""
    pass


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestContentLengthSanitizerASGIMiddleware:
    """Tests du correcteur de header Content-Length vide."""

    @pytest.mark.asyncio
    async def test_corrige_content_length_vide(self):
        """Le header Content-Length vide doit être remplacé par b'0'."""
        captured = {}

        async def app(scope, receive, send):
            captured["headers"] = scope["headers"]

        scope = _make_scope([(b"content-length", b"")])
        mw = ContentLengthSanitizerASGIMiddleware(app)
        await mw(scope, None, None)

        assert dict(captured["headers"])[b"content-length"] == b"0"

    @pytest.mark.asyncio
    async def test_corrige_content_length_espaces(self):
        """Un header Content-Length contenant uniquement des espaces est vide."""
        captured = {}

        async def app(scope, receive, send):
            captured["headers"] = scope["headers"]

        scope = _make_scope([(b"content-length", b"   ")])
        mw = ContentLengthSanitizerASGIMiddleware(app)
        await mw(scope, None, None)

        assert dict(captured["headers"])[b"content-length"] == b"0"

    @pytest.mark.asyncio
    async def test_ne_modifie_pas_content_length_valide(self):
        """Un Content-Length valide (ex: b'42') ne doit pas être modifié."""
        captured = {}

        async def app(scope, receive, send):
            captured["headers"] = scope["headers"]

        scope = _make_scope([(b"content-length", b"42")])
        mw = ContentLengthSanitizerASGIMiddleware(app)
        await mw(scope, None, None)

        assert dict(captured["headers"])[b"content-length"] == b"42"

    @pytest.mark.asyncio
    async def test_ignore_scope_non_http(self):
        """Les scopes non-HTTP (websocket, lifespan) doivent être ignorés."""
        captured = {}

        async def app(scope, receive, send):
            captured["scope"] = scope

        scope = _make_scope([(b"content-length", b"")], scope_type="websocket")
        mw = ContentLengthSanitizerASGIMiddleware(app)
        await mw(scope, None, None)

        # Le header ne doit PAS avoir été modifié (scope non-HTTP)
        assert dict(scope["headers"])[b"content-length"] == b""

    @pytest.mark.asyncio
    async def test_preserve_autres_headers(self):
        """Les autres headers ne doivent pas être affectés par la correction."""
        captured = {}

        async def app(scope, receive, send):
            captured["headers"] = scope["headers"]

        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", b""),
            (b"authorization", b"Bearer token"),
        ]
        scope = _make_scope(headers)
        mw = ContentLengthSanitizerASGIMiddleware(app)
        await mw(scope, None, None)

        h = dict(captured["headers"])
        assert h[b"content-type"] == b"application/json"
        assert h[b"content-length"] == b"0"
        assert h[b"authorization"] == b"Bearer token"

    @pytest.mark.asyncio
    async def test_sans_content_length(self):
        """Un scope sans header Content-Length ne doit pas planter."""
        captured = {}

        async def app(scope, receive, send):
            captured["headers"] = scope["headers"]

        scope = _make_scope([(b"accept", b"application/json")])
        mw = ContentLengthSanitizerASGIMiddleware(app)
        await mw(scope, None, None)

        assert dict(captured["headers"])[b"accept"] == b"application/json"
