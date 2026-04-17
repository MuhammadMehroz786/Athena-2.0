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


async def _make_tenant_site(session):
    t = Tenant(name="Acme")
    session.add(t)
    await session.flush()
    s = Site(tenant_id=t.id, name="HQ")
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
    result = await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

    assert result == {"event_id": e.id, "classification": "notify_critical"}
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
    result = await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

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
    result = await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

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
    result = await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

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
    result = await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

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
    result = await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

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
    result = await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

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
        await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

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
        result = await jobs.detect_event({"domotz_client": mock_client}, event_id=e.id)

    assert result == {"event_id": e.id, "classification": "notify_warn"}
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
            {"domotz_client": mock_client},
            event_id="00000000-0000-0000-0000-000000000000",
        )
