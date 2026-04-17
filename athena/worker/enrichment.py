"""Device-importance enrichment via Domotz."""
from __future__ import annotations

from athena.integrations.domotz_client import (
    DomotzClient,
    DomotzNotFoundError,
)


async def resolve_device_importance(
    client: DomotzClient,
    vendor: str,
    vendor_site_id: str,
    vendor_device_id: str | None,
) -> bool:
    if vendor != "domotz":
        return False
    if vendor_device_id is None:
        return False
    try:
        device = await client.get_device(vendor_site_id, vendor_device_id)
    except DomotzNotFoundError:
        return False
    if not isinstance(device, dict):
        return False
    if device.get("is_important"):
        return True
    if device.get("important"):
        return True
    return False
