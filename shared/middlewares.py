class ContentLengthSanitizerASGIMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = scope.get("headers", [])
            for i, (k, v) in enumerate(headers):
                if k.lower() == b"content-length" and not v.strip():
                    headers[i] = (b"content-length", b"0")
        return await self.app(scope, receive, send)
