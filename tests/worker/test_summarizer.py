import logging
from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from athena.integrations.openai_client import OpenAIAPIError, OpenAIRateLimitError
from athena.worker.summarizer import generate_summary


def _event(**overrides):
    base = dict(
        vendor="domotz",
        event_type="device.down",
        severity="critical",
        occurred_at=datetime(2026, 4, 17, 12, 0, tzinfo=UTC),
        raw_payload={"port": 22},
        device_id="dev-uuid",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _site(vendor_site_id="vendor-site-xyz"):
    return SimpleNamespace(vendor_site_id=vendor_site_id)


@pytest.mark.asyncio
async def test_generate_summary_success():
    client = AsyncMock()
    client.summarize_event = AsyncMock(return_value="X")
    result = await generate_summary(
        client, _event(), _site(), True, "notify_critical", vendor_device_id="dev-1"
    )
    assert result == "X"


@pytest.mark.asyncio
async def test_generate_summary_graceful_degrade_on_api_error(caplog):
    client = AsyncMock()
    client.summarize_event = AsyncMock(
        side_effect=OpenAIAPIError("boom", status_code=500, url="u")
    )
    with caplog.at_level(logging.WARNING, logger="athena.worker.summarizer"):
        result = await generate_summary(
            client, _event(), _site(), True, "notify_critical"
        )
    assert result is None
    assert any(
        "openai summary failed" in r.getMessage() for r in caplog.records
    )


@pytest.mark.asyncio
async def test_generate_summary_graceful_degrade_on_rate_limit():
    client = AsyncMock()
    client.summarize_event = AsyncMock(
        side_effect=OpenAIRateLimitError("slow", status_code=429, url="u")
    )
    result = await generate_summary(
        client, _event(), _site(), True, "notify_critical"
    )
    assert result is None


@pytest.mark.asyncio
async def test_generate_summary_graceful_degrade_on_network_error():
    client = AsyncMock()
    client.summarize_event = AsyncMock(
        side_effect=OpenAIAPIError("net", status_code=None, url="u")
    )
    result = await generate_summary(
        client, _event(), _site(), True, "notify_critical"
    )
    assert result is None


@pytest.mark.asyncio
async def test_generate_summary_context_shape():
    captured = {}

    async def capture(ctx):
        captured.update(ctx)
        return "ok"

    client = AsyncMock()
    client.summarize_event = AsyncMock(side_effect=capture)

    await generate_summary(
        client,
        _event(),
        _site(),
        True,
        "notify_critical",
        vendor_device_id="dev-abc",
    )

    assert set(captured.keys()) == {
        "vendor",
        "event_type",
        "severity",
        "classification",
        "is_important_device",
        "occurred_at",
        "vendor_device_id",
        "vendor_site_id",
        "raw_payload",
    }
    assert captured["vendor"] == "domotz"
    assert captured["classification"] == "notify_critical"
    assert captured["is_important_device"] is True
    assert captured["vendor_device_id"] == "dev-abc"
    assert captured["vendor_site_id"] == "vendor-site-xyz"
    assert captured["raw_payload"] == {"port": 22}
