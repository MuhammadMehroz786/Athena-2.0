"""Idempotent seed for the local smoke-test recipe.

Creates one Tenant + one Site with fixed ids matching tests/fixtures/unifi/link_down.json
(site_id="site-abc"). Safe to run repeatedly; re-runs are no-ops.

Usage:
    python scripts/seed_smoke.py

Env:
    DATABASE_URL must be set (see .env.example). Reads via athena.config.get_settings().
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from athena.db.engine import get_sessionmaker
from athena.db.models import Site, Tenant

SMOKE_TENANT_ID = "tenant-smoke-01"
SMOKE_TENANT_NAME = "Smoke Test Tenant"
SMOKE_SITE_ID = "site-abc"  # matches tests/fixtures/unifi/link_down.json
SMOKE_SITE_NAME = "Smoke Test Site"


async def seed(session: AsyncSession) -> tuple[str, str]:
    """Insert the smoke Tenant + Site if they don't already exist.

    Returns (tenant_id, site_id). Commits the session.
    """
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == SMOKE_TENANT_ID))
    ).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(id=SMOKE_TENANT_ID, name=SMOKE_TENANT_NAME)
        session.add(tenant)
        await session.flush()

    site = (
        await session.execute(select(Site).where(Site.id == SMOKE_SITE_ID))
    ).scalar_one_or_none()
    if site is None:
        site = Site(id=SMOKE_SITE_ID, tenant_id=tenant.id, name=SMOKE_SITE_NAME)
        session.add(site)

    await session.commit()
    return tenant.id, site.id


async def _main() -> None:
    Session = get_sessionmaker()
    async with Session() as s:
        tenant_id, site_id = await seed(s)
    print(f"seeded tenant={tenant_id} site={site_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
