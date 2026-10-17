"""Future read-only configuration and offline signing, never network access."""

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass

from data.schema import epoch_ms, utc
from exchange.contracts import READ_ONLY, ExchangeBlocked, require


class Credentials:
    __slots__ = ("_key", "_secret")

    def __init__(self, key, secret):
        # The docs do not specify a fixed key length/encoding. Validate only a
        # safe local string envelope; this does not authenticate a real key.
        for value in (key, secret):
            require(isinstance(value, str) and 1 <= len(value) <= 512
                    and value.isascii() and all(33 <= ord(c) <= 126 for c in value),
                    "INVALID_OR_MISSING_CREDENTIALS")
        self._key, self._secret = key, secret

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        return cls(env.get("COINDCX_API_KEY"), env.get("COINDCX_API_SECRET"))

    def __repr__(self):
        return "Credentials(<redacted>)"


@dataclass(frozen=True)
class ReadOnlyPolicy:
    enabled: bool = False

    def __post_init__(self):
        require(type(self.enabled) is bool, "INVALID_READ_ONLY_CONFIGURATION")

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        raw = env.get("COINDCX_ENABLE_READ_ONLY", "0")
        require(raw in ("0", "1"), "INVALID_READ_ONLY_CONFIGURATION")
        return cls(raw == "1")


class SignedReadRequest:
    __slots__ = ("url", "body", "_headers")

    def __init__(self, url, body, headers):
        self.url, self.body, self._headers = url, body, headers

    def __repr__(self):
        return "SignedReadRequest(<sensitive; offline only>)"

    def headers_for_offline_test(self):
        """Sensitive material; intentionally never used by any network method."""
        return dict(self._headers)


def prepare_read_only(operation, credentials, policy, *, at, separately_approved=False,
                      client_order_id=None, market=None):
    """Sign documented read-only POST bodies locally; nothing is transmitted.

    Deliberately no signing helper for order creation, cancellation, modification,
    transfers or withdrawals. An enabled environment flag alone is insufficient.
    """
    require(isinstance(policy, ReadOnlyPolicy) and policy.enabled is True and separately_approved is True,
            "READ_ONLY_NOT_SEPARATELY_APPROVED")
    require(isinstance(operation, str) and operation in READ_ONLY, "FORBIDDEN_AUTHENTICATED_OPERATION")
    require(isinstance(credentials, Credentials), "INVALID_OR_MISSING_CREDENTIALS")
    payload = {"timestamp": epoch_ms(utc(at))}
    require(payload["timestamp"] > 0, "INVALID_TIMESTAMP")
    if operation == "order_status":
        require(isinstance(client_order_id, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", client_order_id),
                "CLIENT_ORDER_ID_REQUIRED")
        payload["client_order_id"] = client_order_id
    elif operation == "active_orders":
        require(isinstance(market, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", market), "MARKET_REQUIRED")
        payload.update(market=market, page=1, size=200)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(credentials._secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return SignedReadRequest(READ_ONLY[operation], body, {"Content-Type": "application/json",
                             "X-AUTH-APIKEY": credentials._key, "X-AUTH-SIGNATURE": signature})


def private_failure(http_status):
    """Mock failure classification only; no automatic send or retry."""
    if http_status in (401, 403):
        return "AUTHENTICATION_OR_PERMISSION_ERROR"
    if http_status == 429:
        return "RATE_LIMITED_RECONCILE_BEFORE_RETRY"
    return "PRIVATE_REQUEST_UNRESOLVED"
