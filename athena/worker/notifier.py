from __future__ import annotations

import logging
from dataclasses import dataclass

from athena.db.models import Event
from athena.integrations.twilio_client import TwilioAPIError, TwilioClient

logger = logging.getLogger("athena.worker.notifier")

_BODY_MAX = 1400


@dataclass
class NotifyConfig:
    enabled: bool
    from_number: str
    to_number: str
    twiml_url: str | None = None


def _build_body(classification: str, summary: str | None, event: Event) -> str:
    received_iso = event.received_at.isoformat() if event.received_at else ""
    summary_text = summary if summary else "(no summary)"
    body = (
        f"[{classification.upper()}] {event.vendor}/{event.event_type} "
        f"on {received_iso}: {summary_text}"
    )
    return body[:_BODY_MAX]


async def _try_sms(
    client: TwilioClient, config: NotifyConfig, body: str
) -> str:
    try:
        resp = await client.send_sms(config.from_number, config.to_number, body)
    except TwilioAPIError as e:
        logger.warning("twilio sms failed: status=%s url=%s", e.status_code, e.url)
        return f"sms:failed:{e.status_code}"
    sid = resp.get("sid") if isinstance(resp, dict) else None
    return f"sms:sent:{sid}"


async def _try_call(client: TwilioClient, config: NotifyConfig) -> str:
    kwargs: dict = {
        "from_number": config.from_number,
        "to_number": config.to_number,
    }
    if config.twiml_url:
        kwargs["twiml_url"] = config.twiml_url
    try:
        resp = await client.start_call(**kwargs)
    except TwilioAPIError as e:
        logger.warning("twilio call failed: status=%s url=%s", e.status_code, e.url)
        return f"call:failed:{e.status_code}"
    sid = resp.get("sid") if isinstance(resp, dict) else None
    return f"call:sent:{sid}"


async def dispatch_notifications(
    client: TwilioClient | None,
    classification: str,
    summary: str | None,
    event: Event,
    config: NotifyConfig,
) -> list[str]:
    if client is None or not config.enabled or not config.to_number:
        return []
    if classification not in ("notify_critical", "notify_warn"):
        return []

    body = _build_body(classification, summary, event)
    outcomes: list[str] = [await _try_sms(client, config, body)]
    if classification == "notify_critical":
        outcomes.append(await _try_call(client, config))
    return outcomes
