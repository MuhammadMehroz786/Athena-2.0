"""Async Domotz Public API client."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BODY_EXCERPT_MAX = 256


class DomotzAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None, url: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.url = url


class DomotzNotFoundError(DomotzAPIError):
    pass


class DomotzRateLimitError(DomotzAPIError):
    pass


def _excerpt(text: str) -> str:
    if len(text) <= _BODY_EXCERPT_MAX:
        return text
    return text[:_BODY_EXCERPT_MAX] + "..."


def _build_error(
    method: str,
    path: str,
    status_code: int | None,
    body: str,
    url: str,
) -> DomotzAPIError:
    msg = f"{method} {path} -> {status_code} body={_excerpt(body)}"
    if status_code == 404:
        return DomotzNotFoundError(msg, status_code=status_code, url=url)
    if status_code == 429:
        return DomotzRateLimitError(msg, status_code=status_code, url=url)
    return DomotzAPIError(msg, status_code=status_code, url=url)


class DomotzClient:
    """Async client for the Domotz Public API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._headers = {
            "X-Api-Key": api_key,
            "Accept": "application/json",
        }
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(timeout=timeout)
            self._owns_client = True

    async def __aenter__(self) -> "DomotzClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(self, method: str, path: str) -> Any:
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.request(method, url, headers=self._headers)
        except httpx.RequestError as e:
            logger.warning("domotz %s %s network-error", method, path)
            raise DomotzAPIError(
                f"{method} {path} -> network error: {e.__class__.__name__}",
                status_code=None,
                url=url,
            ) from e

        if resp.status_code >= 400:
            logger.warning("domotz %s %s (%d)", method, path, resp.status_code)
            raise _build_error(method, path, resp.status_code, resp.text, url)

        logger.info("domotz %s %s (%d)", method, path, resp.status_code)
        return resp.json()

    async def list_agents(self) -> list[dict]:
        data = await self._request("GET", "/agent")
        return data

    async def get_agent(self, agent_id: str) -> dict:
        data = await self._request("GET", f"/agent/{agent_id}")
        return data

    async def list_devices(self, agent_id: str) -> list[dict]:
        data = await self._request("GET", f"/agent/{agent_id}/device")
        return data

    async def get_device(self, agent_id: str, device_id: str) -> dict:
        data = await self._request("GET", f"/agent/{agent_id}/device/{device_id}")
        return data
