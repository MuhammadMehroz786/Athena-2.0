from dataclasses import dataclass
from datetime import datetime
from typing import Any


class UnifiNormalizeError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedEvent:
    vendor: str
    vendor_event_id: str
    vendor_site_id: str
    vendor_device_id: str | None
    event_type: str
    severity: str
    occurred_at: datetime
    raw_payload: dict[str, Any]


_SEVERITY_MAP = {
    "info": "info",
    "notice": "info",
    "warning": "warn",
    "warn": "warn",
    "error": "error",
    "critical": "critical",
    "alert": "critical",
}


def normalize_unifi_payload(payload: dict[str, Any]) -> NormalizedEvent:
    required = ("event_id", "timestamp", "type", "site_id")
    missing = [k for k in required if k not in payload]
    if missing:
        raise UnifiNormalizeError(f"missing required fields: {missing}")
    try:
        occurred = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    except Exception as e:
        raise UnifiNormalizeError(f"bad timestamp: {e}") from e

    severity = _SEVERITY_MAP.get(str(payload.get("severity", "info")).lower(), "info")

    return NormalizedEvent(
        vendor="unifi",
        vendor_event_id=str(payload["event_id"]),
        vendor_site_id=str(payload["site_id"]),
        vendor_device_id=(str(payload["device_mac"]) if payload.get("device_mac") is not None else None),
        event_type=str(payload["type"]),
        severity=severity,
        occurred_at=occurred,
        raw_payload=payload,
    )
