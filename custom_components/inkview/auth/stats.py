"""Per-session activity tracking for the binary_sensor + diagnostics.

Lives in `hass.data[DOMAIN][DATA_SESSIONS][instance_id]['stats']`. All methods
are sync — these are hot-path mutations from request handlers."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

_WINDOW_SECONDS = 24 * 3600


@dataclass
class SessionStats:
    last_token_minted_at: float | None = None
    last_token_expires_at: float | None = None
    last_state_fetch_at: float | None = None
    last_failed_auth_at: float | None = None
    _tokens: deque[float] = field(default_factory=deque)
    _failures: deque[float] = field(default_factory=deque)

    def record_token_issued(self, expires_at: float | None = None) -> None:
        now = time.time()
        self.last_token_minted_at = now
        self.last_token_expires_at = expires_at
        self._tokens.append(now)
        self._evict()

    def record_state_fetch(self) -> None:
        self.last_state_fetch_at = time.time()

    def record_failed_auth(self) -> None:
        now = time.time()
        self.last_failed_auth_at = now
        self._failures.append(now)
        self._evict()

    def _evict(self) -> None:
        cutoff = time.time() - _WINDOW_SECONDS
        while self._tokens and self._tokens[0] < cutoff:
            self._tokens.popleft()
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def snapshot(self) -> dict[str, float | int | None]:
        self._evict()
        return {
            "last_token_minted_at": self.last_token_minted_at,
            "last_token_expires_at": self.last_token_expires_at,
            "last_state_fetch_at": self.last_state_fetch_at,
            "last_failed_auth_at": self.last_failed_auth_at,
            "tokens_issued_24h": len(self._tokens),
            "failed_auth_24h": len(self._failures),
        }
