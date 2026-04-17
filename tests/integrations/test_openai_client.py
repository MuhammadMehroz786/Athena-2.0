import json

import httpx
import pytest

from athena.integrations.openai_client import (
    OpenAIAPIError,
    OpenAIClient,
    OpenAIRateLimitError,
)

BASE_URL = "https://api.openai.com/v1"
API_KEY = "test-openai-key"
MODEL = "gpt-4o-mini"


def _client_with_mock(
    status_code: int,
    json_body,
    *,
    captured: list | None = None,
    base_url: str = BASE_URL,
) -> OpenAIClient:
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
    return OpenAIClient(
        base_url=base_url, api_key=API_KEY, model=MODEL, client=http_client
    )


def _ok_body(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


async def test_summarize_event_returns_content():
    client = _client_with_mock(200, _ok_body("Switch offline."))
    try:
        result = await client.summarize_event({"vendor": "unifi"})
        assert result == "Switch offline."
    finally:
        await client.aclose()


async def test_summarize_event_sends_bearer_token():
    captured: list[httpx.Request] = []
    client = _client_with_mock(200, _ok_body("hi"), captured=captured)
    try:
        await client.summarize_event({"vendor": "unifi"})
        assert captured[0].headers["Authorization"] == f"Bearer {API_KEY}"
    finally:
        await client.aclose()


async def test_summarize_event_uses_correct_path():
    captured: list[httpx.Request] = []
    client = _client_with_mock(200, _ok_body("hi"), captured=captured)
    try:
        await client.summarize_event({"vendor": "unifi"})
        assert str(captured[0].url) == f"{BASE_URL}/chat/completions"
    finally:
        await client.aclose()


async def test_summarize_event_sends_expected_body_shape():
    captured: list[httpx.Request] = []
    client = _client_with_mock(200, _ok_body("hi"), captured=captured)
    try:
        await client.summarize_event({"vendor": "unifi", "event_type": "down"})
        payload = json.loads(captured[0].content.decode("utf-8"))
        assert payload["model"] == MODEL
        assert payload["max_tokens"] == 150
        assert payload["temperature"] == 0.2
        assert isinstance(payload["messages"], list)
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert "network operations assistant" in payload["messages"][0]["content"]
        user_content = json.loads(payload["messages"][1]["content"])
        assert user_content["vendor"] == "unifi"
        assert user_content["event_type"] == "down"
    finally:
        await client.aclose()


async def test_summarize_event_strips_whitespace():
    client = _client_with_mock(200, _ok_body("  hi\n"))
    try:
        assert await client.summarize_event({}) == "hi"
    finally:
        await client.aclose()


async def test_summarize_event_returns_none_when_no_content():
    client = _client_with_mock(200, {"choices": [{"message": {"role": "assistant"}}]})
    try:
        assert await client.summarize_event({}) is None
    finally:
        await client.aclose()


async def test_summarize_event_returns_none_when_choices_empty():
    client = _client_with_mock(200, {"choices": []})
    try:
        assert await client.summarize_event({}) is None
    finally:
        await client.aclose()


async def test_429_raises_rate_limit_error():
    client = _client_with_mock(429, {"error": "too many"})
    try:
        with pytest.raises(OpenAIRateLimitError) as exc_info:
            await client.summarize_event({})
        assert exc_info.value.status_code == 429
        assert isinstance(exc_info.value, OpenAIAPIError)
    finally:
        await client.aclose()


async def test_500_raises_api_error():
    client = _client_with_mock(500, {"error": "boom"})
    try:
        with pytest.raises(OpenAIAPIError) as exc_info:
            await client.summarize_event({})
        assert not isinstance(exc_info.value, OpenAIRateLimitError)
        assert exc_info.value.status_code == 500
    finally:
        await client.aclose()


async def test_network_error_raises_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = OpenAIClient(
        base_url=BASE_URL, api_key=API_KEY, model=MODEL, client=http_client
    )
    try:
        with pytest.raises(OpenAIAPIError) as exc_info:
            await client.summarize_event({})
        assert exc_info.value.status_code is None
        assert not isinstance(exc_info.value, OpenAIRateLimitError)
    finally:
        await client.aclose()


async def test_non_json_response_raises_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>oops</html>")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = OpenAIClient(
        base_url=BASE_URL, api_key=API_KEY, model=MODEL, client=http_client
    )
    try:
        with pytest.raises(OpenAIAPIError) as exc_info:
            await client.summarize_event({})
        assert not isinstance(exc_info.value, OpenAIRateLimitError)
        assert exc_info.value.status_code == 200
    finally:
        await client.aclose()


async def test_injected_client_not_closed_by_aclose():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(_ok_body("hi")).encode())

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = OpenAIClient(
        base_url=BASE_URL, api_key=API_KEY, model=MODEL, client=http_client
    )
    await client.aclose()
    assert not http_client.is_closed
    await http_client.aclose()


async def test_context_manager_closes_owned_client():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, content=json.dumps(_ok_body("hi")).encode())
    )
    http_client = httpx.AsyncClient(transport=transport)
    async with OpenAIClient(
        base_url=BASE_URL, api_key=API_KEY, model=MODEL, client=http_client
    ) as c:
        result = await c.summarize_event({})
        assert result == "hi"
