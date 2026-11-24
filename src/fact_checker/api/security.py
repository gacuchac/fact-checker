"""Access-code check and per-IP rate limit of the API, with their state kept on the app."""

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

POSTS_PER_WINDOW = 30
WINDOW_SECONDS = 60.0


class RateLimiter:
    """A sliding-window counter of requests per client key."""

    def __init__(self, limit: int = POSTS_PER_WINDOW, window: float = WINDOW_SECONDS) -> None:
        """Allow `limit` hits per `window` seconds for each key."""
        self._limit = limit
        self._window = window
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record a hit for key and return True, or return False without recording when key is over its limit."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True


def require_access_code(request: Request, x_access_code: str | None = Header(default=None)) -> None:
    """Raise 401 unless X-Access-Code equals the configured access code; no check when none is configured."""
    expected = request.app.state.settings.access_code
    if expected is None:
        return
    given = (x_access_code or "").encode()
    if not hmac.compare_digest(given, expected.encode()):
        raise HTTPException(status_code=401, detail="access code required")


def limit_posts(request: Request) -> None:
    """Raise 429 when the client IP has made more than 30 POSTs in the last minute; GETs are not counted."""
    if request.method != "POST":
        return
    host = request.client.host if request.client else "unknown"
    if not request.app.state.rate_limiter.allow(host):
        raise HTTPException(status_code=429, detail="too many requests, try again in a minute")
