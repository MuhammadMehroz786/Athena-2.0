import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from athena.integrations.twilio_client import (
    TwilioAPIError,
    TwilioAuthError,
    TwilioClient,
    TwilioRateLimitError,
)

BASE_URL = "https://api.twilio.com/2010-04-01"
ACCOUNT_SID = "AC123"
AUTH_TOKEN = "supersecret"
FROM_NUMBER = "+15555550100"
TO_NUMBER = "+15555550199"


def _client_with_mock(
    status_code: int,
    json_body,
    *,
    captured: list | None = None,
    base_url: str = BASE_URL,
    account_sid: str = ACCOUNT_SID,
) -> TwilioClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        if isinstance(json_body, (bytes, str)):
            body = json_body
        else:
            body = json.dumps(json_body)
        return httpx.Response(
            status_code,
            content=body,
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return TwilioClient(
        account_sid=account_sid,
        auth_token=AUTH_TOKEN,
        base_url=base_url,
        client=http_client,
    )


def _sms_body(sid: str = "SM123") -> dict:
    return {"sid": sid, "status": "queued", "from": FROM_NUMBER, "to": TO_NUMBER}


def _call_body(sid: str = "CA123") -> dict:
    return {"sid": sid, "status": "queued", "from": FROM_NUMBER, "to": TO_NUMBER}


async def test_send_sms_happy_path():
    client = _client_with_mock(201, _sms_body("SM999"))
    try:
        result = await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert result["sid"] == "SM999"
    finally:
        await client.aclose()


async def test_send_sms_posts_to_correct_path():
    captured: list[httpx.Request] = []
    client = _client_with_mock(201, _sms_body(), captured=captured)
    try:
        await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert f"/Accounts/{ACCOUNT_SID}/Messages.json" in str(captured[0].url)
    finally:
        await client.aclose()


async def test_send_sms_sends_basic_auth():
    captured: list[httpx.Request] = []
    client = _client_with_mock(201, _sms_body(), captured=captured)
    try:
        await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        auth_header = captured[0].headers["Authorization"]
        assert auth_header.startswith("Basic ")
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode()
        assert decoded == f"{ACCOUNT_SID}:{AUTH_TOKEN}"
    finally:
        await client.aclose()


async def test_send_sms_form_encoded_body():
    captured: list[httpx.Request] = []
    client = _client_with_mock(201, _sms_body(), captured=captured)
    try:
        await client.send_sms(FROM_NUMBER, TO_NUMBER, "hello world")
        req = captured[0]
        assert "application/x-www-form-urlencoded" in req.headers["Content-Type"]
        form = parse_qs(req.content.decode())
        assert form["From"] == [FROM_NUMBER]
        assert form["To"] == [TO_NUMBER]
        assert form["Body"] == ["hello world"]
    finally:
        await client.aclose()


async def test_send_sms_url_encodes_account_sid():
    weird_sid = "AC/weird"
    captured: list[httpx.Request] = []
    client = _client_with_mock(
        201, _sms_body(), captured=captured, account_sid=weird_sid
    )
    try:
        await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        path = str(captured[0].url)
        assert "AC/weird" not in path
        assert "AC%2Fweird" in path
    finally:
        await client.aclose()


async def test_start_call_happy_path():
    client = _client_with_mock(201, _call_body("CA999"))
    try:
        result = await client.start_call(
            FROM_NUMBER, TO_NUMBER, "http://example.com/twiml.xml"
        )
        assert result["sid"] == "CA999"
    finally:
        await client.aclose()


async def test_start_call_posts_to_correct_path():
    captured: list[httpx.Request] = []
    client = _client_with_mock(201, _call_body(), captured=captured)
    try:
        await client.start_call(FROM_NUMBER, TO_NUMBER, "http://example.com/twiml.xml")
        assert f"/Accounts/{ACCOUNT_SID}/Calls.json" in str(captured[0].url)
    finally:
        await client.aclose()


async def test_start_call_form_encoded_body():
    captured: list[httpx.Request] = []
    client = _client_with_mock(201, _call_body(), captured=captured)
    try:
        await client.start_call(
            FROM_NUMBER, TO_NUMBER, "http://example.com/twiml.xml"
        )
        req = captured[0]
        assert "application/x-www-form-urlencoded" in req.headers["Content-Type"]
        form = parse_qs(req.content.decode())
        assert form["From"] == [FROM_NUMBER]
        assert form["To"] == [TO_NUMBER]
        assert form["Url"] == ["http://example.com/twiml.xml"]
    finally:
        await client.aclose()


async def test_start_call_default_twiml_url():
    captured: list[httpx.Request] = []
    client = _client_with_mock(201, _call_body(), captured=captured)
    try:
        await client.start_call(FROM_NUMBER, TO_NUMBER)
        form = parse_qs(captured[0].content.decode())
        assert form["Url"] == ["http://demo.twilio.com/docs/voice.xml"]
    finally:
        await client.aclose()


async def test_401_raises_auth_error():
    body_str = '{"code":20003,"message":"Authentication Error - invalid credentials"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, content=body_str.encode(),
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = TwilioClient(
        account_sid=ACCOUNT_SID, auth_token=AUTH_TOKEN,
        base_url=BASE_URL, client=http_client,
    )
    try:
        with pytest.raises(TwilioAuthError) as exc_info:
            await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert exc_info.value.status_code == 401
        msg = str(exc_info.value)
        assert "invalid credentials" not in msg
        assert "20003" not in msg
        assert body_str not in msg
    finally:
        await client.aclose()


async def test_403_raises_auth_error():
    body_str = '{"code":20005,"message":"forbidden"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, content=body_str.encode(),
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = TwilioClient(
        account_sid=ACCOUNT_SID, auth_token=AUTH_TOKEN,
        base_url=BASE_URL, client=http_client,
    )
    try:
        with pytest.raises(TwilioAuthError) as exc_info:
            await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert exc_info.value.status_code == 403
        msg = str(exc_info.value)
        assert "forbidden" not in msg
        assert body_str not in msg
    finally:
        await client.aclose()


async def test_429_raises_rate_limit_error():
    client = _client_with_mock(429, {"code": 20429, "message": "too many"})
    try:
        with pytest.raises(TwilioRateLimitError) as exc_info:
            await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert exc_info.value.status_code == 429
        assert isinstance(exc_info.value, TwilioAPIError)
    finally:
        await client.aclose()


async def test_500_raises_api_error():
    client = _client_with_mock(500, {"error": "boom specific detail"})
    try:
        with pytest.raises(TwilioAPIError) as exc_info:
            await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert not isinstance(exc_info.value, TwilioRateLimitError)
        assert not isinstance(exc_info.value, TwilioAuthError)
        assert exc_info.value.status_code == 500
        assert "boom specific detail" in str(exc_info.value)
    finally:
        await client.aclose()


async def test_network_error_raises_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = TwilioClient(
        account_sid=ACCOUNT_SID, auth_token=AUTH_TOKEN,
        base_url=BASE_URL, client=http_client,
    )
    try:
        with pytest.raises(TwilioAPIError) as exc_info:
            await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert exc_info.value.status_code is None
    finally:
        await client.aclose()


async def test_non_json_success_raises_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, content=b"<html>")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = TwilioClient(
        account_sid=ACCOUNT_SID, auth_token=AUTH_TOKEN,
        base_url=BASE_URL, client=http_client,
    )
    try:
        with pytest.raises(TwilioAPIError) as exc_info:
            await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert exc_info.value.status_code == 201
    finally:
        await client.aclose()


async def test_injected_client_not_closed_by_aclose():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, content=json.dumps(_sms_body()).encode())

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = TwilioClient(
        account_sid=ACCOUNT_SID, auth_token=AUTH_TOKEN,
        base_url=BASE_URL, client=http_client,
    )
    await client.aclose()
    assert not http_client.is_closed
    await http_client.aclose()


async def test_context_manager_closes_owned_client():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(201, content=json.dumps(_sms_body()).encode())
    )
    http_client = httpx.AsyncClient(transport=transport)
    async with TwilioClient(
        account_sid=ACCOUNT_SID, auth_token=AUTH_TOKEN,
        base_url=BASE_URL, client=http_client,
    ) as c:
        result = await c.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert result["sid"] == "SM123"


async def test_network_error_suppresses_exception_chain():
    """The original httpx.RequestError carries the request object and its
    Authorization header. Using 'raise ... from None' prevents that object
    from being preserved in __cause__ (and keeps tracebacks clean)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = TwilioClient(
        account_sid=ACCOUNT_SID, auth_token=AUTH_TOKEN,
        base_url=BASE_URL, client=http_client,
    )
    try:
        with pytest.raises(TwilioAPIError) as exc_info:
            await client.send_sms(FROM_NUMBER, TO_NUMBER, "hi")
        assert exc_info.value.__cause__ is None
    finally:
        await client.aclose()
