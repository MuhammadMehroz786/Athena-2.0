import base64
import json
from datetime import datetime, timedelta, UTC

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from athena.api import deps
from athena.api.app import create_app
from athena.db.models import Event, Site, Tenant


class FakeArqPool:
    def __init__(self):
        self.jobs: list[tuple] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, args, kwargs))
        return None


@pytest.fixture
def settings_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", "test-secret")
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


async def _seed_tenant_site(session, name="Acme", site_id="site-1"):
    t = Tenant(name=name)
    session.add(t)
    await session.flush()
    s = Site(id=site_id, tenant_id=t.id, name=name + "-HQ")
    session.add(s)
    await session.commit()
    return t.id, site_id


def _make_event(tenant_id, site_id, **kwargs):
    defaults = dict(
        tenant_id=tenant_id,
        site_id=site_id,
        vendor="unifi",
        vendor_event_id="vid-" + str(kwargs.get("n", 0)),
        event_type="link.down",
        severity="warning",
        raw_payload={"secret": "hidden"},
        occurred_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
    )
    n = kwargs.pop("n", None)
    defaults.update(kwargs)
    return Event(**defaults)


@pytest.mark.asyncio
async def test_events_returns_tenant_scoped_rows(session, app_and_deps, client):
    app, _, _, Factory = app_and_deps
    ta = Tenant(name="A")
    tb = Tenant(name="B")
    session.add_all([ta, tb])
    await session.flush()
    sa = Site(id="site-a", tenant_id=ta.id, name="A-HQ")
    sb = Site(id="site-b", tenant_id=tb.id, name="B-HQ")
    session.add_all([sa, sb])
    await session.flush()

    now = datetime.now(UTC)
    session.add(_make_event(ta.id, "site-a", vendor_event_id="a-1", occurred_at=now, received_at=now))
    session.add(_make_event(tb.id, "site-b", vendor_event_id="b-1", occurred_at=now, received_at=now))
    await session.commit()

    resp = await client.get("/events", headers={"X-Athena-Tenant-Id": ta.id})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["next_cursor"] is None
    assert len(data["events"]) == 1
    assert data["events"][0]["tenant_id"] == ta.id
    assert data["events"][0]["vendor_event_id"] == "a-1"
    assert "raw_payload" not in data["events"][0]


@pytest.mark.asyncio
async def test_events_filter_by_site(session, app_and_deps, client):
    app, _, _, Factory = app_and_deps
    t = Tenant(name="T")
    session.add(t)
    await session.flush()
    s1 = Site(id="s-1", tenant_id=t.id, name="one")
    s2 = Site(id="s-2", tenant_id=t.id, name="two")
    session.add_all([s1, s2])
    await session.flush()

    now = datetime.now(UTC)
    session.add(_make_event(t.id, "s-1", vendor_event_id="e1", occurred_at=now, received_at=now))
    session.add(_make_event(t.id, "s-2", vendor_event_id="e2", occurred_at=now, received_at=now))
    await session.commit()

    resp = await client.get(
        "/events",
        params={"site_id": "s-2"},
        headers={"X-Athena-Tenant-Id": t.id},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["site_id"] == "s-2"


@pytest.mark.asyncio
async def test_events_filter_by_vendor(session, app_and_deps, client):
    tenant_id, site_id = await _seed_tenant_site(session)

    now = datetime.now(UTC)
    async with app_and_deps[3]() as s:
        s.add(_make_event(tenant_id, site_id, vendor="unifi", vendor_event_id="u-1", occurred_at=now, received_at=now))
        s.add(_make_event(tenant_id, site_id, vendor="meraki", vendor_event_id="m-1", occurred_at=now, received_at=now))
        await s.commit()

    resp = await client.get(
        "/events",
        params={"vendor": "meraki"},
        headers={"X-Athena-Tenant-Id": tenant_id},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["vendor"] == "meraki"


@pytest.mark.asyncio
async def test_events_filter_by_severity(session, app_and_deps, client):
    tenant_id, site_id = await _seed_tenant_site(session)

    now = datetime.now(UTC)
    async with app_and_deps[3]() as s:
        s.add(_make_event(tenant_id, site_id, severity="info", vendor_event_id="i-1", occurred_at=now, received_at=now))
        s.add(_make_event(tenant_id, site_id, severity="critical", vendor_event_id="c-1", occurred_at=now, received_at=now))
        await s.commit()

    resp = await client.get(
        "/events",
        params={"severity": "critical"},
        headers={"X-Athena-Tenant-Id": tenant_id},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_events_pagination_keyset(session, app_and_deps, client):
    tenant_id, site_id = await _seed_tenant_site(session)

    base = datetime.now(UTC)
    async with app_and_deps[3]() as s:
        for i in range(5):
            ts = base + timedelta(seconds=i)
            s.add(_make_event(
                tenant_id, site_id,
                vendor_event_id=f"v-{i}",
                occurred_at=ts, received_at=ts,
            ))
        await s.commit()

    resp1 = await client.get(
        "/events",
        params={"limit": 2},
        headers={"X-Athena-Tenant-Id": tenant_id},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert len(data1["events"]) == 2
    assert data1["next_cursor"] is not None

    resp2 = await client.get(
        "/events",
        params={"limit": 2, "cursor": data1["next_cursor"]},
        headers={"X-Athena-Tenant-Id": tenant_id},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["events"]) == 2
    assert data2["next_cursor"] is not None

    resp3 = await client.get(
        "/events",
        params={"limit": 2, "cursor": data2["next_cursor"]},
        headers={"X-Athena-Tenant-Id": tenant_id},
    )
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert len(data3["events"]) == 1
    assert data3["next_cursor"] is None

    all_ids = [e["id"] for e in data1["events"] + data2["events"] + data3["events"]]
    assert len(set(all_ids)) == 5


@pytest.mark.asyncio
async def test_events_limit_capped_at_200(session, app_and_deps, client, monkeypatch):
    tenant_id, site_id = await _seed_tenant_site(session)

    base = datetime.now(UTC)
    async with app_and_deps[3]() as s:
        for i in range(5):
            ts = base + timedelta(seconds=i)
            s.add(_make_event(
                tenant_id, site_id,
                vendor_event_id=f"cap-{i}",
                occurred_at=ts, received_at=ts,
            ))
        await s.commit()

    from athena.api.routes import events as events_mod
    assert events_mod.MAX_LIMIT == 200

    monkeypatch.setattr(events_mod, "MAX_LIMIT", 3)

    resp = await client.get(
        "/events",
        params={"limit": 999},
        headers={"X-Athena-Tenant-Id": tenant_id},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["events"]) == 3
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_events_empty_page_returns_empty_list_and_null_cursor(session, app_and_deps, client):
    tenant_id, _ = await _seed_tenant_site(session)

    resp = await client.get("/events", headers={"X-Athena-Tenant-Id": tenant_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"events": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_events_invalid_cursor_returns_400(session, app_and_deps, client):
    tenant_id, _ = await _seed_tenant_site(session)

    resp = await client.get(
        "/events",
        params={"cursor": "not-a-real-cursor!!!"},
        headers={"X-Athena-Tenant-Id": tenant_id},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid cursor"
