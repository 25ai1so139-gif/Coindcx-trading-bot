"""Deterministic SYNTHETIC continuous-paper tests; never market evidence."""

import io
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event
from unittest.mock import patch

from cli import main
from config import Settings
from data.coindcx import HttpResponse, PublicClient, PublicDataError, ROUTES
from data.models import Candle
from data.schema import INTERVAL, epoch_ms
from paper_trading import session, state
from paper_trading.commands import open_account
from paper_trading.continuous import Batch, PaperLoop, PublicFeed, ShutdownRequested, status
from paper_trading.persistence import CorruptState, PersistenceError, PersistentPaperBroker, _hash
from strategies import create_strategy
from strategies.base import Direction, Signal
from tests.helpers import START, synthetic_proposal

D = Decimal
IDENTITY = {"symbol": "SYNTHETIC-INR", "data_kind": "synthetic", "allow_synthetic": True}


class SyntheticFeed:
    """Explicit fabricated OHLCV, sized exactly to each requested window."""
    def __init__(self):
        self.calls = []
        self.change = lambda batch, end: batch
        self.prices = lambda index: D(110 if index >= 299 else 100)

    def fetch(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        rows = []
        at = start
        while at < end:
            value = str(self.prices((at - START) // INTERVAL))
            rows.append(dict(timestamp=at.isoformat(), open=value, high=value, low=value, close=value,
                             volume="1000", symbol=symbol, timeframe="15m"))
            at += INTERVAL
        metadata = dict(symbol=symbol, timeframe="15m", quote_currency="INR", kind="synthetic",
                        market_status="active", source_order_valid=True, quote_volume_verified=False)
        return self.change(Batch(tuple(rows), metadata), end)


class LoopFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.settings = Settings(mode="paper", strategy="momentum", min_history_bars=200)
        self.strategy = create_strategy("momentum", lookback=2, threshold="0.01")
        self.clock = START + INTERVAL * 300
        self.account = PersistentPaperBroker.create(self.path, self.settings, **IDENTITY)
        self.feed = SyntheticFeed()
        self.loop = PaperLoop(self.account, self.strategy, feed=self.feed, now=lambda: self.clock, poll_seconds=1)
        self.loop.start()

    def reopen(self):
        return PersistentPaperBroker.open(self.path, self.settings, **IDENTITY)

    def tick(self, steps=1):
        self.advance(steps)
        return self.loop.poll()

    def advance(self, steps=1, *, account=None, owner=None):
        """Simulate the healthy worker heartbeats between 15-minute bars."""
        target = self.clock + INTERVAL * steps
        while self.clock < target:
            self.clock = min(target, self.clock + timedelta(seconds=240))
            session.heartbeat(account or self.account, owner or self.loop.owner, self.clock)

    def buy(self):
        self.loop.poll()
        self.tick()
        snapshot = self.account.snapshot()
        self.assertIsNotNone(snapshot.state["position"])
        return snapshot

    def bar(self, index, price=110, low=None):
        return Candle(START + INTERVAL * index, D(price), D(price), D(low or price), D(price), D(1000))


class CompletedCandleTests(LoopFixture):
    def test_startup_warms_history_without_replaying_entries(self):
        self.assertEqual(self.loop.poll(), "OK")
        snapshot = self.account.snapshot()
        self.assertEqual(snapshot.processed_candles, 1)
        self.assertIsNone(snapshot.state["position"])
        self.assertEqual(snapshot.state["risk"]["entries_today"], 0)

    def test_prior_signal_executes_next_open_without_lookahead(self):
        self.loop.poll()
        original = self.strategy.evaluate
        with patch.object(type(self.strategy), "evaluate", autospec=True, side_effect=lambda _, bars, **kw: original(bars, **kw)) as evaluate:
            self.tick()
        visible = evaluate.call_args.args[1]
        snapshot = self.account.snapshot()
        self.assertEqual(visible[-1].closed_at, START + INTERVAL * 300)
        self.assertEqual(snapshot.state["position"]["opened_at"], (START + INTERVAL * 300).isoformat())
        self.assertEqual(snapshot.state["position"]["entry_reference"], "110")
        record = snapshot.state["audit"][-1]
        self.assertEqual(record["signal_timestamp"], visible[-1].closed_at.isoformat())
        self.assertTrue(record["approved"])
        self.assertLessEqual(D(record["planned_risk"]), 10)

    def test_repeated_poll_has_one_processed_candle_and_one_entry(self):
        snapshot = self.buy()
        for _ in range(3):
            self.loop.poll()
        after = self.account.snapshot()
        self.assertEqual(after.state_json, snapshot.state_json)
        self.assertEqual(after.processed_candles, 2)
        self.assertEqual(after.state["risk"]["entries_today"], 1)

    def test_incomplete_candle_is_excluded(self):
        def change(batch, end):
            row = {**batch.rows[-1], "timestamp": end.isoformat(), "close": "999999", "high": "999999"}
            return replace(batch, rows=batch.rows + (row,))
        self.feed.change = change
        self.loop.poll()
        self.assertEqual(self.account.snapshot().processed_candles, 1)
        self.assertIn("INCOMPLETE_CANDLES_EXCLUDED", self.loop.last_report["warnings"])

    def test_duplicate_source_timestamp_is_blocked(self):
        self.feed.change = lambda b, _: replace(b, rows=b.rows + (b.rows[-1],))
        self.assertEqual(self.loop.poll(), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().processed_candles, 0)

    def test_missing_internal_candle_is_blocked(self):
        self.feed.change = lambda b, _: replace(b, rows=b.rows[:20] + b.rows[21:])
        self.assertEqual(self.loop.poll(), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().runtime["reason"], "MISSING_INTERVALS")

    def test_missing_leading_edge_cannot_be_hidden_by_metadata(self):
        self.feed.change = lambda b, _: replace(b, rows=b.rows[2:], metadata={**b.metadata, "requested_start": b.rows[2]["timestamp"]})
        self.assertEqual(self.loop.poll(), "DATA_BLOCKED")

    def test_stale_data_halts_processing_and_keeps_position(self):
        self.buy()
        before = self.account.snapshot().state_json
        self.feed.change = lambda b, _: replace(b, rows=b.rows[:-4])
        self.assertEqual(self.tick(), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().runtime["reason"], "STALE_DATA")
        self.assertEqual(self.account.snapshot().state_json, before)

    def test_invalid_ohlc_is_not_used_for_exits(self):
        self.buy()
        before = self.account.snapshot().state_json
        self.feed.change = lambda b, _: replace(b, rows=b.rows[:-1] + ({**b.rows[-1], "low": "10000"},))
        self.assertEqual(self.tick(), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().state_json, before)

    def test_insufficient_history_is_blocked(self):
        self.feed.change = lambda b, _: replace(b, rows=b.rows[-50:])
        self.assertEqual(self.loop.poll(), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().runtime["reason"], "INSUFFICIENT_HISTORY")

    def test_wrong_market_and_synthetic_kind_are_blocked(self):
        for change in ({"symbol": "OTHER-INR"}, {"kind": "historical"}, {"quote_currency": "USDT"}):
            with self.subTest(change=change):
                self.feed.change = lambda b, _, c=change: replace(b, metadata={**b.metadata, **c})
                self.assertEqual(self.loop.poll(), "DATA_BLOCKED")
                self.assertIsNone(self.account.snapshot().state["position"])

    def test_source_order_warning_is_blocked(self):
        self.feed.change = lambda b, _: replace(b, metadata={**b.metadata, "source_order_valid": False})
        self.assertEqual(self.loop.poll(), "DATA_BLOCKED")

    def test_zero_volume_is_blocked(self):
        self.feed.change = lambda b, _: replace(b, rows=b.rows[:-1] + ({**b.rows[-1], "volume": "0"},))
        self.assertEqual(self.loop.poll(), "DATA_BLOCKED")

    def test_correction_to_processed_candle_is_blocked(self):
        self.loop.poll()
        before = self.account.snapshot().state_json
        self.feed.prices = lambda _: D(100)
        self.assertEqual(self.tick(), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().state_json, before)

    def test_large_gap_requires_review_and_preserves_position(self):
        self.buy()
        before = self.account.snapshot().state_json
        self.assertEqual(self.tick(97), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().state_json, before)

    def test_catchup_processes_stops_but_never_opens_new_entries(self):
        self.loop.poll()
        self.advance(3)
        # Only latest could enter; this flat strategy history generates NO_TRADE.
        self.loop.poll()
        self.assertEqual(self.account.snapshot().processed_candles, 4)
        self.assertEqual(self.account.snapshot().state["risk"]["entries_today"], 0)

    def test_structured_status_has_labels_daily_pnl_and_freshness(self):
        self.buy()
        report = status(self.account, self.clock)
        self.assertEqual(report["fills"], "SIMULATED_ESTIMATES")
        self.assertEqual(report["data_kind"], "synthetic")
        self.assertFalse(report["live_trading_enabled"])
        self.assertEqual(report["orders_submitted"], 0)
        self.assertTrue(report["daily_summary_current"])
        self.assertEqual(report["equity_marked_at"], self.clock.isoformat())
        self.assertEqual(D(report["daily_marked_pnl"]), D(report["equity"]) - 2000)
        self.assertIsNotNone(report["last_successful_market_data_at"])
        self.assertEqual(status(self.account, self.clock + timedelta(hours=1))["health"], "STALE_OR_OFFLINE")
        self.assertFalse(status(self.account, self.clock + timedelta(days=1))["daily_summary_current"])


class SessionSafetyTests(LoopFixture):
    def direct(self, index, action=Signal.HOLD, price=110):
        self.advance()
        bar = self.bar(index, price)
        proposal = synthetic_proposal(self.settings, bar.timestamp, D(price)) if action == Signal.BUY else None
        if proposal is not None:
            with sqlite3.connect(self.path) as connection:
                stored = {key: state._decode(state.strict_json(value), Candle) for key, value in
                          connection.execute("SELECT candle_id,candle_json FROM processed")}
            records = tuple(stored.get(row.timestamp.isoformat(), row) for row in proposal.candles)
            last_close = records[-1].close
            proposal = replace(proposal, candles=records, decision=replace(proposal.decision,
                               entry_reference=last_close, stop_loss_reference=last_close * (1 - self.settings.stop_loss_fraction)))
        return session.process(self.account, self.loop.owner, self.clock, bar, action, entry=proposal).snapshot

    def test_three_entries_and_fourth_rejection_survive_restart(self):
        self.loop.poll()
        for index in range(300, 308, 2):
            self.direct(index, Signal.BUY)
            self.direct(index + 1, Signal.SELL)
        recovered = self.reopen().snapshot().state
        self.assertEqual(recovered["risk"]["entries_today"], 3)
        self.assertEqual(len(recovered["trades"]), 3)
        self.assertEqual(recovered["audit"][-1]["reason"], "daily_trade_limit")

    def test_daily_loss_halt_is_not_reset_by_session_takeover(self):
        # A gap through a stop may exceed planned risk; the daily halt must latch.
        self.buy()
        self.direct(301, price=50)
        before = self.reopen().snapshot()
        self.assertTrue(before.state["risk"]["daily_halted"])
        self.clock += timedelta(seconds=301)
        recovered = self.reopen()
        self.loop.owner = session.claim(recovered, self.clock)
        self.account = recovered
        self.direct(302, Signal.BUY, price=50)
        after = self.account.snapshot().state
        self.assertTrue(after["risk"]["daily_halted"])
        self.assertIsNone(after["position"])
        self.assertEqual(after["audit"][-1]["reason"], "daily_loss_limit")

    def test_drawdown_halt_survives_managed_recovery(self):
        self.path = self.path.with_name("leveraged.sqlite3")
        self.settings = replace(self.settings, leverage=3)
        self.account = PersistentPaperBroker.create(self.path, self.settings, **IDENTITY)
        self.loop = PaperLoop(self.account, self.strategy, feed=self.feed, now=lambda: self.clock, poll_seconds=1)
        self.loop.start()
        self.buy()
        self.direct(301, price=50)
        recovered = self.reopen().snapshot().state
        self.assertTrue(recovered["risk"]["daily_halted"])
        self.assertTrue(recovered["risk"]["drawdown_halted"])
        self.assertLessEqual(D(recovered["equity"]), 1900)
        self.assertIsNone(recovered["position"])

    def test_duplicate_direct_session_bar_is_noop_without_gate_review(self):
        before = self.buy()
        with patch("risk.entry.approve_entry", side_effect=AssertionError("duplicate gate call")):
            result = session.process(self.account, self.loop.owner, self.clock, self.bar(300), Signal.BUY)
        self.assertFalse(result.applied)
        self.assertEqual(result.snapshot.state_json, before.state_json)

    def test_same_timestamp_changed_bar_cannot_replace_committed_entry(self):
        before = self.buy()
        with self.assertRaises(PersistenceError):
            session.process(self.account, self.loop.owner, self.clock, self.bar(300, price=111))
        self.assertEqual(self.reopen().snapshot().state_json, before.state_json)

    def test_invalid_entry_history_cannot_bypass_session_or_gate(self):
        self.loop.poll()
        self.advance()
        proposal = synthetic_proposal(self.settings, START + INTERVAL * 300, D(110))
        proposal = replace(proposal, candles=proposal.candles[:-1])
        with self.assertRaises(PersistenceError):
            session.process(self.account, self.loop.owner, self.clock, self.bar(300), Signal.BUY, entry=proposal)
        self.assertIsNone(self.reopen().snapshot().state["position"])

    def test_lease_expired_during_fetch_never_commits_entry(self):
        self.loop.poll()
        def change(batch, end):
            self.clock += timedelta(seconds=301)
            return batch
        self.feed.change = change
        self.advance()
        with self.assertRaises(session.SessionError):
            self.loop.poll()
        self.assertEqual(self.reopen().snapshot().state["risk"]["entries_today"], 0)

    def test_stop_and_entry_serialize_across_two_connections(self):
        self.loop.poll()
        self.advance()
        other = self.reopen()
        proposal = synthetic_proposal(self.settings, START + INTERVAL * 300, D(110))
        def enter():
            try:
                session.process(self.account, self.loop.owner, self.clock, self.bar(300), Signal.BUY, entry=proposal)
            except session.SessionStopped:
                return "stopped"
            return "entered"
        with ThreadPoolExecutor(max_workers=2) as pool:
            entry = pool.submit(enter)
            stopping = pool.submit(session.stop, other, self.clock)
            entry.result(timeout=10)
            stopping.result(timeout=10)
        value = self.reopen().snapshot().state
        self.assertIsNone(value["position"])
        self.assertTrue(value["risk"]["emergency_halted"])
        self.assertLessEqual(value["risk"]["entries_today"], 1)

    def test_managed_direct_broker_entry_path_is_blocked(self):
        before = self.account.snapshot().state_json
        with self.assertRaisesRegex(PersistenceError, "SESSION_INTERFACE"):
            self.account.process_bar(self.bar(299), Signal.BUY, entry=synthetic_proposal(self.settings, START + INTERVAL * 299))
        self.assertEqual(self.reopen().snapshot().state_json, before)

    def test_managed_finish_path_is_blocked(self):
        self.loop.poll()
        with self.assertRaises(PersistenceError):
            self.account.finish(self.bar(299))

    def test_risk_gate_is_authoritative_and_rejects_missing_stop(self):
        self.loop.poll()
        self.advance()
        proposal = synthetic_proposal(self.settings, START + INTERVAL * 300, D(110))
        proposal = replace(proposal, decision=replace(proposal.decision, stop_loss_reference=None))
        session.process(self.account, self.loop.owner, self.clock, self.bar(300), Signal.BUY, entry=proposal)
        snapshot = self.account.snapshot()
        self.assertIsNone(snapshot.state["position"])
        self.assertFalse(snapshot.state["audit"][-1]["approved"])

    def test_one_open_position_rejects_repeated_signal(self):
        self.buy()
        self.tick()
        snapshot = self.account.snapshot()
        self.assertEqual(snapshot.state["risk"]["entries_today"], 1)
        self.assertFalse(snapshot.state["audit"][-1]["approved"])

    def test_short_cannot_create_position(self):
        self.loop.poll()
        self.advance()
        proposal = synthetic_proposal(self.settings, START + INTERVAL * 300, D(110))
        proposal = replace(proposal, decision=replace(proposal.decision, signal=Direction.SHORT, stop_loss_reference=D("112.20")))
        session.process(self.account, self.loop.owner, self.clock, self.bar(300), Signal.SELL, entry=proposal)
        snapshot = self.account.snapshot()
        self.assertIsNone(snapshot.state["position"])
        self.assertFalse(snapshot.state["audit"][-1]["approved"])

    def test_startup_or_catchup_direct_entry_is_forbidden(self):
        with self.assertRaises(session.SessionError):
            session.process(self.account, self.loop.owner, self.clock, self.bar(299), Signal.BUY,
                            entry=synthetic_proposal(self.settings, START + INTERVAL * 299, D(110)))
        self.assertEqual(self.reopen().snapshot().state["risk"]["entries_today"], 0)

    def test_incomplete_direct_candle_is_forbidden(self):
        with self.assertRaises(session.SessionError):
            session.process(self.account, self.loop.owner, self.clock, self.bar(300))

    def test_direct_gap_is_forbidden(self):
        self.loop.poll()
        self.advance(2)
        with self.assertRaises(session.SessionError):
            session.process(self.account, self.loop.owner, self.clock, self.bar(301))

    def test_wrong_lease_token_cannot_process(self):
        with self.assertRaises(session.SessionError):
            session.process(self.account, "wrong", self.clock, self.bar(299))

    def test_two_workers_cannot_claim_same_account(self):
        other = self.reopen()
        with self.assertRaisesRegex(session.SessionError, "ALREADY_OWNED"):
            session.claim(other, self.clock)
        self.assertEqual(self.account.snapshot().runtime["owner"], self.loop.owner)

    def test_lease_expiry_fences_old_worker_after_takeover(self):
        self.loop.poll()
        self.clock += timedelta(seconds=301)
        other = self.reopen()
        new_owner = session.claim(other, self.clock)
        self.assertNotEqual(new_owner, self.loop.owner)
        with self.assertRaises(session.SessionError):
            self.loop.poll()
        self.assertEqual(other.snapshot().runtime["owner"], new_owner)

    def test_stop_during_network_io_prevents_entry(self):
        self.loop.poll()
        def change(batch, end):
            session.stop(self.reopen(), self.clock)
            return batch
        self.feed.change = change
        with self.assertRaises(session.SessionError):
            self.tick()
        snapshot = self.reopen().snapshot()
        self.assertTrue(snapshot.state["risk"]["emergency_halted"])
        self.assertEqual(snapshot.state["risk"]["entries_today"], 0)

    def test_emergency_stop_flattens_once_and_persists(self):
        self.buy()
        stopped = session.stop(self.account, self.clock)
        session.stop(self.account, self.clock)
        recovered = self.reopen().snapshot()
        self.assertEqual(stopped.state_json, recovered.state_json)
        self.assertIsNone(recovered.state["position"])
        self.assertTrue(recovered.state["risk"]["emergency_halted"])
        self.assertEqual(len(recovered.state["trades"]), 1)
        with self.assertRaises(session.SessionError):
            session.claim(self.account, self.clock)

    def test_existing_emergency_api_also_stops_managed_session(self):
        self.buy()
        self.account.emergency_shutdown()
        snapshot = self.reopen().snapshot()
        self.assertTrue(snapshot.runtime["stop_requested"])
        self.assertTrue(snapshot.state["risk"]["emergency_halted"])

    def test_restart_recovers_open_position_and_does_not_duplicate_entry(self):
        before = self.buy()
        self.account.close()
        self.clock += timedelta(seconds=301)
        account = self.reopen()
        restarted = PaperLoop(account, self.strategy, feed=self.feed, now=lambda: self.clock, poll_seconds=1)
        restarted.start()
        restarted.poll()
        self.assertEqual(before.state_json, account.snapshot().state_json)
        self.assertEqual(account.snapshot().state["risk"]["entries_today"], 1)

    def test_actual_process_recovers_session_and_position(self):
        before = self.buy()
        code = "from paper_trading.commands import open_account; import sys,json; a=open_account(sys.argv[1]); s=a.snapshot(); print(json.dumps([s.state['position'],s.state['risk'],s.processed_candles])); a.close()"
        result = subprocess.run([sys.executable, "-c", code, str(self.path)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        position, risk, count = json.loads(result.stdout)
        self.assertEqual(position, before.state["position"])
        self.assertEqual(risk, before.state["risk"])
        self.assertEqual(count, before.processed_candles)

    def test_stop_loss_fees_slippage_and_equity_reconcile_after_restart(self):
        before = self.buy()
        self.advance()
        bar = self.bar(301, low=100)
        session.process(self.account, self.loop.owner, self.clock, bar)
        recovered = self.reopen().snapshot().state
        trade = recovered["trades"][0]
        self.assertEqual(trade["reason"], "stop_loss")
        self.assertGreater(D(trade["fees"]), 0)
        self.assertGreater(D(trade["slippage"]), 0)
        self.assertEqual(D(recovered["cash"]), 2000 + D(trade["net_pnl"]))
        self.assertEqual(recovered["cash"], recovered["equity"])
        self.assertLessEqual(D(trade["planned_stop_risk"]), 10)

    def test_commit_failure_rolls_back_session_and_account_and_poison_handle(self):
        self.loop.poll()
        before = self.account.snapshot()
        with patch.object(self.account, "_commit", side_effect=sqlite3.OperationalError("synthetic write failure")):
            with self.assertRaises(PersistenceError):
                self.tick()
        after = self.reopen().snapshot()
        self.assertEqual(after.state_json, before.state_json)
        self.assertEqual(after.runtime_json, before.runtime_json)
        with self.assertRaises(PersistenceError):
            self.loop.poll()

    def test_corrupt_runtime_rejected_instead_of_reset(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE runtime SET payload='{}'")
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_rehashed_inconsistent_stop_state_rejected(self):
        value = self.account.snapshot().runtime
        value.update(stop_requested=True, health="STOPPED", owner=None, lease_until=None)
        value["events"][-1].update(health="STOPPED")
        payload = state.canonical(value)
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE runtime SET payload=?,digest=?", (payload, _hash(payload)))
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_invalid_or_changed_strategy_config_is_rejected(self):
        with self.assertRaises(ValueError):
            session.configuration(self.settings, create_strategy("sma_cross"))
        with self.assertRaises(session.SessionError):
            session.enable(self.account, session.configuration(self.settings, self.strategy, 2), self.clock)

    def test_invalid_poll_and_excessive_warmup_parameters_are_rejected(self):
        for value in (0, 301, True, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                session.configuration(self.settings, self.strategy, value)


class PublicDataRecoveryTests(LoopFixture):
    def test_timeout_keeps_position_and_allows_later_data_recovery(self):
        self.buy()
        before = self.account.snapshot().state_json
        with patch.object(self.feed, "fetch", side_effect=TimeoutError("synthetic timeout")):
            self.assertEqual(self.tick(), "NETWORK_ERROR")
        self.assertEqual(self.account.snapshot().state_json, before)
        self.assertEqual(self.loop.poll(), "OK")
        self.assertEqual(self.account.snapshot().state["risk"]["entries_today"], 1)

    def test_rate_limit_exhaustion_fails_closed_and_recovers(self):
        with patch.object(self.feed, "fetch", side_effect=PublicDataError("RETRY_LATER", "synthetic 429", 429)):
            self.assertEqual(self.loop.poll(), "NETWORK_ERROR")
        self.assertEqual(self.account.snapshot().processed_candles, 0)
        self.assertEqual(self.loop.poll(), "OK")

    def test_retry_after_and_timeouts_are_bounded_by_existing_client(self):
        sequence = [TimeoutError(), HttpResponse(429, b"{}", {"retry-after": "2"}), HttpResponse(200, b"[]", {})]
        calls, waits = [], []
        def transport(url, timeout):
            calls.append(url)
            result = sequence.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        client = PublicClient(transport=transport, sleep=waits.append, request_interval=0, max_retry_delay=5)
        self.assertEqual(client._json("markets", {}, lambda x: x, timedelta(0))[0], [])
        self.assertEqual(len(calls), 3)
        self.assertEqual(waits, [1, 2])

    def test_excessive_retry_after_is_not_ignored(self):
        transport = unittest.mock.Mock(return_value=HttpResponse(429, b"{}", {"retry-after": "999"}))
        client = PublicClient(transport=transport, sleep=lambda _: self.fail("must not wait"), request_interval=0, max_retry_delay=5)
        with self.assertRaises(PublicDataError):
            client._json("markets", {}, lambda x: x, timedelta(0))
        self.assertEqual(transport.call_count, 1)

    def test_public_feed_calls_only_existing_public_client(self):
        class Client:
            def history(self, symbol, start, end, **kw):
                from data.coindcx import History, Market
                return History((), Market(symbol, "TESTINR", "INR", "TEST", "active", True), (), True, ())
        batch = PublicFeed(Client()).fetch("TEST-INR", START, START + INTERVAL)
        self.assertEqual(batch.metadata["kind"], "historical")
        self.assertFalse(batch.metadata["quote_volume_verified"])
        self.assertFalse(batch.metadata["quality_reviewed"])
        self.assertEqual(set(ROUTES), {"markets", "details", "candles"})

    def test_public_only_data_does_not_qualify_real_liquidity(self):
        path = self.path.with_name("historical.sqlite3")
        account = PersistentPaperBroker.create(path, self.settings, symbol="TEST-INR", data_kind="historical")
        self.feed.change = lambda b, _: replace(b, metadata={**b.metadata, "kind": "historical", "quality_reviewed": False})
        loop = PaperLoop(account, self.strategy, feed=self.feed, now=lambda: self.clock, poll_seconds=1)
        loop.start()
        self.assertEqual(loop.poll(), "NO_TRADE")
        self.advance(account=account, owner=loop.owner)
        self.assertEqual(loop.poll(), "NO_TRADE")
        saved = account.snapshot().state
        self.assertIsNone(saved["position"])
        self.assertEqual(saved["risk"]["entries_today"], 0)
        self.assertFalse(saved["audit"][-1]["approved"])
        self.assertIn("LIQUIDITY_REVIEW_REQUIRED", loop.last_report["reasons"])


class Phase8AcceptanceTests(LoopFixture):
    """SYNTHETIC adverse histories; no real liquidity or returns are inferred."""

    def zero_volume(self, batch, end):
        return replace(batch, rows=batch.rows[:-1] + ({**batch.rows[-1], "volume": "0"},))

    def test_zero_volume_repeated_and_restarted_preserves_exact_two_thousand(self):
        genesis = self.account.snapshot().state_json
        self.feed.change = self.zero_volume
        for _ in range(3):
            self.assertEqual(self.loop.poll(), "DATA_BLOCKED")
            self.assertEqual(self.account.snapshot().runtime["reason"], "ZERO_VOLUME")
        self.account.close()
        self.clock += timedelta(seconds=301)
        recovered = self.reopen()
        loop = PaperLoop(recovered, self.strategy, feed=self.feed, now=lambda: self.clock, poll_seconds=1)
        loop.start()
        self.assertEqual(loop.poll(), "DATA_BLOCKED")
        snapshot = recovered.snapshot()
        self.assertEqual(snapshot.state_json, genesis)
        self.assertEqual(snapshot.processed_candles, 0)
        self.assertEqual(snapshot.state["cash"], "2000")
        self.assertEqual(snapshot.state["equity"], "2000")
        self.assertEqual(snapshot.state["realized_pnl"], "0")
        self.assertEqual(snapshot.state["risk"]["entries_today"], 0)
        self.assertEqual(snapshot.state["trades"], [])
        self.assertIsNone(snapshot.state["position"])

    def test_timeout_recovery_to_zero_volume_is_not_successful_data_qualification(self):
        self.feed.change = self.zero_volume
        genesis = self.account.snapshot().state_json
        self.assertEqual(self.loop.poll(), "DATA_BLOCKED")
        with patch.object(self.feed, "fetch", side_effect=TimeoutError("SYNTHETIC injected fault")):
            self.assertEqual(self.loop.poll(), "NETWORK_ERROR")
        self.assertEqual(self.loop.poll(), "DATA_BLOCKED")
        snapshot = self.reopen().snapshot()
        self.assertEqual(snapshot.state_json, genesis)
        self.assertIsNone(snapshot.runtime["last_success"])
        self.assertEqual(snapshot.runtime["reason"], "ZERO_VOLUME")
        report = status(self.account, self.clock)
        self.assertIsNone(report["last_successful_market_data_at"])
        self.assertEqual(report["orders_submitted"], 0)
        self.assertFalse(report["live_trading_enabled"])

    def test_missing_interval_recovery_retains_position_without_duplicate_entry(self):
        before = self.buy()
        self.feed.change = lambda b, _: replace(b, rows=b.rows[:20] + b.rows[21:])
        self.assertEqual(self.tick(), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().state_json, before.state_json)
        self.feed.change = lambda batch, end: batch
        self.assertEqual(self.loop.poll(), "OK")
        after = self.reopen().snapshot()
        self.assertEqual(after.processed_candles, before.processed_candles + 1)
        self.assertEqual(after.state["position"], before.state["position"])
        self.assertEqual(after.state["risk"]["entries_today"], 1)
        self.loop.poll()
        self.assertEqual(self.account.snapshot().state_json, after.state_json)

    def test_duplicate_timestamp_with_stop_wick_cannot_mutate_existing_position(self):
        before = self.buy()
        def change(batch, end):
            bad = {**batch.rows[-1], "low": "1"}
            return replace(batch, rows=batch.rows[:-1] + (bad, bad))
        self.feed.change = change
        self.assertEqual(self.tick(), "DATA_BLOCKED")
        self.assertEqual(self.account.snapshot().state_json, before.state_json)
        self.assertEqual(self.reopen().snapshot().processed_candles, before.processed_candles)

    def test_emergency_during_stale_data_uses_last_known_close_and_stays_latched(self):
        before = self.buy()
        self.feed.change = lambda batch, end: replace(batch, rows=batch.rows[:-4])
        self.assertEqual(self.tick(), "DATA_BLOCKED")
        stopped = session.stop(self.account, self.clock)
        self.assertIsNone(stopped.state["position"])
        self.assertTrue(stopped.state["risk"]["emergency_halted"])
        trade = stopped.state["trades"][0]
        self.assertEqual(trade["exit_reference"], before.state["last_candle"]["close"])
        self.assertEqual(D(stopped.state["cash"]), D(2000) + D(trade["net_pnl"]))
        recovered = self.reopen()
        loop = PaperLoop(recovered, self.strategy, feed=SyntheticFeed(), now=lambda: self.clock, poll_seconds=1)
        with self.assertRaises(session.SessionError):
            loop.start()
        self.assertEqual(self.reopen().snapshot().state_json, stopped.state_json)

    def test_storage_failure_during_rejected_data_never_implicitly_recovers(self):
        self.feed.change = self.zero_volume
        self.loop.poll()
        before = self.account.snapshot()
        with patch.object(self.account, "_commit", side_effect=sqlite3.OperationalError("SYNTHETIC disk failure")):
            with self.assertRaises(PersistenceError):
                self.loop.poll()
        self.assertEqual(self.reopen().snapshot(), before)
        with patch.object(self.feed, "fetch", side_effect=AssertionError("must not fetch after poisoned storage")):
            with self.assertRaises(PersistenceError):
                self.loop.poll()


class SessionMigrationTests(LoopFixture):
    def legacy(self):
        path = self.path.with_name("phase6a-v2.sqlite3")
        account = PersistentPaperBroker.create(path, self.settings, **IDENTITY)
        bar = self.bar(299)
        account.process_bar(bar, Signal.BUY, entry=synthetic_proposal(self.settings, bar.timestamp, D(110)))
        return path, account

    def child(self, path, body, expected):
        code = """
import os,sys
from datetime import datetime
from paper_trading.commands import open_account
from paper_trading import session
from strategies import create_strategy
account=open_account(sys.argv[1])
now=datetime.fromisoformat(sys.argv[2])
""" + body
        result = subprocess.run([sys.executable, "-c", code, str(path), self.clock.isoformat()], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_v2_extension_preserves_financial_payload_chain_and_open_position(self):
        path, account = self.legacy()
        before = account.snapshot()
        session.enable(account, self.loop.config, self.clock)
        after = open_account(path).snapshot()
        self.assertEqual(before.state_json, after.state_json)
        self.assertEqual(before.checkpoint, after.checkpoint)
        self.assertEqual(after.runtime["configuration"], self.loop.config)
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_extension_failure_rolls_back_schema_and_state(self):
        path, account = self.legacy()
        before = account.snapshot()
        with patch.object(account, "_commit", side_effect=sqlite3.OperationalError("synthetic commit failure")):
            with self.assertRaises(PersistenceError):
                session.enable(account, self.loop.config, self.clock)
        self.assertEqual(open_account(path).snapshot(), before)
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_actual_process_death_during_extension_recovers_v2(self):
        path, account = self.legacy()
        before = account.snapshot()
        self.child(path, "account._commit=lambda connection:os._exit(73)\nsession.enable(account,session.configuration(account._settings,create_strategy('momentum')),now)\n", 73)
        self.assertEqual(open_account(path).snapshot(), before)

    def test_actual_process_death_before_bar_commit_leaves_no_entry_or_cursor(self):
        self.loop.poll()
        self.advance()
        before = self.account.snapshot()
        code = """
from tests.helpers import synthetic_proposal,START
from data.schema import INTERVAL
from data.models import Candle
from decimal import Decimal as D
from strategies.base import Signal
owner=account.snapshot().runtime['owner']
bar=Candle(START+INTERVAL*300,D(110),D(110),D(110),D(110),D(1000))
account._commit=lambda connection:os._exit(73)
session.process(account,owner,now,bar,Signal.BUY,entry=synthetic_proposal(account._settings,bar.timestamp,D(110)))
"""
        self.child(self.path, code, 73)
        self.assertEqual(self.reopen().snapshot(), before)

    def test_actual_process_death_after_commit_does_not_duplicate_entry(self):
        self.loop.poll()
        self.advance()
        code = """
from tests.helpers import synthetic_proposal,START
from data.schema import INTERVAL
from data.models import Candle
from decimal import Decimal as D
from strategies.base import Signal
owner=account.snapshot().runtime['owner']
bar=Candle(START+INTERVAL*300,D(110),D(110),D(110),D(110),D(1000))
commit=account._commit
def die(connection):
 commit(connection)
 os._exit(74)
account._commit=die
session.process(account,owner,now,bar,Signal.BUY,entry=synthetic_proposal(account._settings,bar.timestamp,D(110)))
"""
        self.child(self.path, code, 74)
        resumed = self.reopen()
        before = resumed.snapshot()
        duplicate = session.process(resumed, self.loop.owner, self.clock, self.bar(300), Signal.BUY)
        self.assertFalse(duplicate.applied)
        self.assertEqual(duplicate.snapshot.state_json, before.state_json)
        self.assertEqual(before.state["risk"]["entries_today"], 1)

    def test_v3_backup_contains_control_state_and_financial_state(self):
        self.buy()
        expected = self.account.snapshot()
        backup = self.path.with_name("backup.sqlite3")
        self.account.backup(backup)
        restored = open_account(backup).snapshot()
        self.assertEqual(restored, expected)


class ShutdownAndCLITests(LoopFixture):
    def test_external_stop_exits_worker_normally(self):
        self.clock += timedelta(seconds=301)
        loop = PaperLoop(self.account, self.strategy, feed=self.feed, now=lambda: self.clock, poll_seconds=1)
        def change(batch, end):
            session.stop(self.reopen(), self.clock)
            return batch
        self.feed.change = change
        loop.run()
        self.assertFalse(self.account._failed)
        self.assertTrue(self.account.snapshot().runtime["stop_requested"])

    def test_start_command_binds_defaults_and_can_be_inspected_and_stopped(self):
        path = self.path.with_name("new-historical.sqlite3")
        def run(loop):
            loop.start()
            session.stop(loop.account)
        with patch.dict(os.environ, {}, clear=True), patch.object(PaperLoop, "run", run), redirect_stdout(io.StringIO()) as output:
            result = main(["paper", "start", "--create", "--db", str(path), "--symbol", "TEST-INR", "--strategy", "momentum"])
        self.assertEqual(result, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["health"], "STOPPED")
        self.assertEqual(report["equity"], "2000")
        account = open_account(path)
        self.assertEqual(account._settings.leverage, 1)
        self.assertEqual(account.snapshot().runtime["configuration"]["parameters"]["lookback"], 12)

    def test_graceful_shutdown_persists_emergency_halt(self):
        # Use a fresh owner after simulating an expired process.
        self.clock += timedelta(seconds=301)
        loop = PaperLoop(self.account, self.strategy, feed=self.feed, now=lambda: self.clock, poll_seconds=1)
        def poll():
            loop.shutdown.set()
        with patch.object(loop, "poll", side_effect=poll):
            loop.run()
        self.assertTrue(self.reopen().snapshot().state["risk"]["emergency_halted"])
        self.assertEqual(self.reopen().snapshot().runtime["health"], "STOPPED")

    def test_ctrl_c_and_signal_handlers_are_restored(self):
        self.clock += timedelta(seconds=301)
        loop = PaperLoop(self.account, self.strategy, feed=self.feed, now=lambda: self.clock, poll_seconds=1)
        before = signal.getsignal(signal.SIGINT)
        with patch.object(loop, "poll", side_effect=KeyboardInterrupt):
            loop.run()
        self.assertEqual(signal.getsignal(signal.SIGINT), before)
        self.assertTrue(self.reopen().snapshot().runtime["stop_requested"])

    def test_shutdown_event_after_fetch_prevents_processing(self):
        self.feed.change = lambda b, _: (self.loop.shutdown.set() or b)
        with self.assertRaises(ShutdownRequested):
            self.loop.poll()
        self.assertEqual(self.account.snapshot().processed_candles, 0)

    def test_status_and_stop_cli_never_connect_to_network(self):
        self.buy()
        for action in ("status", "stop", "status"):
            with patch("socket.socket", side_effect=AssertionError("network forbidden")), patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["paper", action, "--db", str(self.path)]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["orders_submitted"], 0)
            self.assertFalse(report["live_trading_enabled"])
        self.assertTrue(report["risk"]["emergency_halted"])

    def test_missing_database_status_fails_without_creating_balance(self):
        missing = self.path.with_name("missing.sqlite3")
        with redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(main(["paper", "status", "--db", str(missing)]), 2)
        self.assertFalse(missing.exists())
        self.assertIn("BLOCKED", errors.getvalue())

    def test_start_cannot_recreate_existing_account(self):
        before = self.path.read_bytes()
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["paper", "start", "--create", "--db", str(self.path), "--symbol", "TEST-INR"]), 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_live_environment_is_rejected_for_start(self):
        with patch.dict(os.environ, {"BOT_MODE": "live"}), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["paper", "start", "--db", str(self.path)]), 2)

    def test_invalid_environment_cannot_prevent_local_emergency_stop(self):
        with patch.dict(os.environ, {"BOT_MODE": "live", "BOT_LEVERAGE": "999"}), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["paper", "stop", "--db", str(self.path)]), 0)
        report = json.loads(output.getvalue())
        self.assertTrue(report["risk"]["emergency_halted"])
        self.assertFalse(report["live_trading_enabled"])

    def test_synthetic_account_cannot_start_public_session(self):
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["paper", "start", "--db", str(self.path)]), 2)

    def test_logs_are_structured_and_do_not_include_provider_messages(self):
        with self.assertLogs("coindcx.paper", level="INFO") as logs, patch.object(self.feed, "fetch", side_effect=PublicDataError("NETWORK_FAILURE", "DO_NOT_LOG_PROVIDER_BODY")):
            self.loop.poll()
        record = json.loads(logs.records[-1].getMessage())
        self.assertEqual(record["reason"], "PUBLIC_API_ERROR")
        self.assertNotIn("DO_NOT_LOG_PROVIDER_BODY", record.values())


if __name__ == "__main__":
    unittest.main()
