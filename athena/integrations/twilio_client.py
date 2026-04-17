"""Async Twilio REST API client."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_BODY_EXCERPT_MAX = 256
_DEFAULT_TWIML_URL = "http://demo.twilio.com/docs/voice.xml"


class TwilioAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None, url: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.url = url


class TwilioAuthError(TwilioAPIError):
    pass


class TwilioRateLimitError(TwilioAPIError):
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
) -> TwilioAPIError:
    if status_code in (401, 403):
        msg = f"{method} {path} -> {status_code}"
        return TwilioAuthError(msg, status_code=status_code, url=url)
    msg = f"{method} {path} -> {status_code} body={_excerpt(body)}"
    if status_code == 429:
        return TwilioRateLimitError(msg, status_code=status_code, url=url)
    return TwilioAPIError(msg, status_code=status_code, url=url)


class TwilioClient:
    """Async client for the Twilio REST API."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        base_url: str = "https://api.twilio.com/2010-04-01",
        timeout: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._account_sid = account_sid
        self._auth = httpx.BasicAuth(account_sid, auth_token)
        self._base_url = base_url.rstrip("/")
        self._headers = {"Accept": "application/json"}
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(timeout=timeout)
            self._owns_client = True

    async def __aenter__(self) -> "TwilioClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _post_form(self, path: str, data: dict[str, str]) -> Any:
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.post(
                url, headers=self._headers, data=data, auth=self._auth
            )
        except httpx.RequestError as e:
            logger.warning("twilio POST %s network-error", path)
            raise TwilioAPIError(
                f"POST {path} -> network error: {e.__class__.__name__}",
                status_code=None,
                url=url,
            ) from e

        if resp.status_code >= 400:
            logger.warning("twilio POST %s (%d)", path, resp.status_code)
            raise _build_error("POST", path, resp.status_code, resp.text, url)

        logger.info("twilio POST %s (%d)", path, resp.status_code)
        try:
            return resp.json()
        except ValueError as exc:
            logger.warning("twilio POST %s non-json-response", path)
            raise TwilioAPIError(
                f"POST {path} -> non-JSON response",
                status_code=resp.status_code,
                url=url,
            ) from exc

    async def send_sms(self, from_number: str, to_number: str, body: str) -> dict:
        path = f"/Accounts/{quote(str(self._account_sid), safe='')}/Messages.json"
        data = {"From": from_number, "To": to_number, "Body": body}
        return await self._post_form(path, data)

    async def start_call(
        self,
        from_number: str,
        to_number: str,
        twiml_url: str = _DEFAULT_TWIML_URL,
    ) -> dict:
        path = f"/Accounts/{quote(str(self._account_sid), safe='')}/Calls.json"
        data = {"From": from_number, "To": to_number, "Url": twiml_url}
        return await self._post_form(path, data)
