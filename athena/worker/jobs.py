import logging

from athena.config import get_settings
from athena.db.engine import get_sessionmaker
from athena.db.models import Device, Event
from athena.integrations.domotz_client import DomotzClient
from athena.worker.classifier import classify
from athena.worker.enrichment import resolve_device_importance

logger = logging.getLogger(__name__)


def _default_domotz_client() -> DomotzClient:
    s = get_settings()
    return DomotzClient(base_url=s.domotz_api_base_url, api_key=s.domotz_api_key)


async def detect_event(ctx, event_id: str) -> dict:
    client = ctx.get("domotz_client") if isinstance(ctx, dict) else None
    owns_client = client is None
    if owns_client:
        client = _default_domotz_client()
    try:
        Session = get_sessionmaker()
        async with Session() as session:
            event = await session.get(Event, event_id)
            if event is None:
                raise ValueError(f"Event {event_id} not found")

            if event.severity == "critical":
                vendor_device_id: str | None = None
                if event.device_id is not None:
                    device = await session.get(Device, event.device_id)
                    if device is not None:
                        vendor_device_id = device.vendor_device_id
                is_important = await resolve_device_importance(
                    client,
                    event.vendor,
                    event.site_id,
                    vendor_device_id,
                )
            else:
                is_important = False
            classification = classify(event.severity, is_important)
            event.classification = classification
            await session.commit()
    finally:
        if owns_client:
            await client.aclose()

    logger.info("detect_event classified %s as %s", event_id, classification)
    return {"event_id": event_id, "classification": classification}
