"""Pure-ASGI middleware: request ids and in-memory rate limiting.

Pure ASGI (rather than BaseHTTPMiddleware) so streamed agent responses are not buffered.
"""

import json
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import AppError, error_body

logger = logging.getLogger("farmagent.http")


class RequestContextMiddleware:
    """Adds an X-Request-ID to each response and logs one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # Paths only: query strings can hold locations the farmer searched for.
            logger.info(
                "%s %s status=%s ms=%.0f request_id=%s",
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - started) * 1000,
                request_id,
            )


class SafeErrorMiddleware:
    """Turns an unhandled exception into safe JSON.

    Starlette's own catch-all runs outside CORSMiddleware, so a browser would see its 500 as a CORS
    failure and never read the error. This sits inside CORS, so the error reaches the frontend.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            request_id = scope.get("state", {}).get("request_id")
            logger.exception("unhandled error request_id=%s", request_id)
            if started:
                raise
            body = json.dumps(error_body("internal_error", AppError.message, request_id)).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})


class SlidingWindowLimiter:
    """A per-key sliding window. Per-process: one Render instance is the deployment target."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, window: float = 60.0) -> None:
        self._clock = clock
        self._window = window
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep = clock()

    def check(self, key: str, limit: int) -> float | None:
        """Record a hit, or return seconds to wait if the key is over its limit."""
        now = self._clock()
        self._sweep(now)
        hits = self._hits.setdefault(key, deque())
        cutoff = now - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= limit:
            return max(hits[0] + self._window - now, 0.0)
        hits.append(now)
        return None

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < self._window:
            return
        self._last_sweep = now
        cutoff = now - self._window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]


class RateLimitMiddleware:
    def __init__(
        self, app: ASGIApp, settings: Settings, limiter: SlidingWindowLimiter | None = None
    ):
        self.app = app
        self.settings = settings
        self.limiter = limiter or SlidingWindowLimiter()

    def _limit_for(self, path: str) -> tuple[str, int]:
        s = self.settings
        if path.startswith("/api/agent") or path.startswith("/api/scenarios"):
            return "agent", s.rate_limit_agent_per_minute
        if path.startswith("/api/session/guest"):
            return "session", s.rate_limit_session_per_minute
        return "default", s.rate_limit_default_per_minute

    def _client_id(self, scope: Scope) -> str:
        if self.settings.trust_proxy_headers:
            forwarded = Headers(scope=scope).get("x-forwarded-for")
            if forwarded:
                # Render appends the address it saw, so the last hop is the trustworthy one.
                return forwarded.split(",")[-1].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not self.settings.rate_limit_enabled
            or scope["method"] == "OPTIONS"
            or not scope["path"].startswith("/api/")
            or scope["path"] == "/api/health"
        ):
            await self.app(scope, receive, send)
            return

        bucket, limit = self._limit_for(scope["path"])
        wait = self.limiter.check(f"{bucket}:{self._client_id(scope)}", limit)
        if wait is None:
            await self.app(scope, receive, send)
            return

        retry_after = str(max(int(wait) + 1, 1))
        body = json.dumps(
            error_body(
                "rate_limited",
                "Too many requests. Wait a moment and try again.",
                scope.get("state", {}).get("request_id"),
            )
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", retry_after.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
