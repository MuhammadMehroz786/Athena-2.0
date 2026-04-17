import logging

from athena.config import get_settings
from athena.db.engine import get_sessionmaker
from athena.db.models import Device, Event, Site
from athena.integrations.domotz_client import DomotzClient
from athena.integrations.openai_client import OpenAIClient
from athena.integrations.twilio_client import TwilioClient
from athena.worker.classifier import classify
from athena.worker.enrichment import resolve_device_importance
from athena.worker.notifier import NotifyConfig, dispatch_notifications
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


def _default_twilio_client() -> TwilioClient:
    s = get_settings()
    return TwilioClient(
        account_sid=s.twilio_account_sid,
        auth_token=s.twilio_auth_token,
        base_url=s.twilio_base_url,
        timeout=s.twilio_timeout_seconds,
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

    twilio_client = ctx.get("twilio_client") if isinstance(ctx, dict) else None
    owns_twilio = False
    if settings.twilio_enabled and twilio_client is None:
        twilio_client = _default_twilio_client()
        owns_twilio = True

    summary_value: str | None = None
    notify_outcomes: list[str] = []
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

            # Capture fields needed by dispatch_notifications before the
            # session closes, so notification dispatch can run outside the
            # session block. Doing so avoids re-sending SMS/call if session
            # close errors trigger an Arq retry after a successful commit.
            event_vendor = event.vendor
            event_type = event.event_type
            event_received_at = event.received_at
            event_summary = event.summary

        notify_config = NotifyConfig(
            enabled=settings.twilio_enabled,
            from_number=settings.twilio_from_number,
            to_number=settings.notify_contact_phone,
            twiml_url=None,
        )
        notify_outcomes = await dispatch_notifications(
            client=twilio_client,
            classification=classification,
            summary=event_summary,
            vendor=event_vendor,
            event_type=event_type,
            received_at=event_received_at,
            config=notify_config,
        )
    finally:
        if owns_domotz and domotz_client is not None:
            await domotz_client.aclose()
        if owns_openai and openai_client is not None:
            await openai_client.aclose()
        if owns_twilio and twilio_client is not None:
            await twilio_client.aclose()

    logger.info("detect_event classified %s as %s", event_id, classification)
    return {
        "event_id": event_id,
        "classification": classification,
        "summary": summary_value,
        "notifications": notify_outcomes,
    }
