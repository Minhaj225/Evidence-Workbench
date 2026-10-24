from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class UploadLimit:
    """Bound multipart bytes before Starlette spools the upload to disk."""

    def __init__(self, app: ASGIApp, maximum: int):
        self.app, self.maximum = app, maximum + 65536

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope["path"] != "/api/documents"
        ):
            await self.app(scope, receive, send)
            return
        size = 0

        async def bounded_receive() -> Message:
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self.maximum:
                    raise HTTPException(413)
            return message

        await self.app(scope, bounded_receive, send)
