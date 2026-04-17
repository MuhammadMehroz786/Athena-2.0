import json
from pathlib import Path
import pytest
from athena.webhooks.unifi import normalize_unifi_payload, UnifiNormalizeError

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "unifi"


def test_normalize_poe_lost():
    payload = json.loads((FIX / "poe_lost.json").read_text())
    out = normalize_unifi_payload(payload)
    assert out.vendor == "unifi"
    assert out.vendor_event_id == "unifi-evt-001"
    assert out.event_type == "switch.port.poe_lost"
    assert out.severity == "warn"
    assert out.vendor_site_id == "site-abc"
    assert out.vendor_device_id == "aa:bb:cc:dd:ee:01"
    assert out.raw_payload["data"]["port"] == 22
    assert out.occurred_at.isoformat().startswith("2026-04-17T12:00:00")


def test_normalize_link_downshift():
    payload = json.loads((FIX / "link_downshift_100mbps.json").read_text())
    out = normalize_unifi_payload(payload)
    assert out.event_type == "switch.port.link_speed_changed"
    assert out.raw_payload["data"]["speed_mbps"] == 100


def test_normalize_rejects_missing_event_id():
    with pytest.raises(UnifiNormalizeError):
        normalize_unifi_payload({"timestamp": "2026-04-17T12:00:00Z", "type": "x", "site_id": "s"})


def test_normalize_maps_severity():
    base = {"event_id": "e", "timestamp": "2026-04-17T12:00:00Z", "site_id": "s",
            "device_mac": "m", "type": "t", "data": {}}

    for input_sev, expected in [
        ("error", "error"),
        ("info", "info"),
        ("critical", "critical"),
        ("warning", "warn"),
        ("bogus", "info"),   # unknown → default info
    ]:
        p = {**base, "severity": input_sev}
        assert normalize_unifi_payload(p).severity == expected
