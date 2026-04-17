# Athena 2.0

Monitoring + remediation brain for UniFi/Meraki/Domotz.

## Dev setup
1. `cp .env.example .env`
2. `docker compose up -d postgres redis`
3. `pip install -e .[dev]`
4. `alembic upgrade head`
5. `pytest`
6. `uvicorn athena.main:app --reload`

## Local smoke test

End-to-end check that the full pipeline (FastAPI + Postgres + Redis + Arq worker)
is wired up locally.

### 1. Prerequisites
- Python 3.11+ (see `pyproject.toml`)
- Docker + Docker Compose
- `pip install -e .[dev]`

### 2. Start infrastructure
```bash
docker compose up -d postgres redis
```
Services defined in `docker-compose.yml`: `postgres` (5432) and `redis` (6379).

### 3. Env vars
Copy the template:
```bash
cp .env.example .env
```
Required vars (see `athena/config.py`):
```
DATABASE_URL=postgresql+asyncpg://athena:athena@localhost:5432/athena
REDIS_URL=redis://localhost:6379/0
UNIFI_WEBHOOK_SECRET=changeme-unifi
LOG_LEVEL=INFO
ENV=dev
```
Export to the current shell so the seed script, uvicorn, and arq all see them:
```bash
set -a; source .env; set +a
```

### 4. Run migrations
```bash
alembic upgrade head
```

### 5. Seed minimum data
The webhook route requires an existing `Tenant` + `Site`. Use the bundled
idempotent seed script — it creates tenant id `tenant-smoke-01` and site id
`site-abc` (the latter matches the UniFi fixture payload):
```bash
python scripts/seed_smoke.py
# -> seeded tenant=tenant-smoke-01 site=site-abc
```
Safe to re-run.

### 6. Boot the services
Two terminals (both need the env vars from step 3):
```bash
# Terminal 1: API
uvicorn athena.main:app --reload --port 8000
```
```bash
# Terminal 2: Worker
arq athena.worker.WorkerSettings
```

### 7. Sign and send a webhook
The API verifies `X-Signature` as a raw hex HMAC-SHA256 of the request body
(no `sha256=` prefix — see `athena/webhooks/signatures.py`).
```bash
BODY=$(cat tests/fixtures/unifi/link_down.json)
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$UNIFI_WEBHOOK_SECRET" -hex | awk '{print $2}')
curl -sS -X POST http://localhost:8000/webhooks/unifi \
  -H "X-Athena-Tenant-Id: tenant-smoke-01" \
  -H "X-Signature: $SIG" \
  -H "Content-Type: application/json" \
  --data-binary "$BODY"
```
Expected: `202` with body like
```json
{"status":"accepted","event_id":"<uuid>"}
```

### 8. Verify via GET /events
```bash
curl -sS http://localhost:8000/events \
  -H "X-Athena-Tenant-Id: tenant-smoke-01" | jq
```
Expected: the just-sent event appears in `events[0]`, with
`vendor_event_id == "unifi-evt-002"`, `site_id == "site-abc"`,
`event_type == "switch.port.link_down"`.

### 9. Troubleshooting
- **401 invalid signature** — `X-Signature` must be raw hex (no `sha256=` prefix)
  and `UNIFI_WEBHOOK_SECRET` must match what the API sees. If you change the
  secret, restart uvicorn.
- **404 unknown site** — the payload's `site_id` is not in the DB for this
  tenant. Re-run `python scripts/seed_smoke.py`, and confirm the
  `X-Athena-Tenant-Id` header is `tenant-smoke-01`.
- **200 `{"status": "duplicate"}`** — the same `vendor_event_id` is already in
  Redis (24h TTL) or the DB. Edit the fixture's `event_id` field or flush Redis
  (`docker compose exec redis redis-cli FLUSHDB`) and retry.
- **Worker not picking up jobs** — check `REDIS_URL` is reachable from the arq
  process (`docker compose ps redis`), and that both terminals exported the
  same env vars.
- **`asyncpg` connection refused** — Postgres still warming up; `docker compose
  ps` should show the `postgres` service `healthy` before running migrations.
