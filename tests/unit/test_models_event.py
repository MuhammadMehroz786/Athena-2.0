from datetime import datetime, UTC
import pytest
from sqlalchemy import select
from athena.db.models import Tenant, Site, Device, Event


@pytest.mark.asyncio
async def test_event_append_and_query(session):
    t = Tenant(name="Acme"); session.add(t); await session.flush()
    s = Site(tenant_id=t.id, name="HQ"); session.add(s); await session.flush()
    d = Device(tenant_id=t.id, site_id=s.id, vendor="unifi",
               vendor_device_id="dev1", name="Sw", kind="switch")
    session.add(d); await session.flush()

    e = Event(
        tenant_id=t.id, site_id=s.id, device_id=d.id,
        vendor="unifi",
        event_type="switch.port.poe_lost",
        severity="warn",
        vendor_event_id="vendor-evt-1",
        raw_payload={"port": 22},
        occurred_at=datetime.now(UTC),
    )
    session.add(e); await session.commit()

    rows = (await session.execute(select(Event))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "switch.port.poe_lost"
    assert rows[0].raw_payload == {"port": 22}


@pytest.mark.asyncio
async def test_event_unique_by_tenant_vendor_event_id(session):
    t = Tenant(name="Acme"); session.add(t); await session.flush()
    s = Site(tenant_id=t.id, name="HQ"); session.add(s); await session.flush()
    d = Device(tenant_id=t.id, site_id=s.id, vendor="unifi",
               vendor_device_id="dev1", name="Sw", kind="switch")
    session.add(d); await session.flush()
    common = dict(tenant_id=t.id, site_id=s.id, device_id=d.id, vendor="unifi",
                  event_type="e", severity="info", raw_payload={}, occurred_at=datetime.now(UTC))
    session.add(Event(vendor_event_id="dup", **common))
    await session.commit()
    session.add(Event(vendor_event_id="dup", **common))
    with pytest.raises(Exception):
        await session.commit()


@pytest.mark.asyncio
async def test_event_same_vendor_event_id_allowed_across_tenants(session):
    t1 = Tenant(name="A"); t2 = Tenant(name="B")
    session.add_all([t1, t2]); await session.flush()
    s1 = Site(tenant_id=t1.id, name="S1"); s2 = Site(tenant_id=t2.id, name="S2")
    session.add_all([s1, s2]); await session.flush()

    now = datetime.now(UTC)
    session.add(Event(tenant_id=t1.id, site_id=s1.id, vendor="unifi",
                      event_type="e", severity="info", vendor_event_id="shared",
                      raw_payload={}, occurred_at=now))
    session.add(Event(tenant_id=t2.id, site_id=s2.id, vendor="unifi",
                      event_type="e", severity="info", vendor_event_id="shared",
                      raw_payload={}, occurred_at=now))
    # No exception: two tenants may legitimately see the same vendor_event_id
    await session.commit()
    assert len((await session.execute(select(Event))).scalars().all()) == 2
