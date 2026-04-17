import json

import httpx
import pytest

from athena.integrations.domotz_client import (
    DomotzAPIError,
    DomotzClient,
    DomotzNotFoundError,
    DomotzRateLimitError,
)

BASE_URL = "https://api-eu-west-1-cell-1.domotz.com/public-api/v1"
API_KEY = "test-key"


def _client_with_mock(
    status_code: int,
    json_body,
    *,
    captured: list | None = None,
    base_url: str = BASE_URL,
) -> DomotzClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        body = json.dumps(json_body) if not isinstance(json_body, str) else json_body
        return httpx.Response(
            status_code,
            content=body,
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return DomotzClient(base_url=base_url, api_key=API_KEY, client=http_client)


async def test_list_agents_returns_parsed_json():
    agents = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    client = _client_with_mock(200, agents)
    try:
        result = await client.list_agents()
        assert result == agents
    finally:
        await client.aclose()


async def test_get_agent_sends_api_key_header():
    captured: list[httpx.Request] = []
    client = _client_with_mock(200, {"id": 1}, captured=captured)
    try:
        await client.get_agent("1")
        assert captured[0].headers["X-Api-Key"] == API_KEY
        assert captured[0].headers["Accept"] == "application/json"
    finally:
        await client.aclose()


async def test_list_devices_uses_correct_path():
    captured: list[httpx.Request] = []
    client = _client_with_mock(200, [], captured=captured)
    try:
        await client.list_devices("42")
        assert str(captured[0].url) == f"{BASE_URL}/agent/42/device"
    finally:
        await client.aclose()


async def test_get_device_uses_correct_path():
    captured: list[httpx.Request] = []
    client = _client_with_mock(200, {"id": 7}, captured=captured)
    try:
        await client.get_device("42", "7")
        assert str(captured[0].url) == f"{BASE_URL}/agent/42/device/7"
    finally:
        await client.aclose()


async def test_404_raises_not_found_error():
    client = _client_with_mock(404, {"error": "missing"})
    try:
        with pytest.raises(DomotzNotFoundError) as exc_info:
            await client.get_agent("nope")
        assert exc_info.value.status_code == 404
        assert isinstance(exc_info.value, DomotzAPIError)
    finally:
        await client.aclose()


async def test_429_raises_rate_limit_error():
    client = _client_with_mock(429, {"error": "too many"})
    try:
        with pytest.raises(DomotzRateLimitError) as exc_info:
            await client.list_agents()
        assert exc_info.value.status_code == 429
        assert isinstance(exc_info.value, DomotzAPIError)
    finally:
        await client.aclose()


async def test_500_raises_api_error():
    client = _client_with_mock(500, {"error": "boom"})
    try:
        with pytest.raises(DomotzAPIError) as exc_info:
            await client.list_agents()
        assert not isinstance(exc_info.value, DomotzNotFoundError)
        assert not isinstance(exc_info.value, DomotzRateLimitError)
        assert exc_info.value.status_code == 500
    finally:
        await client.aclose()


async def test_network_error_raises_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = DomotzClient(base_url=BASE_URL, api_key=API_KEY, client=http_client)
    try:
        with pytest.raises(DomotzAPIError) as exc_info:
            await client.list_agents()
        assert exc_info.value.status_code is None
        assert not isinstance(exc_info.value, DomotzNotFoundError)
        assert not isinstance(exc_info.value, DomotzRateLimitError)
    finally:
        await client.aclose()


async def test_base_url_trailing_slash_tolerated():
    captured: list[httpx.Request] = []
    client = _client_with_mock(
        200, [], captured=captured, base_url=BASE_URL + "/"
    )
    try:
        await client.list_agents()
        assert str(captured[0].url) == f"{BASE_URL}/agent"
    finally:
        await client.aclose()


async def test_client_is_reusable_with_context_manager():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"[]")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    async with DomotzClient(base_url=BASE_URL, api_key=API_KEY, client=http_client) as c:
        result = await c.list_agents()
        assert result == []


async def test_injected_client_not_closed_by_aclose():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"[]")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = DomotzClient(base_url=BASE_URL, api_key=API_KEY, client=http_client)
    await client.aclose()
    assert not http_client.is_closed
    await http_client.aclose()


async def test_error_message_excludes_api_key():
    client = _client_with_mock(500, {"error": "boom"})
    try:
        with pytest.raises(DomotzAPIError) as exc_info:
            await client.list_agents()
        assert API_KEY not in str(exc_info.value)
    finally:
        await client.aclose()


async def test_non_json_success_raises_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>oops</html>")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = DomotzClient(base_url=BASE_URL, api_key=API_KEY, client=http_client)
    try:
        with pytest.raises(DomotzAPIError) as exc_info:
            await client.list_agents()
        assert not isinstance(exc_info.value, DomotzNotFoundError)
        assert not isinstance(exc_info.value, DomotzRateLimitError)
        assert exc_info.value.status_code == 200
    finally:
        await client.aclose()


async def test_path_segments_url_encoded():
    captured: list[httpx.Request] = []
    client = _client_with_mock(200, {"id": 1}, captured=captured)
    try:
        await client.get_device(agent_id="a/b", device_id="x y")
        raw_path = captured[0].url.raw_path.decode("ascii")
        assert raw_path.endswith("/agent/a%2Fb/device/x%20y")
    finally:
        await client.aclose()
