import copy
import json

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

SECRET = "test-domotz-secret"


class FakeArqPool:
    def __init__(self):
        self.jobs: list[tuple] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, args, kwargs))
        return None


def _domotz_payload(**overrides):
    base = {
        "event_id": "evt-abc-123",
        "event_type": "device.down",
        "event_timestamp": "2026-04-17T10:30:00Z",
        "agent": {"id": "agent-xyz", "name": "4925Appel"},
        "device": {
            "id": "device-123",
            "name": "USW-Flex-Mini.localdomain",
            "ip_address": "10.0.1.202",
            "mac_address": "F0:23:B9:E3:F6:E2",
            "type": "SWITCH",
            "make": "Ubiquiti Inc",
            "model": "USW-Flex-Mini",
        },
        "details": {"reason": "ping timeout"},
    }
    payload = copy.deepcopy(base)
    for k, v in overrides.items():
        if v is _REMOVE:
            payload.pop(k, None)
        else:
            payload[k] = v
    return payload


_REMOVE = object()


@pytest.fixture
def settings_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", "test-unifi-secret")
    monkeypatch.setenv("DOMOTZ_WEBHOOK_SECRET", SECRET)
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


async def _seed_tenant_and_site(session, site_id="agent-xyz", tenant_id=None):
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


def _headers(tenant_id: str, api_key: str = SECRET) -> dict:
    return {
        "X-Athena-Tenant-Id": tenant_id,
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_domotz_webhook_happy_path(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    tenant_id, site_id = await _seed_tenant_and_site(session, site_id="agent-xyz")

    payload = _domotz_payload()
    resp = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers=_headers(tenant_id),
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
    assert rows[0].vendor == "domotz"
    assert rows[0].vendor_event_id == "evt-abc-123"
    assert rows[0].event_type == "device.down"
    assert rows[0].severity == "critical"

    assert arq.jobs == [("detect_event", (event_id,), {})]
    assert await redis.exists(f"wh:seen:{tenant_id}:domotz:evt-abc-123")


@pytest.mark.asyncio
async def test_domotz_webhook_bad_api_key(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="agent-xyz")

    payload = _domotz_payload()
    resp = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers=_headers(tenant_id, api_key="not-the-right-secret"),
    )
    assert resp.status_code == 401

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert rows == []
    assert arq.jobs == []


@pytest.mark.asyncio
async def test_domotz_webhook_missing_api_key(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="agent-xyz")

    payload = _domotz_payload()
    resp = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers={
            "X-Athena-Tenant-Id": tenant_id,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code in (401, 422)

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert rows == []
    assert arq.jobs == []


@pytest.mark.asyncio
async def test_domotz_webhook_duplicate_returns_200_via_redis(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="agent-xyz")

    payload = _domotz_payload()
    await mark_seen(
        redis,
        tenant_id=tenant_id,
        vendor="domotz",
        vendor_event_id=payload["event_id"],
    )

    resp = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers=_headers(tenant_id),
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
async def test_domotz_webhook_duplicate_returns_200_via_integrity_error(
    session, app_and_deps, client, monkeypatch
):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="agent-xyz")

    payload = _domotz_payload()
    resp1 = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers=_headers(tenant_id),
    )
    assert resp1.status_code == 202, resp1.text

    async def _always_unseen(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "athena.api.routes.webhooks.already_seen", _always_unseen
    )

    resp2 = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers=_headers(tenant_id),
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
async def test_domotz_webhook_unknown_agent_returns_404(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    t = Tenant(name="Acme")
    session.add(t)
    await session.commit()
    tenant_id = t.id

    payload = _domotz_payload()
    resp = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers=_headers(tenant_id),
    )
    assert resp.status_code == 404

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert rows == []
    assert arq.jobs == []


@pytest.mark.asyncio
async def test_domotz_webhook_cross_tenant_isolation(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps

    tenant_a = Tenant(name="TenantA")
    tenant_b = Tenant(name="TenantB")
    session.add_all([tenant_a, tenant_b])
    await session.flush()
    site_a = Site(id="agent-xyz", tenant_id=tenant_a.id, name="A-HQ")
    site_b = Site(id="agent-xyz-b", tenant_id=tenant_b.id, name="B-HQ")
    session.add_all([site_a, site_b])
    await session.commit()

    payload_a = _domotz_payload()
    payload_b = _domotz_payload()
    payload_b["agent"]["id"] = "agent-xyz-b"

    resp_a = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload_a),
        headers=_headers(tenant_a.id),
    )
    assert resp_a.status_code == 202, resp_a.text

    resp_b = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload_b),
        headers=_headers(tenant_b.id),
    )
    assert resp_b.status_code == 202, resp_b.text
    assert resp_b.json()["status"] == "accepted"

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert len(rows) == 2
    tenants_seen = {r.tenant_id for r in rows}
    assert tenants_seen == {tenant_a.id, tenant_b.id}
    assert len(arq.jobs) == 2


@pytest.mark.asyncio
async def test_domotz_webhook_invalid_payload_returns_400(session, app_and_deps, client):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="agent-xyz")

    payload = _domotz_payload()
    del payload["event_id"]

    resp = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers=_headers(tenant_id),
    )
    assert resp.status_code == 400
    assert "event_id" in resp.json()["detail"]

    async with Factory() as s:
        rows = (await s.execute(select(Event))).scalars().all()
    assert rows == []
    assert arq.jobs == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type,expected_severity",
    [
        ("device.down", "critical"),
        ("device.up", "info"),
        ("heartbeat.lost", "critical"),
        ("configuration.change", "warn"),
        ("ip.change", "info"),
    ],
)
async def test_domotz_webhook_severity_mapping(
    session, app_and_deps, client, event_type, expected_severity
):
    app, redis, arq, Factory = app_and_deps
    tenant_id, _ = await _seed_tenant_and_site(session, site_id="agent-xyz")

    payload = _domotz_payload(event_type=event_type, event_id=f"evt-{event_type}")

    resp = await client.post(
        "/webhooks/domotz",
        content=json.dumps(payload),
        headers=_headers(tenant_id),
    )
    assert resp.status_code == 202, resp.text

    async with Factory() as s:
        row = (
            await s.execute(
                select(Event).where(Event.vendor_event_id == payload["event_id"])
            )
        ).scalar_one()
    assert row.severity == expected_severity
    assert row.event_type == event_type
