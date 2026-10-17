import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from data.cache import ResponseCache
from data.coindcx import PublicClient
from data.schema import normalize


@unittest.skipUnless(os.environ.get('COINDCX_RUN_PUBLIC_INTEGRATION') == '1',
                     'public read-only integration disabled; set COINDCX_RUN_PUBLIC_INTEGRATION=1 to opt in')
class PublicReadOnlyIntegration(unittest.TestCase):
    def test_discovery_and_recent_candles(self):
        with tempfile.TemporaryDirectory() as cache:
            client = PublicClient(ResponseCache(cache))
            active = [market for market in client.discover() if market.active_confirmed]
            self.assertTrue(active, 'public discovery returned no active market')
            market = next((item for item in active if item.quote_currency == 'INR'), active[0])
            now = datetime.now(timezone.utc)
            end = now.replace(minute=(now.minute // 15)*15, second=0, microsecond=0)
            history = client.history(market.pair, end-timedelta(hours=1), end)
            self.assertIsInstance(history.rows, tuple)
            self.assertTrue(history.source_order_valid)
            self.assertTrue(history.rows, 'selected active market returned no recent historical candles')
            normalized = [normalize(row, market.pair) for row in history.rows]
            self.assertTrue(all(record.closed_at <= end for record in normalized))
            self.assertEqual(len({record.timestamp for record in normalized}), len(normalized))
            self.assertEqual([record.timestamp for record in normalized],
                             sorted(record.timestamp for record in normalized))
