"""Small in-memory rate limits for a public deployment.

Every question costs NEAR AI credits and a testnet transaction, so a public
server caps them per visitor (per hour) and in total (per day). Limits are off
when their setting is 0, which is the default for local use.

Single-process only: fine for one container; counts reset on restart.
"""

from __future__ import annotations

import time
from collections import deque

from fastapi import HTTPException

HOUR = 3600
DAY = 86400


class RateLimiter:
    def __init__(self, per_ip_per_hour: int = 0, per_day: int = 0, what: str = "requests"):
        self.per_ip_per_hour = max(0, per_ip_per_hour)
        self.per_day = max(0, per_day)
        self.what = what
        self._by_ip: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()

    @property
    def enabled(self) -> bool:
        return bool(self.per_ip_per_hour or self.per_day)

    def check(self, ip: str | None) -> None:
        """Count one request from ip, or raise 429 if a limit is reached."""
        if not self.enabled:
            return
        now = time.time()
        if self.per_day:
            while self._all and self._all[0] < now - DAY:
                self._all.popleft()
            if len(self._all) >= self.per_day:
                raise HTTPException(429, f"This demo has reached today's limit of {self.per_day} {self.what}. Try again tomorrow.")
        if self.per_ip_per_hour:
            q = self._by_ip.setdefault(ip or "unknown", deque())
            while q and q[0] < now - HOUR:
                q.popleft()
            if len(q) >= self.per_ip_per_hour:
                wait = int(q[0] + HOUR - now) // 60 + 1
                raise HTTPException(429, f"You've reached the limit of {self.per_ip_per_hour} {self.what} an hour. Try again in about {wait} minutes.")
            q.append(now)
            if len(self._by_ip) > 10_000:  # forget idle visitors
                for k in [k for k, v in self._by_ip.items() if not v or v[-1] < now - HOUR]:
                    del self._by_ip[k]
        if self.per_day:
            self._all.append(now)
