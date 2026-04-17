# TODO: validate against real Domotz payload; current schema inferred from event catalog only.
from datetime import datetime
from typing import Any

from athena.webhooks.unifi import NormalizedEvent


class DomotzNormalizeError(ValueError):
    pass


def _severity_for(event_type: str) -> str:
    tokens = event_type.lower().split(".")
    if "down" in tokens or "lost" in tokens:
        return "critical"
    if "configuration" in tokens:
        return "warn"
    return "info"


def normalize_domotz_payload(raw: dict[str, Any]) -> NormalizedEvent:
    if not isinstance(raw, dict):
        raise DomotzNormalizeError("payload must be a JSON object")

    for key in ("event_id", "event_type", "event_timestamp"):
        if key not in raw or raw[key] in (None, ""):
            raise DomotzNormalizeError(f"missing required field: {key}")

    agent = raw.get("agent")
    if not isinstance(agent, dict) or not agent.get("id"):
        raise DomotzNormalizeError("missing required field: agent.id")

    try:
        occurred = datetime.fromisoformat(str(raw["event_timestamp"]).replace("Z", "+00:00"))
    except Exception as e:
        raise DomotzNormalizeError(f"bad event_timestamp: {e}") from e

    device = raw.get("device") if isinstance(raw.get("device"), dict) else {}
    vendor_device_id = str(device["id"]) if device.get("id") is not None else None

    event_type = str(raw["event_type"])
    severity = _severity_for(event_type)

    return NormalizedEvent(
        vendor="domotz",
        vendor_event_id=str(raw["event_id"]),
        vendor_site_id=str(agent["id"]),
        vendor_device_id=vendor_device_id,
        event_type=event_type,
        severity=severity,
        occurred_at=occurred,
        raw_payload=raw,
    )
