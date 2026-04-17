import logging

from athena.config import get_settings
from athena.db.engine import get_sessionmaker
from athena.db.models import Device, Event, Site
from athena.integrations.domotz_client import DomotzClient
from athena.integrations.openai_client import OpenAIClient
from athena.worker.classifier import classify
from athena.worker.enrichment import resolve_device_importance
from athena.worker.summarizer import generate_summary

logger = logging.getLogger(__name__)


def _default_domotz_client() -> DomotzClient:
    s = get_settings()
    return DomotzClient(base_url=s.domotz_api_base_url, api_key=s.domotz_api_key)


def _default_openai_client() -> OpenAIClient:
    s = get_settings()
    return OpenAIClient(
        base_url=s.openai_base_url,
        api_key=s.openai_api_key,
        model=s.openai_model,
        timeout=s.openai_timeout_seconds,
    )


async def detect_event(ctx, event_id: str) -> dict:
    settings = get_settings()

    domotz_client = ctx.get("domotz_client") if isinstance(ctx, dict) else None
    owns_domotz = False
    if domotz_client is None:
        domotz_client = _default_domotz_client()
        owns_domotz = True

    openai_client = ctx.get("openai_client") if isinstance(ctx, dict) else None
    owns_openai = False
    if settings.openai_enabled and openai_client is None:
        openai_client = _default_openai_client()
        owns_openai = True

    summary_value: str | None = None
    try:
        Session = get_sessionmaker()
        async with Session() as session:
            event = await session.get(Event, event_id)
            if event is None:
                raise ValueError(f"Event {event_id} not found")

            site = await session.get(Site, event.site_id)
            vendor_device_id: str | None = None
            if event.device_id is not None:
                device = await session.get(Device, event.device_id)
                if device is not None:
                    vendor_device_id = device.vendor_device_id

            if event.severity == "critical":
                vendor_site_id = site.vendor_site_id if site is not None else None
                if vendor_site_id is None:
                    is_important = False
                else:
                    is_important = await resolve_device_importance(
                        domotz_client,
                        event.vendor,
                        vendor_site_id,
                        vendor_device_id,
                    )
            else:
                is_important = False

            classification = classify(event.severity, is_important)
            event.classification = classification

            if settings.openai_enabled and openai_client is not None:
                summary = await generate_summary(
                    openai_client,
                    event,
                    site,
                    is_important,
                    classification,
                    vendor_device_id=vendor_device_id,
                )
                if summary is not None:
                    truncated = summary[:512]
                    event.summary = truncated
                    summary_value = truncated

            await session.commit()
    finally:
        if owns_domotz and domotz_client is not None:
            await domotz_client.aclose()
        if owns_openai and openai_client is not None:
            await openai_client.aclose()

    logger.info("detect_event classified %s as %s", event_id, classification)
    return {
        "event_id": event_id,
        "classification": classification,
        "summary": summary_value,
    }
