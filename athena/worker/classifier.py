"""Minimal severity x importance classifier."""
from __future__ import annotations

VALID_CLASSIFICATIONS = frozenset({"notify_critical", "notify_warn", "log_only"})


def classify(severity: str, is_important_device: bool) -> str:
    if severity == "critical" and is_important_device:
        return "notify_critical"
    if severity == "critical" and not is_important_device:
        return "notify_warn"
    if severity == "warn":
        return "notify_warn"
    return "log_only"
