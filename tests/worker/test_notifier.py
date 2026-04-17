from datetime import datetime, UTC
from unittest.mock import AsyncMock

import pytest

from athena.integrations.twilio_client import TwilioAPIError
from athena.worker.notifier import NotifyConfig, dispatch_notifications


_DEFAULT_VENDOR = "domotz"
_DEFAULT_EVENT_TYPE = "device.down"
_DEFAULT_RECEIVED_AT = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)


def _fields(**overrides) -> dict:
    base = dict(
        vendor=_DEFAULT_VENDOR,
        event_type=_DEFAULT_EVENT_TYPE,
        received_at=_DEFAULT_RECEIVED_AT,
    )
    base.update(overrides)
    return base


def _cfg(**overrides) -> NotifyConfig:
    base = dict(
        enabled=True,
        from_number="+15555550100",
        to_number="+15555550199",
        twiml_url=None,
    )
    base.update(overrides)
    return NotifyConfig(**base)


def _mk_client(sms_sid: str = "SM1", call_sid: str = "CA1"):
    c = AsyncMock()
    c.send_sms = AsyncMock(return_value={"sid": sms_sid})
    c.start_call = AsyncMock(return_value={"sid": call_sid})
    return c


@pytest.mark.asyncio
async def test_dispatch_notify_critical_sends_sms_and_call():
    client = _mk_client("SMcrit", "CAcrit")
    outcomes = await dispatch_notifications(
        client, "notify_critical", "summary text", **_fields(), config=_cfg()
    )
    assert client.send_sms.await_count == 1
    assert client.start_call.await_count == 1
    assert outcomes == ["sms:sent:SMcrit", "call:sent:CAcrit"]


@pytest.mark.asyncio
async def test_dispatch_notify_warn_sends_sms_only():
    client = _mk_client("SMwarn")
    outcomes = await dispatch_notifications(
        client, "notify_warn", "summary text", **_fields(), config=_cfg()
    )
    assert client.send_sms.await_count == 1
    assert client.start_call.await_count == 0
    assert outcomes == ["sms:sent:SMwarn"]


@pytest.mark.asyncio
async def test_dispatch_log_only_sends_nothing():
    client = _mk_client()
    outcomes = await dispatch_notifications(
        client, "log_only", "x", **_fields(), config=_cfg()
    )
    assert outcomes == []
    assert client.send_sms.await_count == 0
    assert client.start_call.await_count == 0


@pytest.mark.asyncio
async def test_dispatch_unknown_classification_sends_nothing():
    client = _mk_client()
    outcomes = await dispatch_notifications(
        client, "bogus", "x", **_fields(), config=_cfg()
    )
    assert outcomes == []
    assert client.send_sms.await_count == 0


@pytest.mark.asyncio
async def test_dispatch_when_disabled_returns_empty():
    client = _mk_client()
    outcomes = await dispatch_notifications(
        client, "notify_critical", "x", **_fields(), config=_cfg(enabled=False)
    )
    assert outcomes == []
    assert client.send_sms.await_count == 0


@pytest.mark.asyncio
async def test_dispatch_when_client_is_none():
    outcomes = await dispatch_notifications(
        None, "notify_critical", "x", **_fields(), config=_cfg()
    )
    assert outcomes == []


@pytest.mark.asyncio
async def test_dispatch_when_to_number_empty():
    client = _mk_client()
    outcomes = await dispatch_notifications(
        client, "notify_critical", "x", **_fields(), config=_cfg(to_number="")
    )
    assert outcomes == []
    assert client.send_sms.await_count == 0


@pytest.mark.asyncio
async def test_dispatch_sms_failure_does_not_raise():
    client = AsyncMock()
    client.send_sms = AsyncMock(
        side_effect=TwilioAPIError("boom", status_code=500, url="u")
    )
    client.start_call = AsyncMock(return_value={"sid": "CAok"})
    outcomes = await dispatch_notifications(
        client, "notify_critical", "x", **_fields(), config=_cfg()
    )
    assert client.send_sms.await_count == 1
    assert client.start_call.await_count == 1
    assert outcomes[0] == "sms:failed:500"
    assert outcomes[1] == "call:sent:CAok"


@pytest.mark.asyncio
async def test_dispatch_call_failure_does_not_raise():
    client = AsyncMock()
    client.send_sms = AsyncMock(return_value={"sid": "SMok"})
    client.start_call = AsyncMock(
        side_effect=TwilioAPIError("boom", status_code=429, url="u")
    )
    outcomes = await dispatch_notifications(
        client, "notify_critical", "x", **_fields(), config=_cfg()
    )
    assert outcomes[0] == "sms:sent:SMok"
    assert outcomes[1] == "call:failed:429"


@pytest.mark.asyncio
async def test_dispatch_message_body_format():
    client = _mk_client()
    await dispatch_notifications(
        client,
        "notify_critical",
        "Link down on port 22",
        **_fields(vendor="domotz", event_type="device.down"),
        config=_cfg(),
    )
    args, kwargs = client.send_sms.await_args
    body = args[2] if len(args) >= 3 else kwargs.get("body")
    assert body.startswith("[NOTIFY_CRITICAL] domotz/device.down on ")
    assert "2026-04-17T12:00:00+00:00" in body
    assert "Link down on port 22" in body


@pytest.mark.asyncio
async def test_dispatch_message_body_truncated_at_1400_chars():
    client = _mk_client()
    long_summary = "Z" * 5000
    await dispatch_notifications(
        client, "notify_warn", long_summary, **_fields(), config=_cfg()
    )
    args, kwargs = client.send_sms.await_args
    body = args[2] if len(args) >= 3 else kwargs.get("body")
    assert len(body) <= 1400


@pytest.mark.asyncio
async def test_dispatch_handles_null_summary():
    client = _mk_client()
    await dispatch_notifications(
        client, "notify_warn", None, **_fields(), config=_cfg()
    )
    args, kwargs = client.send_sms.await_args
    body = args[2] if len(args) >= 3 else kwargs.get("body")
    assert "(no summary)" in body


@pytest.mark.asyncio
async def test_dispatch_message_body_truncates_summary_not_header():
    """With a short header and very long summary, the header must remain
    fully intact and only the summary portion gets truncated."""
    client = _mk_client()
    long_summary = "S" * 5000
    await dispatch_notifications(
        client,
        "notify_warn",
        long_summary,
        **_fields(vendor="domotz", event_type="device.down"),
        config=_cfg(),
    )
    args, kwargs = client.send_sms.await_args
    body = args[2] if len(args) >= 3 else kwargs.get("body")
    expected_header = (
        "[NOTIFY_WARN] domotz/device.down on "
        "2026-04-17T12:00:00+00:00: "
    )
    # First 80 chars of the body must match the header exactly (header is < 80).
    assert body.startswith(expected_header)
    assert body[: len(expected_header)] == expected_header
    # Total body must be within the 1400-char cap.
    assert len(body) <= 1400
    # After the header, only summary content remains; nothing got clobbered.
    assert set(body[len(expected_header):]) == {"S"}


@pytest.mark.asyncio
async def test_dispatch_message_body_pathological_header_truncates_header():
    """If the header alone exceeds _BODY_MAX, the body is capped at
    exactly _BODY_MAX chars (truncated header, no summary)."""
    client = _mk_client()
    verbose_vendor = "v" * 900
    verbose_event_type = "e" * 900
    await dispatch_notifications(
        client,
        "notify_warn",
        "short-summary",
        vendor=verbose_vendor,
        event_type=verbose_event_type,
        received_at=_DEFAULT_RECEIVED_AT,
        config=_cfg(),
    )
    args, kwargs = client.send_sms.await_args
    body = args[2] if len(args) >= 3 else kwargs.get("body")
    assert len(body) == 1400
