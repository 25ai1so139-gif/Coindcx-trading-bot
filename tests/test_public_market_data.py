import json
import ssl
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

from data.cache import ResponseCache
from data.coindcx import HttpResponse, PublicClient, PublicDataError, unsigned_get
from data.schema import epoch_ms
from tests.market_fixtures import START, end


def reply(value, status=200, headers=None):
    return HttpResponse(status, json.dumps(value).encode(), headers or {})


ACTIVE = ["SYNTHETICINR"]
DETAILS = [{"pair": "I-SYNTHETIC_INR", "symbol": "SYNTHETICINR", "coindcx_name": "SYNTHETICINR",
            "base_currency_short_name": "INR", "target_currency_short_name": "SYNTHETIC", "status": "active"}]


def api_row(index):
    return {"time": epoch_ms(START + timedelta(minutes=15 * index)),
            "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10"}


class PublicApiTests(unittest.TestCase):
    def client(self, queue, **kwargs):
        self.urls = []
        self.delays = []
        def transport(url, timeout):
            self.urls.append(url)
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return PublicClient(transport=transport, now=lambda: end(), sleep=self.delays.append,
                            monotonic=lambda: 0, request_interval=0, **kwargs)

    def test_documented_market_discovery_has_no_private_requests(self):
        client = self.client([reply(ACTIVE), reply(DETAILS)])
        market = client.discover()[0]
        self.assertTrue(market.active_confirmed)
        self.assertEqual(market.quote_currency, "INR")
        self.assertEqual(market.asset_currency, "SYNTHETIC")
        self.assertTrue(all(url.startswith("https://api.coindcx.com/exchange/v1/markets") for url in self.urls))

    def test_market_status_and_active_list_must_agree(self):
        client = self.client([reply([]), reply(DETAILS)])
        self.assertFalse(client.discover()[0].active_confirmed)

    def test_inactive_pair_is_not_fetched(self):
        client = self.client([reply(ACTIVE), reply([{**DETAILS[0], "status": "inactive"}])])
        with self.assertRaises(PublicDataError) as caught:
            client.history("I-SYNTHETIC_INR", START, end(4))
        self.assertEqual(caught.exception.code, "INVALID_MARKET")
        self.assertEqual(len(self.urls), 2)

    def test_descending_pages_use_documented_ms_bounds_and_normalize_ascending(self):
        client = self.client([reply(ACTIVE), reply(DETAILS), reply([api_row(3), api_row(2)]),
                              reply([api_row(1), api_row(0)])])
        result = client.history("I-SYNTHETIC_INR", START, end(4), limit=2)
        self.assertEqual([row["timestamp"] for row in result.rows],
                         [(START + timedelta(minutes=15 * index)).isoformat() for index in range(4)])
        first = parse_qs(urlparse(self.urls[2]).query)
        self.assertTrue(self.urls[2].startswith('https://api.coindcx.com/market_data/candles?'))
        second = parse_qs(urlparse(self.urls[3]).query)
        self.assertEqual(first["startTime"], [str(epoch_ms(START))])
        self.assertEqual(first["endTime"], [str(epoch_ms(end(4)) - 1)])
        self.assertEqual(second["endTime"], [str(epoch_ms(end(2)) - 1)])
        self.assertEqual(first["interval"], ["15m"])
        self.assertEqual(first["limit"], ["2"])
        self.assertNotIn("quote_volume", result.rows[0])
        self.assertEqual(len(result.raw_pages), 2)

    def test_end_boundary_is_exclusive_and_original_response_is_retained(self):
        page = reply([api_row(4), api_row(3), api_row(0)])
        client = self.client([reply(ACTIVE), reply(DETAILS), page])
        history = client.history("I-SYNTHETIC_INR", START, end(4))
        self.assertEqual(len(history.rows), 2)
        self.assertEqual(history.raw_pages[0], page.body)
        self.assertIn("API_RETURNED_OUTSIDE_PAGE_BOUNDS", history.warnings)

    def test_unexpected_api_order_is_reported_after_normalization(self):
        client = self.client([reply(ACTIVE), reply(DETAILS), reply([api_row(0), api_row(1)])])
        self.assertFalse(client.history("I-SYNTHETIC_INR", START, end(2)).source_order_valid)

    def test_duplicates_remain_visible_to_quality_checks(self):
        client = self.client([reply(ACTIVE), reply(DETAILS), reply([api_row(1), api_row(0), api_row(0)])])
        result = client.history("I-SYNTHETIC_INR", START, end(2))
        self.assertEqual(len(result.rows), 3)

    def test_empty_history_stops_without_fabricating_candles(self):
        client = self.client([reply(ACTIVE), reply(DETAILS), reply([])])
        self.assertEqual(client.history("I-SYNTHETIC_INR", START, end(4)).rows, ())

    def test_nonprogressing_pagination_fails_instead_of_looping(self):
        client = self.client([reply(ACTIVE), reply(DETAILS), reply([api_row(3)]), reply([api_row(3)])])
        with self.assertRaises(PublicDataError) as caught:
            client.history("I-SYNTHETIC_INR", START, end(4))
        self.assertEqual(caught.exception.code, "PAGINATION_STALLED")

    def test_local_page_budget_is_not_reported_as_complete_history(self):
        client = self.client([reply(ACTIVE), reply(DETAILS), reply([api_row(3)])])
        with self.assertRaises(PublicDataError) as caught:
            client.history("I-SYNTHETIC_INR", START, end(4), max_pages=1)
        self.assertEqual(caught.exception.code, "PAGE_LIMIT_REACHED")

    def test_invalid_limit_or_date_range_never_makes_requests(self):
        for change in ({"limit": 1001}, {"limit": 0}, {"max_pages": 0}):
            client = self.client([])
            with self.subTest(change=change), self.assertRaises(ValueError):
                client.history("I-SYNTHETIC_INR", START, end(4), **change)
            self.assertEqual(self.urls, [])

    def test_rate_limit_retry_after_seconds_is_respected(self):
        client = self.client([reply({}, 429, {"Retry-After": "4"}), reply(ACTIVE), reply(DETAILS)])
        client.discover()
        self.assertEqual(self.delays, [4])

    def test_rate_limit_retry_after_http_date_is_respected(self):
        from email.utils import format_datetime
        header = format_datetime(end() + timedelta(seconds=7), usegmt=True)
        client = self.client([reply({}, 429, {"Retry-After": header}), reply(ACTIVE), reply(DETAILS)])
        client.discover()
        self.assertEqual(self.delays, [7])

    def test_long_retry_after_aborts_instead_of_retrying_early(self):
        client = self.client([reply({}, 429, {"Retry-After": "600"})])
        with self.assertRaises(PublicDataError) as caught:
            client.discover()
        self.assertEqual(caught.exception.code, "RETRY_LATER")
        self.assertEqual(self.delays, [])

    def test_server_failure_retries_are_bounded(self):
        client = self.client([reply({}, 503), reply({}, 500), reply({}, 503)])
        with self.assertRaises(PublicDataError):
            client.discover()
        self.assertEqual(len(self.urls), 3)
        self.assertEqual(self.delays, [1, 2])

    def test_network_timeout_can_recover(self):
        client = self.client([TimeoutError(), reply(ACTIVE), reply(DETAILS)])
        self.assertTrue(client.discover()[0].active_confirmed)
        self.assertEqual(self.delays, [1])

    def test_nonretryable_http_failures_do_not_request_credentials(self):
        for status in (400, 401, 403, 404, 302):
            client = self.client([reply({}, status)])
            with self.subTest(status=status), self.assertRaises(PublicDataError):
                client.discover()
            self.assertEqual(len(self.urls), 1)
            self.assertEqual(self.delays, [])

    def test_proxy_denial_and_tls_failure_do_not_retry_or_disable_verification(self):
        for error, code in ((URLError("Tunnel connection failed: 403 Forbidden"), "ACCESS_DENIED"),
                            (URLError(ssl.SSLCertVerificationError("untrusted")), "TLS_VERIFICATION_FAILED")):
            client = self.client([error])
            with self.assertRaises(PublicDataError) as caught:
                client.discover()
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(len(self.urls), 1)

    def test_malformed_and_error_json_is_not_retried_as_success(self):
        for body in (b'not JSON', b'{"error":"bad"}', b'[NaN]', b'[{}]'):
            client = self.client([HttpResponse(200, body, {})])
            with self.subTest(body=body), self.assertRaises(PublicDataError):
                client.discover()
            self.assertEqual(len(self.urls), 1)

    def test_transport_rejects_private_non_https_and_redirect_destinations(self):
        for url in ("https://api.coindcx.com/exchange/v1/users/balances",
                    "https://api.coindcx.com/exchange/v1/orders/create", "http://public.coindcx.com/market_data/candles",
                    "https://example.com/market_data/candles"):
            with self.subTest(url=url), patch("data.coindcx.build_opener") as opener:
                with self.assertRaises(PublicDataError):
                    unsigned_get(url, 10)
                opener.assert_not_called()

    def test_real_transport_constructs_unsigned_get_and_disallows_redirects(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.code, response.headers = 200, {}
        response.read.return_value = b'[]'
        with patch('data.coindcx.build_opener') as factory:
            factory.return_value.open.return_value = response
            result = unsigned_get('https://api.coindcx.com/exchange/v1/markets', 10)
        request = factory.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'GET')
        self.assertFalse(any(key.lower() in {'authorization', 'x-auth-apikey', 'x-auth-signature'}
                             for key in request.headers))
        handler = factory.call_args.args[0]
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'https://example.com'))
        self.assertEqual(result.body, b'[]')

    def test_transport_response_size_limit_is_enforced(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'12345'
        with patch('data.coindcx.build_opener') as factory, patch('data.coindcx.MAX_RESPONSE_BYTES', 4):
            factory.return_value.open.return_value = response
            with self.assertRaises(PublicDataError) as caught:
                unsigned_get('https://api.coindcx.com/exchange/v1/markets', 10)
        self.assertEqual(caught.exception.code, 'RESPONSE_TOO_LARGE')


class ResponseCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = ResponseCache(Path(self.temp.name))

    def test_fresh_raw_response_is_reused_and_timestamp_is_not_refreshed(self):
        self.cache.put("url", b'["data"]', START)
        result = self.cache.get("url", START + timedelta(seconds=5), timedelta(seconds=10))
        self.assertEqual(result.body, b'["data"]')
        self.assertEqual(result.fetched_at, START)

    def test_expired_or_future_cache_is_not_a_fallback(self):
        self.cache.put("url", b'[]', START)
        self.assertIsNone(self.cache.get("url", START + timedelta(seconds=10), timedelta(seconds=10)))
        self.assertIsNone(self.cache.get("url", START - timedelta(seconds=1), timedelta(seconds=10)))

    def test_corrupt_payload_is_rejected(self):
        self.cache.put("url", b'[]', START)
        path = next(Path(self.temp.name).glob('*.json'))
        value = json.loads(path.read_text())
        value["body_hex"] = b'[1]'.hex()
        path.write_text(json.dumps(value))
        self.assertIsNone(self.cache.get("url", START, timedelta(seconds=10)))

    def test_overflowing_cache_timestamp_is_rejected(self):
        self.cache.put('url', b'[]', START)
        path = next(Path(self.temp.name).glob('*.json'))
        value = json.loads(path.read_text())
        value['fetched_at'] = '9999-12-31T23:59:59-01:00'
        path.write_text(json.dumps(value))
        self.assertIsNone(self.cache.get('url', START, timedelta(seconds=10)))

    def test_client_uses_cache_without_a_second_network_call(self):
        calls = []
        def transport(url, timeout):
            calls.append(url)
            return reply(ACTIVE if url.endswith('/markets') else DETAILS)
        client = PublicClient(self.cache, transport=transport, now=lambda: START,
                              request_interval=0)
        first = client.discover()
        self.assertEqual(first, client.discover())
        self.assertEqual(len(calls), 2)

    def test_api_error_is_not_cached(self):
        client = PublicClient(self.cache, transport=lambda *_: reply({}, 400), now=lambda: START)
        with self.assertRaises(PublicDataError):
            client.discover()
        self.assertEqual(list(Path(self.temp.name).glob('*.json')), [])

    def test_expired_cache_does_not_mask_an_api_failure(self):
        self.cache.put('https://api.coindcx.com/exchange/v1/markets', json.dumps(ACTIVE).encode(), START)
        client = PublicClient(self.cache, transport=lambda *_: reply({}, 503),
                              now=lambda: START + timedelta(hours=1), sleep=lambda _: None, request_interval=0)
        with self.assertRaises(PublicDataError):
            client.discover()
