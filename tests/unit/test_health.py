"""Tests for CampaignHealth and HealthStatus."""

import pytest
from unittest.mock import AsyncMock

from sidestage.health import HealthStatus, CampaignHealth


class TestHealthStatus:
    def test_enum_values(self):
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"


class TestCampaignHealth:
    def test_initializes_healthy(self):
        health = CampaignHealth()
        assert health.status == HealthStatus.HEALTHY

    @pytest.mark.anyio
    async def test_set_status_transitions(self):
        health = CampaignHealth()
        await health.set_status(HealthStatus.DEGRADED, "embed down")
        assert health.status == HealthStatus.DEGRADED
        assert health.reason == "embed down"

    @pytest.mark.anyio
    async def test_set_status_fires_on_change(self):
        callback = AsyncMock()
        health = CampaignHealth(on_change=callback)
        await health.set_status(HealthStatus.DEGRADED, "embed down")
        callback.assert_awaited_once_with(HealthStatus.DEGRADED, "embed down")

    @pytest.mark.anyio
    async def test_set_status_no_fire_when_unchanged(self):
        callback = AsyncMock()
        health = CampaignHealth(on_change=callback)
        await health.set_status(HealthStatus.HEALTHY, "still fine")
        callback.assert_not_awaited()

    @pytest.mark.anyio
    async def test_set_status_works_without_callback(self):
        health = CampaignHealth()
        await health.set_status(HealthStatus.DEGRADED, "no callback")
        assert health.status == HealthStatus.DEGRADED

    def test_is_accepting_chat_healthy(self):
        health = CampaignHealth()
        assert health.is_accepting_chat is True

    @pytest.mark.anyio
    async def test_is_accepting_chat_degraded(self):
        health = CampaignHealth()
        await health.set_status(HealthStatus.DEGRADED, "degraded")
        assert health.is_accepting_chat is True

    @pytest.mark.anyio
    async def test_is_accepting_chat_unhealthy(self):
        health = CampaignHealth()
        await health.set_status(HealthStatus.UNHEALTHY, "db down")
        assert health.is_accepting_chat is False

    def test_is_embedding_available_healthy(self):
        health = CampaignHealth()
        assert health.is_embedding_available is True

    @pytest.mark.anyio
    async def test_is_embedding_available_degraded(self):
        health = CampaignHealth()
        await health.set_status(HealthStatus.DEGRADED, "degraded")
        assert health.is_embedding_available is False

    @pytest.mark.anyio
    async def test_is_embedding_available_unhealthy(self):
        health = CampaignHealth()
        await health.set_status(HealthStatus.UNHEALTHY, "db down")
        assert health.is_embedding_available is False
