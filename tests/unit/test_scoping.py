import pytest
from datetime import datetime, UTC
from sqlalchemy import select
from athena.db.models import Tenant, Site, Device, Event
from athena.db.scoping import scoped


@pytest.mark.asyncio
async def test_scoped_filters_by_tenant_id(session):
    t1 = Tenant(name="A"); t2 = Tenant(name="B")
    session.add_all([t1, t2]); await session.flush()
    s1 = Site(tenant_id=t1.id, name="S1"); s2 = Site(tenant_id=t2.id, name="S2")
    session.add_all([s1, s2]); await session.flush()
    d1 = Device(tenant_id=t1.id, site_id=s1.id, vendor="unifi", vendor_device_id="x", name="n", kind="switch")
    d2 = Device(tenant_id=t2.id, site_id=s2.id, vendor="unifi", vendor_device_id="y", name="n", kind="switch")
    session.add_all([d1, d2]); await session.flush()
    session.add_all([
        Event(tenant_id=t1.id, site_id=s1.id, device_id=d1.id, vendor="unifi",
              event_type="e", severity="info", vendor_event_id="v1", raw_payload={},
              occurred_at=datetime.now(UTC)),
        Event(tenant_id=t2.id, site_id=s2.id, device_id=d2.id, vendor="unifi",
              event_type="e", severity="info", vendor_event_id="v2", raw_payload={},
              occurred_at=datetime.now(UTC)),
    ])
    await session.commit()

    q = scoped(select(Event), Event, tenant_id=t1.id)
    rows = (await session.execute(q)).scalars().all()
    assert len(rows) == 1
    assert rows[0].tenant_id == t1.id


def test_scoped_requires_tenant_id_empty_string():
    with pytest.raises(ValueError):
        scoped(select(Event), Event, tenant_id="")


def test_scoped_requires_tenant_id_none():
    with pytest.raises(ValueError):
        scoped(select(Event), Event, tenant_id=None)  # type: ignore[arg-type]


def test_scoped_rejects_model_without_tenant_id():
    with pytest.raises(ValueError):
        scoped(select(Tenant), Tenant, tenant_id="any")


def test_scoped_rejects_instance_instead_of_class():
    instance = Event(tenant_id="t1", site_id="s1", vendor="unifi",
                     event_type="e", severity="info", vendor_event_id="v",
                     raw_payload={}, occurred_at=datetime.now(UTC))
    with pytest.raises(ValueError):
        scoped(select(Event), instance, tenant_id="t1")
