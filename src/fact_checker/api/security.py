"""Access-code check and per-IP rate limit of the API, with their state kept on the app."""

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

POSTS_PER_WINDOW = 30
WINDOW_SECONDS = 60.0
WRONG_CODES_PER_WINDOW = 10


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

    def blocked(self, key: str) -> bool:
        """Return True when key has `limit` or more hits in the current window; records nothing."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            return len(hits) >= self._limit


def client_key(request: Request) -> str:
    """Return the configured client-IP header's stripped value when present, else the peer host, else "unknown"."""
    header = request.app.state.settings.client_ip_header
    value = request.headers.get(header, "").strip() if header else ""
    if value:
        return value
    return request.client.host if request.client else "unknown"


def require_access_code(request: Request, x_access_code: str | None = Header(default=None)) -> None:
    """Raise 401 unless X-Access-Code equals the configured code, 429 after too many wrong ones; off when unset."""
    expected = request.app.state.settings.access_code
    if expected is None:
        return
    key = client_key(request)
    if request.app.state.code_failures.blocked(key):
        raise HTTPException(status_code=429, detail="too many wrong access codes, try again in a minute")
    given = (x_access_code or "").encode()
    if not hmac.compare_digest(given, expected.encode()):
        if given:
            request.app.state.code_failures.allow(key)
        raise HTTPException(status_code=401, detail="access code required")


def limit_posts(request: Request) -> None:
    """Raise 429 when the client IP has made more than 30 POSTs in the last minute; GETs are not counted."""
    if request.method != "POST":
        return
    if not request.app.state.rate_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="too many requests, try again in a minute")
