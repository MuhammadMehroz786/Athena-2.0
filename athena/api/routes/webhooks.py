import hmac
import json
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from redis.asyncio import Redis
from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from athena.api.deps import get_arq_pool, get_db_session, get_redis
from athena.config import get_settings
from athena.db.models import Event, Site
from athena.db.scoping import scoped
from athena.webhooks.dedupe import already_seen, mark_seen
from athena.webhooks.domotz import DomotzNormalizeError, normalize_domotz_payload
from athena.webhooks.signatures import verify_hmac_sha256
from athena.webhooks.unifi import UnifiNormalizeError, normalize_unifi_payload

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/unifi", status_code=status.HTTP_202_ACCEPTED)
async def unifi_webhook(
    request: Request,
    response: Response,
    x_athena_tenant_id: str = Header(...),
    x_signature: str = Header(...),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    arq: ArqRedis = Depends(get_arq_pool),
):
    body = await request.body()
    secret = get_settings().unifi_webhook_secret
    if not verify_hmac_sha256(body, x_signature, secret):
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    try:
        normalized = normalize_unifi_payload(payload)
    except UnifiNormalizeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    vendor_event_id = normalized.vendor_event_id
    site_id = normalized.vendor_site_id

    if await already_seen(
        redis,
        tenant_id=x_athena_tenant_id,
        vendor=normalized.vendor,
        vendor_event_id=vendor_event_id,
    ):
        response.status_code = status.HTTP_200_OK
        return {"status": "duplicate", "vendor_event_id": vendor_event_id}

    stmt = scoped(select(Site), Site, tenant_id=x_athena_tenant_id).where(Site.id == site_id)
    site = (await db.execute(stmt)).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="unknown site")

    event = Event(
        tenant_id=x_athena_tenant_id,
        site_id=site.id,
        vendor=normalized.vendor,
        vendor_event_id=normalized.vendor_event_id,
        event_type=normalized.event_type,
        severity=normalized.severity,
        raw_payload=normalized.raw_payload,
        occurred_at=normalized.occurred_at,
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        response.status_code = status.HTTP_200_OK
        return {"status": "duplicate", "vendor_event_id": vendor_event_id}
    await db.refresh(event)

    # At-least-once: DB row is source of truth; failures here trigger producer retry,
    # and the unique constraint above makes retries idempotent.
    await mark_seen(
        redis,
        tenant_id=x_athena_tenant_id,
        vendor=normalized.vendor,
        vendor_event_id=vendor_event_id,
    )
    await arq.enqueue_job("detect_event", event.id)

    return {"status": "accepted", "event_id": event.id}


@router.post("/domotz", status_code=status.HTTP_202_ACCEPTED)
async def domotz_webhook(
    request: Request,
    response: Response,
    x_athena_tenant_id: str = Header(...),
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    arq: ArqRedis = Depends(get_arq_pool),
):
    secret = get_settings().domotz_webhook_secret
    if not hmac.compare_digest(x_api_key, secret):
        raise HTTPException(status_code=401, detail="invalid api key")

    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    try:
        normalized = normalize_domotz_payload(payload)
    except DomotzNormalizeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    vendor_event_id = normalized.vendor_event_id
    site_id = normalized.vendor_site_id

    if await already_seen(
        redis,
        tenant_id=x_athena_tenant_id,
        vendor=normalized.vendor,
        vendor_event_id=vendor_event_id,
    ):
        response.status_code = status.HTTP_200_OK
        return {"status": "duplicate", "vendor_event_id": vendor_event_id}

    stmt = scoped(select(Site), Site, tenant_id=x_athena_tenant_id).where(Site.id == site_id)
    site = (await db.execute(stmt)).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="unknown agent")

    event = Event(
        tenant_id=x_athena_tenant_id,
        site_id=site.id,
        vendor=normalized.vendor,
        vendor_event_id=normalized.vendor_event_id,
        event_type=normalized.event_type,
        severity=normalized.severity,
        raw_payload=normalized.raw_payload,
        occurred_at=normalized.occurred_at,
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        response.status_code = status.HTTP_200_OK
        return {"status": "duplicate", "vendor_event_id": vendor_event_id}
    await db.refresh(event)

    await mark_seen(
        redis,
        tenant_id=x_athena_tenant_id,
        vendor=normalized.vendor,
        vendor_event_id=vendor_event_id,
    )
    await arq.enqueue_job("detect_event", event.id)

    return {"status": "accepted", "event_id": event.id}
