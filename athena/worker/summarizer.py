from __future__ import annotations

import logging

from athena.db.models import Device, Event, Site
from athena.integrations.openai_client import OpenAIAPIError, OpenAIClient

logger = logging.getLogger("athena.worker.summarizer")


async def generate_summary(
    client: OpenAIClient,
    event: Event,
    site: Site,
    is_important: bool,
    classification: str,
    vendor_device_id: str | None = None,
) -> str | None:
    context = {
        "vendor": event.vendor,
        "event_type": event.event_type,
        "severity": event.severity,
        "classification": classification,
        "is_important_device": is_important,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "vendor_device_id": vendor_device_id,
        "vendor_site_id": site.vendor_site_id if site is not None else None,
        "raw_payload": event.raw_payload,
    }
    try:
        return await client.summarize_event(context)
    except OpenAIAPIError as e:
        logger.warning(
            "openai summary failed: status=%s url=%s", e.status_code, e.url
        )
        return None
