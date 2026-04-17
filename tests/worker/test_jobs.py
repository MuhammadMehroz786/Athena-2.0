from datetime import datetime, UTC
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from athena.db.models import Tenant, Site, Event
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


@pytest.mark.asyncio
async def test_detect_event_returns_stub_payload(session, patch_sessionmaker):
    t = Tenant(name="Acme"); session.add(t); await session.flush()
    s = Site(tenant_id=t.id, name="HQ"); session.add(s); await session.flush()
    e = Event(
        tenant_id=t.id, site_id=s.id, vendor="unifi",
        event_type="switch.port.poe_lost", severity="warn",
        vendor_event_id="vendor-evt-1", raw_payload={"port": 22},
        occurred_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()

    result = await jobs.detect_event({}, event_id=e.id)
    assert result == {"event_id": e.id, "status": "detected_stub"}


@pytest.mark.asyncio
async def test_detect_event_raises_for_missing_id(patch_sessionmaker):
    with pytest.raises(ValueError):
        await jobs.detect_event({}, event_id="00000000-0000-0000-0000-000000000000")
