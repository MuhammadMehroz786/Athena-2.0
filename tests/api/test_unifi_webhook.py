import hashlib
import hmac
import json
from pathlib import Path

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from athena.api import deps
from athena.api.app import create_app
from athena.db.models import Event, Site, Tenant
from athena.webhooks.dedupe import mark_seen

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "unifi"
SECRET = "test-unifi-secret"


class FakeArqPool:
    def __init__(self):
        self.jobs: list[tuple] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, args, kwargs))
        return None


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.fixture
def settings_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("DOMOTZ_WEBHOOK_SECRET", "test-domotz-secret")
    monkeypatch.setenv("DOMOTZ_API_BASE_URL", "https://api.test.domotz.local/public-api/v1")
    monkeypatch.setenv("DOMOTZ_API_KEY", "test-domotz-api-key")
    from athena import config
    config.get_settings.cache_clear() if hasattr(config.get_settings, "cache_clear") else None


@pytest_asyncio.fixture
async def app_and_deps(session, settings_env):
    bind = session.bind
    Factory = async_sessionmaker(
        bind=bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    redis = fakeredis.aioredis.FakeRedis()
    arq = FakeArqPool()

    async def _get_db():
        async with Factory() as s:
            yield s

    async def _get_redis():
        yield redis

    async def _get_arq():
        return arq

    app = create_app()
    app.dependency_overrides[deps.get_db_session] = _get_db
    app.dependency_overrides[deps.get_redis] = _get_redis
    app.dependency_overrides[deps.get_arq_pool] = _get_arq
    return app, redis, arq, Factory


@pytest_asyncio.fixture
async def client(app_and_deps):
    app, _, _, _ = app_and_deps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _seed_tenant_and_site(session, site_id="site-abc", tenant_id=None):
    if tenant_id is None:
        t = Tenant(name="Acme")
        session.add(t)
        await session.flush()
        tenant_id = t.id
    else:
        t = Tenant(id=tenant_id, name=f"Tenant-{tenant_id}")
        session.add(t)
        await session.flush()
    s = Site(id=site_id, tenant_id=tenant_id, name="HQ")
    session.add(s)
    await session.commit()
    return tenant_id, site_id


@pytest.mark.asyncio
async def test_unifi_webhook_happy_path(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    tenant_id, site_id = await _seed_tenant_and_site(session, site_id="site-abc")

    body = (FIX / "link_down.json").read_bytes()
    sig = _sign(body)

    resp = await client.post(
        "/webhooks/unifi",
        content=body,
        headers={
            "X-Athena-Tenant-Id": tenant_id,
            "X-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["status"] == "accepted"
    event_id = data["event_id"]
    assert event_id

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == event_id
    assert rows[0].tenant_id == tenant_id
    assert rows[0].site_id == site_id
    assert rows[0].vendor == "unifi"
    assert rows[0].vendor_event_id == "unifi-evt-002"

    assert arq.jobs == [("detect_event", (event_id,), {})]
    assert await redis.exists(f"wh:seen:{tenant_id}:unifi:unifi-evt-002")


@pytest.mark.asyncio
async def test_unifi_webhook_bad_signature(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="site-abc")

    body = (FIX / "link_down.json").read_bytes()
    resp = await client.post(
        "/webhooks/unifi",
        content=body,
        headers={
            "X-Athena-Tenant-Id": tenant_id,
            "X-Signature": "deadbeef" * 8,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert rows == []
    assert arq.jobs == []


@pytest.mark.asyncio
async def test_unifi_webhook_duplicate_returns_200(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="site-abc")

    body = (FIX / "link_down.json").read_bytes()
    payload = json.loads(body)
    await mark_seen(
        redis,
        tenant_id=tenant_id,
        vendor="unifi",
        vendor_event_id=payload["event_id"],
    )

    sig = _sign(body)
    resp = await client.post(
        "/webhooks/unifi",
        content=body,
        headers={
            "X-Athena-Tenant-Id": tenant_id,
            "X-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "duplicate"
    assert data["vendor_event_id"] == payload["event_id"]

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert rows == []
    assert arq.jobs == []


@pytest.mark.asyncio
async def test_unifi_webhook_unknown_site(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    t = Tenant(name="Acme")
    session.add(t)
    await session.commit()
    tenant_id = t.id

    body = (FIX / "link_down.json").read_bytes()
    sig = _sign(body)

    resp = await client.post(
        "/webhooks/unifi",
        content=body,
        headers={
            "X-Athena-Tenant-Id": tenant_id,
            "X-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 404

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert rows == []
    assert arq.jobs == []


@pytest.mark.asyncio
async def test_unifi_webhook_integrity_error_returns_duplicate(
    session, app_and_deps, client, monkeypatch
):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="site-abc")

    body = (FIX / "link_down.json").read_bytes()
    payload = json.loads(body)
    sig = _sign(body)

    resp1 = await client.post(
        "/webhooks/unifi",
        content=body,
        headers={
            "X-Athena-Tenant-Id": tenant_id,
            "X-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp1.status_code == 202, resp1.text

    # Simulate concurrent race: bypass Redis dedupe so the request hits the DB
    # and trips the unique constraint.
    async def _always_unseen(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "athena.api.routes.webhooks.already_seen", _always_unseen
    )

    resp2 = await client.post(
        "/webhooks/unifi",
        content=body,
        headers={
            "X-Athena-Tenant-Id": tenant_id,
            "X-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp2.status_code == 200, resp2.text
    data = resp2.json()
    assert data["status"] == "duplicate"
    assert data["vendor_event_id"] == payload["event_id"]

    async with Factory() as s:
        rows = (
            await s.execute(
                select(Event).where(Event.vendor_event_id == payload["event_id"])
            )
        ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_unifi_webhook_cross_tenant_isolation(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps

    tenant_a = Tenant(name="TenantA")
    tenant_b = Tenant(name="TenantB")
    session.add_all([tenant_a, tenant_b])
    await session.flush()
    site_a = Site(id="site-abc", tenant_id=tenant_a.id, name="A-HQ")
    site_b = Site(id="site-abc-b", tenant_id=tenant_b.id, name="B-HQ")
    session.add_all([site_a, site_b])
    await session.commit()

    body_a = (FIX / "link_down.json").read_bytes()
    payload_b = json.loads(body_a)
    payload_b["site_id"] = "site-abc-b"
    body_b = json.dumps(payload_b).encode("utf-8")

    sig_a = _sign(body_a)
    sig_b = _sign(body_b)

    resp_a = await client.post(
        "/webhooks/unifi",
        content=body_a,
        headers={
            "X-Athena-Tenant-Id": tenant_a.id,
            "X-Signature": sig_a,
            "Content-Type": "application/json",
        },
    )
    assert resp_a.status_code == 202

    resp_b = await client.post(
        "/webhooks/unifi",
        content=body_b,
        headers={
            "X-Athena-Tenant-Id": tenant_b.id,
            "X-Signature": sig_b,
            "Content-Type": "application/json",
        },
    )
    assert resp_b.status_code == 202
    assert resp_b.json()["status"] == "accepted"

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert len(rows) == 2
    tenants_seen = {r.tenant_id for r in rows}
    assert tenants_seen == {tenant_a.id, tenant_b.id}
    assert len(arq.jobs) == 2
