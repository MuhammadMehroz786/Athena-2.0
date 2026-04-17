import pytest
import fakeredis.aioredis
from athena.webhooks.dedupe import already_seen, mark_seen


@pytest.mark.asyncio
async def test_first_time_not_seen_then_seen():
    r = fakeredis.aioredis.FakeRedis()
    seen = await already_seen(r, tenant_id="t1", vendor="unifi", vendor_event_id="evt-1")
    assert seen is False
    await mark_seen(r, tenant_id="t1", vendor="unifi", vendor_event_id="evt-1")
    assert await already_seen(r, tenant_id="t1", vendor="unifi", vendor_event_id="evt-1") is True


@pytest.mark.asyncio
async def test_different_vendors_dont_collide():
    r = fakeredis.aioredis.FakeRedis()
    await mark_seen(r, tenant_id="t1", vendor="unifi", vendor_event_id="evt-1")
    assert await already_seen(r, tenant_id="t1", vendor="meraki", vendor_event_id="evt-1") is False


@pytest.mark.asyncio
async def test_different_tenants_dont_collide():
    r = fakeredis.aioredis.FakeRedis()
    await mark_seen(r, tenant_id="t1", vendor="unifi", vendor_event_id="evt-1")
    assert await already_seen(r, tenant_id="t2", vendor="unifi", vendor_event_id="evt-1") is False


@pytest.mark.asyncio
async def test_mark_seen_sets_ttl():
    r = fakeredis.aioredis.FakeRedis()
    await mark_seen(r, tenant_id="t1", vendor="unifi", vendor_event_id="evt-1")
    ttl = await r.ttl("wh:seen:t1:unifi:evt-1")
    assert 86000 < ttl <= 86400
