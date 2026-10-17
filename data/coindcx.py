"""Unsigned GET-only public API, based on the official documentation.

See docs/COINDCX_API.md for the exact source revision and compatibility limits.
No private route, authentication header, or order method exists here.
"""

import json
import math
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from data.cache import ResponseCache
from data.schema import SYMBOL, epoch_ms, milliseconds, utc

ROUTES = {
    "markets": "https://api.coindcx.com/exchange/v1/markets",
    "details": "https://api.coindcx.com/exchange/v1/markets_details",
    "candles": "https://api.coindcx.com/market_data/candles",
}
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class PublicDataError(ValueError):
    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def unsigned_get(url: str, timeout: float) -> HttpResponse:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment
            or f"{parsed.scheme}://{parsed.netloc}{parsed.path}" not in ROUTES.values()):
        raise PublicDataError("FORBIDDEN_ROUTE", "only the three documented public GET routes are allowed")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "CoinDCX-Offline-Research/2"}, method="GET")
    opener = build_opener(NoRedirect())  # Default HTTPS certificate/hostname verification stays enabled.
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise PublicDataError("RESPONSE_TOO_LARGE", "public response exceeds the local size limit")
        return HttpResponse(response.code, body, {key.lower(): value for key, value in response.headers.items()})


@dataclass(frozen=True, slots=True)
class Market:
    pair: str
    symbol: str
    quote_currency: str
    asset_currency: str
    status: str
    active_confirmed: bool


@dataclass(frozen=True, slots=True)
class History:
    rows: tuple[dict, ...]
    market: Market
    raw_pages: tuple[bytes, ...]
    source_order_valid: bool
    warnings: tuple[str, ...]


class PublicClient:
    def __init__(self, cache: ResponseCache | None = None, *, transport: Callable = unsigned_get,
                 now: Callable = lambda: datetime.now(timezone.utc), sleep: Callable = time.sleep,
                 monotonic: Callable = time.monotonic, timeout: float = 10,
                 attempts: int = 3, request_interval: float = 0.5, max_retry_delay: float = 60):
        for name, value in (("timeout", timeout), ("request_interval", request_interval),
                            ("max_retry_delay", max_retry_delay)):
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid {name}")
        if timeout == 0 or type(attempts) is not int or not 1 <= attempts <= 5:
            raise ValueError("timeout must be positive; attempts must be between 1 and 5")
        self.cache, self.transport, self.now, self.sleep = cache, transport, now, sleep
        self.monotonic, self.timeout, self.attempts = monotonic, timeout, attempts
        self.request_interval, self.max_retry_delay = request_interval, max_retry_delay
        self.last_request: float | None = None

    def _json(self, route: str, params: dict, validate: Callable, ttl: timedelta):
        url = ROUTES[route] + ("?" + urlencode(sorted(params.items())) if params else "")
        if self.cache:
            entry = self.cache.get(url, self.now(), ttl)
            if entry:
                try:
                    return validate(self._decode(entry.body)), entry.body
                except (ValueError, TypeError, KeyError):
                    pass  # Invalid cached content must be replaced through a successful request.
        for attempt in range(self.attempts):
            if self.last_request is not None:
                pause = self.request_interval - (self.monotonic() - self.last_request)
                if pause > 0:
                    self.sleep(pause)
            self.last_request = self.monotonic()
            response = None
            try:
                response = self.transport(url, self.timeout)
            except (OSError, URLError) as exc:
                reason = getattr(exc, "reason", exc)
                if isinstance(reason, ssl.SSLError):
                    raise PublicDataError("TLS_VERIFICATION_FAILED", "TLS verification failed; verification was not disabled") from exc
                if "403" in str(reason):
                    raise PublicDataError("ACCESS_DENIED", "public endpoint was blocked by the network or proxy", 403) from exc
                failure = PublicDataError("NETWORK_FAILURE", "public market-data request failed")
            else:
                if response.status == 200:
                    try:
                        result = validate(self._decode(response.body))
                    except (ValueError, TypeError, KeyError, OverflowError) as exc:
                        raise PublicDataError("INVALID_API_RESPONSE", "public endpoint returned malformed or unsupported data") from exc
                    if self.cache:
                        self.cache.put(url, response.body, self.now())
                    return result, response.body
                failure = PublicDataError("API_FAILURE", f"public market-data endpoint returned HTTP {response.status}", response.status)
                if response.status not in {429, 500, 502, 503, 504}:
                    raise failure
            if attempt + 1 == self.attempts:
                raise failure
            delay = float(2 ** attempt)
            header = next((value for key, value in (response.headers if response else {}).items()
                           if key.lower() == "retry-after"), None)
            if header:
                try:
                    delay = float(header)
                except ValueError:
                    try:
                        delay = (utc(parsedate_to_datetime(header)) - utc(self.now())).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        pass
            if not math.isfinite(delay) or delay > self.max_retry_delay:
                raise PublicDataError("RETRY_LATER", "server retry delay exceeds the local waiting budget", response.status if response else None)
            self.sleep(max(0, delay))
        raise AssertionError("unreachable retry state")

    @staticmethod
    def _decode(body: bytes):
        def invalid_constant(value):
            raise ValueError("nonfinite JSON number")
        return json.loads(body.decode("utf-8"), parse_float=Decimal, parse_constant=invalid_constant)

    def discover(self) -> tuple[Market, ...]:
        def active_list(value):
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError("active markets must be a string array")
            return set(value)
        active, _ = self._json("markets", {}, active_list, timedelta(minutes=5))

        def details(value):
            if not isinstance(value, list):
                raise ValueError("market details must be an array")
            markets = []
            for item in value:
                fields = ("pair", "symbol", "base_currency_short_name", "target_currency_short_name", "status")
                if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key] for key in fields):
                    raise ValueError("invalid market detail fields")
                if not SYMBOL.fullmatch(item["pair"]) or not SYMBOL.fullmatch(item["symbol"]):
                    raise ValueError("invalid market symbol or pair")
                markets.append(Market(item["pair"], item["symbol"], item["base_currency_short_name"],
                                      item["target_currency_short_name"], item["status"],
                                      item["status"] == "active" and (item["symbol"] in active or item.get("coindcx_name") in active)))
            if len({market.pair for market in markets}) != len(markets):
                raise ValueError("ambiguous duplicate market pair")
            return tuple(markets)
        return self._json("details", {}, details, timedelta(minutes=5))[0]

    def history(self, pair: str, start: datetime, end: datetime, *, limit: int = 1000,
                max_pages: int = 100) -> History:
        start, end = utc(start), utc(end)
        if start >= end or start.second or start.microsecond or start.minute % 15:
            raise ValueError("start must precede end and align to a 15-minute boundary")
        if type(limit) is not int or not 1 <= limit <= 1000 or type(max_pages) is not int or max_pages < 1:
            raise ValueError("limit must be 1..1000 and max_pages must be positive")
        matches = [market for market in self.discover() if market.pair == pair]
        if len(matches) != 1 or not matches[0].active_confirmed:
            raise PublicDataError("INVALID_MARKET", "pair is not confirmed active in public market discovery")
        market = matches[0]
        cursor = epoch_ms(end) - 1
        start_ms = epoch_ms(start)
        rows, raw_pages, warnings = [], [], []
        source_order_valid = True
        for _ in range(max_pages):
            def page(value):
                if not isinstance(value, list):
                    raise ValueError("candles must be an array")
                converted = []
                for item in value:
                    if not isinstance(item, dict):
                        raise ValueError("candle must be an object")
                    stamp = milliseconds(item["time"])
                    converted.append({"timestamp": stamp.isoformat(),
                                      **{key: item[key] for key in ("open", "high", "low", "close", "volume")},
                                      "symbol": pair, "timeframe": "15m"})
                return converted
            params = {"pair": pair, "interval": "15m", "startTime": start_ms, "endTime": cursor, "limit": limit}
            records, raw = self._json("candles", params, page, timedelta(seconds=30))
            raw_pages.append(raw)
            if not records:
                break
            times = [epoch_ms(utc(row["timestamp"])) for row in records]
            source_order_valid &= all(right <= left for left, right in zip(times, times[1:]))
            if any(stamp < start_ms or stamp > cursor for stamp in times):
                warnings.append("API_RETURNED_OUTSIDE_PAGE_BOUNDS")
            rows.extend(row for row, stamp in zip(records, times) if start_ms <= stamp < epoch_ms(end))
            oldest = min(times)
            if oldest <= start_ms:
                break
            if oldest > cursor:
                raise PublicDataError("PAGINATION_STALLED", "API did not move backwards within the requested range")
            cursor = oldest - 1
        else:
            raise PublicDataError("PAGE_LIMIT_REACHED", "local pagination limit reached before history was exhausted")
        rows.sort(key=lambda row: row["timestamp"])
        return History(tuple(rows), market, tuple(raw_pages), source_order_valid, tuple(sorted(set(warnings))))
