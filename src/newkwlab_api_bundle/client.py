"""NewKwLab API Bundle — Python SDK.

Wraps the production gateway at https://api.newkwlab.com/gateway:
    POST /v1/activate            activate a Gumroad license key -> credits + first API key
    GET  /v1/usage               balance, credit lots, per-product usage (Bearer key)
    GET  /v1/usage/history       ledger history (Bearer key)
    POST /v1/keys                issue an additional API key (Bearer key)
    DELETE /v1/keys/:id          disable an API key (Bearer key)
    GET|POST /v1/<product>/<endpoint>   product call, charged per result in credits

Product calls return credit headers: x-credits-charged, x-credits-balance,
x-cache (HIT = same key + same parameters within 24h, charged 0 credits).
"Not found" results and upstream errors are never charged.

Standard library only (urllib) — no third-party dependencies.
Requires Python >= 3.9.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

__all__ = ["DEFAULT_BASE_URL", "GatewayError", "CallResult", "NewKwLabClient"]

DEFAULT_BASE_URL = "https://api.newkwlab.com/gateway"


class GatewayError(Exception):
    """Raised for gateway (and passed-through upstream) errors.

    Attributes:
        status: HTTP status code (0 when the gateway could not be reached).
        code:   Machine-readable error code, e.g. "UNAUTHORIZED".
        detail: Optional human-readable detail from the gateway.
    """

    def __init__(self, status: int, code: str, detail: Optional[str] = None):
        message = f"Gateway error {status}: {code}"
        if detail:
            message += f" — {detail}"
        super().__init__(message)
        self.status = status
        self.code = code
        self.detail = detail


@dataclass
class CallResult:
    """Result of a product call: payload plus the credit headers."""

    data: Any
    credits_charged: Optional[int]
    credits_balance: Optional[int]
    cache: Optional[str]


def _error_from(status: int, data: Any) -> GatewayError:
    """Build a GatewayError from an error body.

    The gateway's own errors look like {"error": {"code": ..., "detail"/"reason": ...}};
    upstream errors pass through in the flat form {"code": ..., "error": "..."}.
    Both shapes are parsed (same dual-shape handling as the CLI).
    """
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return GatewayError(status, err.get("code") or "UNKNOWN_ERROR",
                                err.get("detail") or err.get("reason"))
        if data.get("code"):
            return GatewayError(status, data["code"],
                                err if isinstance(err, str) else None)
    return GatewayError(status, "UNKNOWN_ERROR", None)


def _int_header(headers, name: str) -> Optional[int]:
    value = headers.get(name) if headers is not None else None
    return int(value) if value is not None else None


class NewKwLabClient:
    """Client for the NewKwLab API Bundle gateway.

    Args:
        api_key:  Aggregate API key (``nkw_live_...``). Not needed for
                  ``health()`` / ``activate()``. Falls back to ``NKW_API_KEY``.
        base_url: Gateway base URL. Falls back to ``NKW_BASE_URL``, then the
                  production gateway.
        timeout:  Per-request timeout in seconds (default 30).
    """

    def __init__(self, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, timeout: float = 30.0):
        self.api_key = api_key if api_key is not None else os.environ.get("NKW_API_KEY")
        base = base_url or os.environ.get("NKW_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = base.rstrip("/")
        self.timeout = timeout

    # -- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, body: Any = None, auth: bool = True):
        headers = {}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        if auth:
            if not self.api_key:
                raise ValueError(
                    "An API key is required for this call — pass api_key=... or set NKW_API_KEY."
                )
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = Request(f"{self.base_url}{path}", data=payload, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as res:
                status, resp_headers, raw = res.status, res.headers, res.read()
        except HTTPError as e:
            status, resp_headers, raw = e.code, e.headers, e.read()
        except URLError as e:
            raise GatewayError(0, "CONNECTION_ERROR", str(e.reason)) from e
        text = raw.decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except ValueError:
            data = text
        return status, resp_headers, data

    def _unwrap(self, method: str, path: str, body: Any = None, auth: bool = True):
        status, _headers, data = self._request(method, path, body=body, auth=auth)
        if status >= 400:
            raise _error_from(status, data)
        return data

    # -- account -----------------------------------------------------------

    def health(self):
        """GET /health — no key required. Returns {"ok": True}."""
        return self._unwrap("GET", "/health", auth=False)

    def activate(self, license_key: str, product_permalink: str):
        """POST /v1/activate — exchange a Gumroad license key for credits.

        On first activation the response includes ``api_key`` (plaintext,
        shown once); store it. Repeat activation returns
        ``key_already_issued: True`` instead.
        """
        return self._unwrap("POST", "/v1/activate", auth=False, body={
            "license_key": license_key,
            "product_permalink": product_permalink,
        })

    def usage(self):
        """GET /v1/usage — balance, credit lots (source / remaining / expires_at), per-product usage."""
        return self._unwrap("GET", "/v1/usage")

    def usage_history(self, days: int = 30, limit: int = 50, offset: int = 0):
        """GET /v1/usage/history — ledger entries for the last `days` days (1–90)."""
        q = urlencode({"days": days, "limit": limit, "offset": offset})
        return self._unwrap("GET", f"/v1/usage/history?{q}")

    def create_key(self, label: Optional[str] = None):
        """POST /v1/keys — issue an additional API key. The plaintext key is returned once."""
        return self._unwrap("POST", "/v1/keys", body={"label": label} if label else {})

    def disable_key(self, key_id) -> Any:
        """DELETE /v1/keys/:id — disable one of your API keys."""
        return self._unwrap("DELETE", f"/v1/keys/{quote(str(key_id), safe='')}")

    # -- product calls -------------------------------------------------------

    def call(self, product: str, endpoint: str, method: str = "GET",
             params: Optional[dict] = None, body: Any = None) -> CallResult:
        """Call any connected product: /v1/<product>/<endpoint>.

        Args:
            product:  e.g. "emailcheck", "vatscope", "leilookup"
            endpoint: e.g. "/validate" (leading slash optional)
            method:   HTTP method (default "GET")
            params:   query parameters dict
            body:     JSON body for POST calls

        Returns a CallResult with .data, .credits_charged, .credits_balance
        and .cache. On gateway errors, raises GatewayError with .status and
        .code (401 UNAUTHORIZED, 402 INSUFFICIENT_CREDITS,
        403 CAPABILITY_DENIED, 503 PRODUCT_NOT_CONNECTED, ...).
        """
        ep = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        q = urlencode(params) if params else ""
        path = f"/v1/{product}{ep}" + (f"?{q}" if q else "")
        status, headers, data = self._request(method, path, body=body)
        if status >= 400:
            raise _error_from(status, data)
        return CallResult(
            data=data,
            credits_charged=_int_header(headers, "x-credits-charged"),
            credits_balance=_int_header(headers, "x-credits-balance"),
            cache=headers.get("x-cache") if headers is not None else None,
        )

    # -- Convenience wrappers for the anchor products ------------------------

    def email_check(self, email: str) -> CallResult:
        """EmailCheck (1 credit): full validation verdict for one email address."""
        return self.call("emailcheck", "/validate", params={"email": email})

    def phone_check(self, phone: str) -> CallResult:
        """PhoneCheck (1 credit): validity and line details for one phone number."""
        return self.call("phonecheck", "/validate", params={"phone": phone})

    def card_check(self, number: str) -> CallResult:
        """CardCheck (1 credit): BIN / Luhn / brand checks for one card number."""
        return self.call("cardcheck", "/validate", params={"number": number})
