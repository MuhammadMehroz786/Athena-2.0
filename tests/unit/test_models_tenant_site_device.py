import pytest
from sqlalchemy import select
from athena.db.models import Tenant, Site, Device


@pytest.mark.asyncio
async def test_create_tenant_site_device(session):
    t = Tenant(name="Acme")
    session.add(t)
    await session.flush()

    s = Site(tenant_id=t.id, name="HQ")
    session.add(s)
    await session.flush()

    d = Device(
        tenant_id=t.id,
        site_id=s.id,
        vendor="unifi",
        vendor_device_id="aa:bb:cc:dd:ee:ff",
        name="Core Switch",
        kind="switch",
    )
    session.add(d)
    await session.commit()

    got = (await session.execute(select(Device))).scalar_one()
    assert got.name == "Core Switch"
    assert got.tenant_id == t.id
