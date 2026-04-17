import logging
from datetime import datetime, UTC
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from athena.db.models import Device, Event, Site, Tenant
from athena.integrations.domotz_client import (
    DomotzNotFoundError,
    DomotzRateLimitError,
)
from athena.integrations.openai_client import OpenAIAPIError
from athena.worker import jobs


@pytest.fixture
def patch_sessionmaker(session, monkeypatch):
    bind = session.bind
    Factory = async_sessionmaker(
        bind=bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(jobs, "get_sessionmaker", lambda: Factory)
    return Factory


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", "s")
    monkeypatch.setenv("DOMOTZ_WEBHOOK_SECRET", "s")
    monkeypatch.setenv("DOMOTZ_API_BASE_URL", "https://x/public-api/v1")
    monkeypatch.setenv("DOMOTZ_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_ENABLED", "true")


def _mk_openai_mock(content: str | None = "summary-text"):
    m = AsyncMock()
    m.summarize_event = AsyncMock(return_value=content)
    return m


def _ctx(domotz_client=None, openai_client=None):
    return {
        "domotz_client": domotz_client if domotz_client is not None else AsyncMock(),
        "openai_client": openai_client if openai_client is not None else _mk_openai_mock(),
    }


async def _make_tenant_site(session, vendor_site_id="vendor-site-xyz"):
    t = Tenant(name="Acme")
    session.add(t)
    await session.flush()
    s = Site(tenant_id=t.id, name="HQ", vendor_site_id=vendor_site_id)
    session.add(s)
    await session.flush()
    return t, s


async def _make_device(session, tenant_id, site_id, vendor, vendor_device_id):
    d = Device(
        tenant_id=tenant_id,
        site_id=site_id,
        vendor=vendor,
        vendor_device_id=vendor_device_id,
        name="router-1",
        kind="router",
    )
    session.add(d)
    await session.flush()
    return d


@pytest.mark.asyncio
async def test_detect_event_critical_important_classifies_notify_critical(
    session, patch_sessionmaker
):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-1")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-1", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(return_value={"is_important": True})
    result = await jobs.detect_event(
        _ctx(domotz_client=mock_client), event_id=e.id
    )

    assert result["event_id"] == e.id
    assert result["classification"] == "notify_critical"
    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.classification == "notify_critical"
    mock_client.get_device.assert_called_once()


@pytest.mark.asyncio
async def test_detect_event_critical_not_important_classifies_notify_warn(
    session, patch_sessionmaker
):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-2")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-2", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(return_value={"is_important": False})
    result = await jobs.detect_event(
        _ctx(domotz_client=mock_client), event_id=e.id
    )

    assert result["classification"] == "notify_warn"
    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.classification == "notify_warn"


@pytest.mark.asyncio
async def test_detect_event_warn_classifies_notify_warn(session, patch_sessionmaker):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-3")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.configuration_change", severity="warn",
        vendor_event_id="vendor-evt-3", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(return_value={"is_important": True})
    result = await jobs.detect_event(
        _ctx(domotz_client=mock_client), event_id=e.id
    )

    assert result["classification"] == "notify_warn"
    assert mock_client.get_device.call_count == 0


@pytest.mark.asyncio
async def test_detect_event_info_classifies_log_only(session, patch_sessionmaker):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-4")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.noise", severity="info",
        vendor_event_id="vendor-evt-4", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(return_value={"is_important": True})
    result = await jobs.detect_event(
        _ctx(domotz_client=mock_client), event_id=e.id
    )

    assert result["classification"] == "log_only"
    assert mock_client.get_device.call_count == 0


@pytest.mark.asyncio
async def test_detect_event_unifi_event_skips_enrichment(session, patch_sessionmaker):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "unifi", "aa:bb:cc:dd:ee:ff")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="unifi",
        event_type="switch.port.poe_lost", severity="critical",
        vendor_event_id="vendor-evt-5", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(return_value={"is_important": True})
    result = await jobs.detect_event(
        _ctx(domotz_client=mock_client), event_id=e.id
    )

    assert result["classification"] == "notify_warn"
    assert mock_client.get_device.call_count == 0


@pytest.mark.asyncio
async def test_detect_event_missing_vendor_device_id_treats_as_not_important(
    session, patch_sessionmaker
):
    t, s = await _make_tenant_site(session)
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=None, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-6", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(return_value={"is_important": True})
    result = await jobs.detect_event(
        _ctx(domotz_client=mock_client), event_id=e.id
    )

    assert result["classification"] == "notify_warn"
    assert mock_client.get_device.call_count == 0


@pytest.mark.asyncio
async def test_detect_event_domotz_not_found_treats_as_not_important(
    session, patch_sessionmaker
):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-7")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-7", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(
        side_effect=DomotzNotFoundError("missing", status_code=404, url="x")
    )
    result = await jobs.detect_event(
        _ctx(domotz_client=mock_client), event_id=e.id
    )

    assert result["classification"] == "notify_warn"
    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.classification == "notify_warn"


@pytest.mark.asyncio
async def test_detect_event_domotz_rate_limit_propagates(session, patch_sessionmaker):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-8")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-8", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(
        side_effect=DomotzRateLimitError("slow", status_code=429, url="x")
    )
    with pytest.raises(DomotzRateLimitError):
        await jobs.detect_event(
            _ctx(domotz_client=mock_client), event_id=e.id
        )

    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.classification is None


@pytest.mark.asyncio
async def test_detect_event_returns_payload_and_logs(session, patch_sessionmaker, caplog):
    t, s = await _make_tenant_site(session)
    e = Event(
        tenant_id=t.id, site_id=s.id, vendor="unifi",
        event_type="switch.port.poe_lost", severity="warn",
        vendor_event_id="vendor-evt-log", raw_payload={"port": 22},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    with caplog.at_level(logging.INFO, logger="athena.worker.jobs"):
        result = await jobs.detect_event(
            _ctx(domotz_client=mock_client), event_id=e.id
        )

    assert result["event_id"] == e.id
    assert result["classification"] == "notify_warn"
    info_records = [
        r for r in caplog.records
        if r.name == "athena.worker.jobs" and r.levelno == logging.INFO
    ]
    assert info_records, "expected at least one INFO log from detect_event"
    assert any(e.id in r.getMessage() for r in info_records)


@pytest.mark.asyncio
async def test_detect_event_raises_for_missing_id(patch_sessionmaker):
    mock_client = AsyncMock()
    with pytest.raises(ValueError):
        await jobs.detect_event(
            _ctx(domotz_client=mock_client),
            event_id="00000000-0000-0000-0000-000000000000",
        )


@pytest.mark.asyncio
async def test_detect_event_site_without_vendor_site_id_skips_enrichment(
    session, patch_sessionmaker
):
    t, s = await _make_tenant_site(session, vendor_site_id=None)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-no-vsid")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-no-vsid", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_client = AsyncMock()
    mock_client.get_device = AsyncMock(return_value={"is_important": True})
    result = await jobs.detect_event(
        _ctx(domotz_client=mock_client), event_id=e.id
    )

    assert result["classification"] == "notify_warn"
    assert mock_client.get_device.call_count == 0


@pytest.mark.asyncio
async def test_detect_event_persists_summary(session, patch_sessionmaker):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-sum-1")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-sum-1", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_domotz = AsyncMock()
    mock_domotz.get_device = AsyncMock(return_value={"is_important": True})
    mock_openai = _mk_openai_mock("Device offline")

    result = await jobs.detect_event(
        _ctx(domotz_client=mock_domotz, openai_client=mock_openai),
        event_id=e.id,
    )

    assert result["summary"] == "Device offline"
    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.summary == "Device offline"


@pytest.mark.asyncio
async def test_detect_event_summary_none_when_disabled(
    session, patch_sessionmaker, monkeypatch
):
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-sum-2")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-sum-2", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_domotz = AsyncMock()
    mock_domotz.get_device = AsyncMock(return_value={"is_important": True})
    mock_openai = _mk_openai_mock("should-not-run")

    result = await jobs.detect_event(
        {"domotz_client": mock_domotz, "openai_client": mock_openai},
        event_id=e.id,
    )

    assert result["classification"] == "notify_critical"
    assert result["summary"] is None
    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.classification == "notify_critical"
    assert refreshed.summary is None
    mock_openai.summarize_event.assert_not_called()


@pytest.mark.asyncio
async def test_detect_event_continues_when_openai_fails(
    session, patch_sessionmaker
):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-sum-3")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-sum-3", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_domotz = AsyncMock()
    mock_domotz.get_device = AsyncMock(return_value={"is_important": True})
    mock_openai = AsyncMock()
    mock_openai.summarize_event = AsyncMock(
        side_effect=OpenAIAPIError("boom", status_code=500, url="u")
    )

    result = await jobs.detect_event(
        _ctx(domotz_client=mock_domotz, openai_client=mock_openai),
        event_id=e.id,
    )

    assert result["classification"] == "notify_critical"
    assert result["summary"] is None
    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.classification == "notify_critical"
    assert refreshed.summary is None


@pytest.mark.asyncio
async def test_detect_event_truncates_oversized_summary(
    session, patch_sessionmaker
):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-sum-trunc")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-sum-trunc", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    oversized = "A" * 600
    mock_domotz = AsyncMock()
    mock_domotz.get_device = AsyncMock(return_value={"is_important": True})
    mock_openai = _mk_openai_mock(oversized)

    result = await jobs.detect_event(
        _ctx(domotz_client=mock_domotz, openai_client=mock_openai),
        event_id=e.id,
    )

    assert result["summary"] == oversized[:512]
    assert len(result["summary"]) == 512
    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.summary == oversized[:512]
    assert len(refreshed.summary) == 512


@pytest.mark.asyncio
async def test_detect_event_summary_never_overrides_classification(
    session, patch_sessionmaker
):
    t, s = await _make_tenant_site(session)
    d = await _make_device(session, t.id, s.id, "domotz", "dev-sum-4")
    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="domotz",
        event_type="device.down", severity="critical",
        vendor_event_id="vendor-evt-sum-4", raw_payload={},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    mock_domotz = AsyncMock()
    mock_domotz.get_device = AsyncMock(return_value={"is_important": True})
    mock_openai = _mk_openai_mock("DOWNGRADE")

    result = await jobs.detect_event(
        _ctx(domotz_client=mock_domotz, openai_client=mock_openai),
        event_id=e.id,
    )

    assert result["classification"] == "notify_critical"
    assert result["summary"] == "DOWNGRADE"
    refreshed = await session.get(Event, e.id)
    await session.refresh(refreshed)
    assert refreshed.classification == "notify_critical"
    assert refreshed.summary == "DOWNGRADE"
