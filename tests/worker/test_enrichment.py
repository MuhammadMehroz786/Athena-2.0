from unittest.mock import AsyncMock

import pytest

from athena.integrations.domotz_client import (
    DomotzNotFoundError,
    DomotzRateLimitError,
)
from athena.worker.enrichment import resolve_device_importance


@pytest.mark.asyncio
async def test_non_domotz_vendor_returns_false_no_call():
    client = AsyncMock()
    result = await resolve_device_importance(client, "unifi", "site-1", "dev-1")
    assert result is False
    client.get_device.assert_not_called()


@pytest.mark.asyncio
async def test_missing_vendor_device_id_returns_false_no_call():
    client = AsyncMock()
    result = await resolve_device_importance(client, "domotz", "site-1", None)
    assert result is False
    client.get_device.assert_not_called()


@pytest.mark.asyncio
async def test_is_important_true_key():
    client = AsyncMock()
    client.get_device = AsyncMock(return_value={"is_important": True})
    result = await resolve_device_importance(client, "domotz", "site-1", "dev-1")
    assert result is True


@pytest.mark.asyncio
async def test_fallback_important_key():
    client = AsyncMock()
    client.get_device = AsyncMock(return_value={"important": True})
    result = await resolve_device_importance(client, "domotz", "site-1", "dev-1")
    assert result is True


@pytest.mark.asyncio
async def test_empty_device_returns_false():
    client = AsyncMock()
    client.get_device = AsyncMock(return_value={})
    result = await resolve_device_importance(client, "domotz", "site-1", "dev-1")
    assert result is False


@pytest.mark.asyncio
async def test_explicit_false_returns_false():
    client = AsyncMock()
    client.get_device = AsyncMock(return_value={"is_important": False})
    result = await resolve_device_importance(client, "domotz", "site-1", "dev-1")
    assert result is False


@pytest.mark.asyncio
async def test_not_found_treats_as_not_important():
    client = AsyncMock()
    client.get_device = AsyncMock(
        side_effect=DomotzNotFoundError("no device", status_code=404, url="x")
    )
    result = await resolve_device_importance(client, "domotz", "site-1", "dev-1")
    assert result is False


@pytest.mark.asyncio
async def test_rate_limit_reraised():
    client = AsyncMock()
    client.get_device = AsyncMock(
        side_effect=DomotzRateLimitError("slow down", status_code=429, url="x")
    )
    with pytest.raises(DomotzRateLimitError):
        await resolve_device_importance(client, "domotz", "site-1", "dev-1")


@pytest.mark.asyncio
async def test_importance_string_false_treated_as_false():
    client = AsyncMock()
    client.get_device = AsyncMock(return_value={"is_important": "false"})
    result = await resolve_device_importance(client, "domotz", "site-1", "dev-1")
    assert result is False


@pytest.mark.asyncio
async def test_importance_string_true_treated_as_true():
    client = AsyncMock()
    client.get_device = AsyncMock(return_value={"is_important": "true"})
    result = await resolve_device_importance(client, "domotz", "site-1", "dev-1")
    assert result is True
