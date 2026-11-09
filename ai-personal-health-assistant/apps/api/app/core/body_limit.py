from fastapi import HTTPException
from starlette.responses import JSONResponse
from app.core.config import settings
import json
import math


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = settings.max_upload_bytes if scope["path"] == "/api/v1/me/documents" else 1024 * 1024
        headers = dict(scope.get("headers", []))
        try:
            too_large = int(headers.get(b"content-length", b"0")) > limit
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, 400)(scope, receive, send)
        if too_large:
            return await JSONResponse({"detail": "Request body exceeds limit"}, 413)(scope, receive, send)
        total = 0

        if scope["method"] not in ("GET", "HEAD", "OPTIONS") and scope["path"] != "/api/v1/me/documents":
            messages, pieces = [], []
            while True:
                message = await receive()
                messages.append(message)
                if message["type"] == "http.disconnect":
                    return
                total += len(message.get("body", b""))
                if total > limit:
                    return await JSONResponse({"detail": "Request body exceeds limit"}, 413)(scope, receive, send)
                pieces.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            raw = b"".join(pieces)
            if raw:
                content_type = headers.get(b"content-type", b"").split(b";")[0].strip().lower()
                if content_type not in (b"", b"application/json"):
                    return await JSONResponse({"detail": "Use application/json"}, 415)(scope, receive, send)
                def invalid_constant(_):
                    raise ValueError("Non-finite JSON numbers are not supported")
                def finite_float(value):
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("Non-finite JSON numbers are not supported")
                    return number
                try:
                    json.loads(raw, parse_constant=invalid_constant, parse_float=finite_float)
                except (ValueError, UnicodeDecodeError):
                    return await JSONResponse({"detail": "Expected valid finite JSON"}, 400)(scope, receive, send)

            async def replay():
                if messages:
                    return messages.pop(0)
                return await receive()
            return await self.app(scope, replay, send)

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise HTTPException(413, "Request body exceeds limit")
            return message

        return await self.app(scope, bounded_receive, send)
