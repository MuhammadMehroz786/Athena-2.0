import pytest
from sqlalchemy import select

from athena.db.models import Site, Tenant
from scripts.seed_smoke import (
    SMOKE_SITE_ID,
    SMOKE_TENANT_ID,
    seed,
)


@pytest.mark.asyncio
async def test_seed_smoke_creates_tenant_and_site(session):
    tenant_id, site_id = await seed(session)
    assert tenant_id == SMOKE_TENANT_ID
    assert site_id == SMOKE_SITE_ID

    tenants = (await session.execute(select(Tenant))).scalars().all()
    sites = (await session.execute(select(Site))).scalars().all()
    assert [t.id for t in tenants] == [SMOKE_TENANT_ID]
    assert [s.id for s in sites] == [SMOKE_SITE_ID]
    assert sites[0].tenant_id == SMOKE_TENANT_ID


@pytest.mark.asyncio
async def test_seed_smoke_is_idempotent(session):
    t1, s1 = await seed(session)
    t2, s2 = await seed(session)
    assert (t1, s1) == (t2, s2)

    tenants = (await session.execute(select(Tenant))).scalars().all()
    sites = (await session.execute(select(Site))).scalars().all()
    assert len(tenants) == 1
    assert len(sites) == 1
