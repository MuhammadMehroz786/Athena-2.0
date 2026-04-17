import base64
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from athena.api.deps import get_db_session
from athena.db.models import Event
from athena.db.scoping import scoped

router = APIRouter(prefix="/events", tags=["events"])

MAX_LIMIT = 200


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    site_id: str
    device_id: Optional[str] = None
    vendor: str
    vendor_event_id: str
    event_type: str
    severity: str
    occurred_at: datetime
    received_at: datetime


class EventsPage(BaseModel):
    events: list[EventOut]
    next_cursor: Optional[str] = None


def _encode_cursor(received_at: datetime, event_id: str) -> str:
    raw = json.dumps({"received_at": received_at.isoformat(), "id": event_id}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return datetime.fromisoformat(data["received_at"]), data["id"]
    except Exception:
        raise HTTPException(status_code=400, detail="invalid cursor")


@router.get("", response_model=EventsPage)
async def list_events(
    x_athena_tenant_id: str = Header(...),
    site_id: Optional[str] = Query(None),
    vendor: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1),
    cursor: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
):
    effective_limit = min(limit, MAX_LIMIT)

    stmt = scoped(select(Event), Event, tenant_id=x_athena_tenant_id)

    if site_id is not None:
        stmt = stmt.where(Event.site_id == site_id)
    if vendor is not None:
        stmt = stmt.where(Event.vendor == vendor)
    if severity is not None:
        stmt = stmt.where(Event.severity == severity)
    if event_type is not None:
        stmt = stmt.where(Event.event_type == event_type)

    if cursor is not None:
        cur_received_at, cur_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Event.received_at < cur_received_at,
                and_(Event.received_at == cur_received_at, Event.id < cur_id),
            )
        )

    stmt = stmt.order_by(Event.received_at.desc(), Event.id.desc()).limit(effective_limit)

    rows = (await db.execute(stmt)).scalars().all()

    next_cursor = None
    if len(rows) == effective_limit and len(rows) > 0:
        last = rows[-1]
        next_cursor = _encode_cursor(last.received_at, last.id)

    return EventsPage(
        events=[EventOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
