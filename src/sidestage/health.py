"""Campaign health status tracking with transition callbacks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class CampaignHealth:
    """Manages campaign health status with transition logic."""

    def __init__(
        self,
        on_change: Callable[[HealthStatus, str], Awaitable[None]] | None = None,
    ):
        self.status = HealthStatus.HEALTHY
        self.reason = ""
        self._on_change = on_change
        self._lock = asyncio.Lock()

    async def set_status(self, status: HealthStatus, reason: str) -> None:
        """Transition to a new status, firing on_change if status actually changed."""
        async with self._lock:
            changed = status != self.status
            self.status = status
            self.reason = reason
            if changed and self._on_change is not None:
                try:
                    await self._on_change(status, reason)
                except Exception:
                    logger.exception("on_change callback failed for %s", status)

    @property
    def is_accepting_chat(self) -> bool:
        """True if HEALTHY or DEGRADED."""
        return self.status != HealthStatus.UNHEALTHY

    @property
    def is_embedding_available(self) -> bool:
        """True only if HEALTHY."""
        return self.status == HealthStatus.HEALTHY
