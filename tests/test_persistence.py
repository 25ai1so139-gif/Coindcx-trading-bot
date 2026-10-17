"""Deterministic SYNTHETIC account/storage tests; no exchange qualification."""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from config import Settings
from paper_trading.broker import PaperBroker
from paper_trading.persistence import (APPLICATION_ID, CandleConflict, CorruptState,
                                      IncompatibleState, PersistenceError,
                                      PersistentPaperBroker, _hash, _SCHEMA_V1)
from paper_trading import state
from risk.entry import approve_entry
from strategies.base import Signal
from tests.helpers import candle, synthetic_proposal

@contextmanager
def _sql(*args, **kwargs):
    """Commit/rollback and close every test connection, including on Windows."""
    connection = sqlite3.connect(*args, **kwargs)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


D = Decimal
IDENTITY = {"symbol": "SYNTHETIC-INR", "data_kind": "synthetic", "allow_synthetic": True}


class PersistenceFixture(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "paper.sqlite3"
        self.settings = Settings(mode="paper", min_history_bars=200)
        self.account = PersistentPaperBroker.create(self.path, self.settings, **IDENTITY)

    def reopen(self, **kwargs):
        return PersistentPaperBroker.open(self.path, self.settings, **{**IDENTITY, **kwargs})

    def buy(self, index=200, *, account=None, proposal=None):
        bar = candle(index)
        return (account or self.account).process_bar(bar, Signal.BUY,
                    entry=proposal or synthetic_proposal(self.settings, bar.timestamp))

    def corrupt(self, change, *, rehash=True):
        """Corrupt a synthetic checkpoint, optionally maintaining valid checksums."""
        with _sql(self.path) as connection:
            revision, payload = connection.execute("SELECT revision,payload FROM checkpoints ORDER BY revision DESC LIMIT 1").fetchone()
            value = state.strict_json(payload)
            change(value)
            payload = state.canonical(value)
            digest = _hash(payload) if rehash else "0" * 64
            meta = dict(connection.execute("SELECT key,value FROM meta"))
            previous = connection.execute("SELECT chain FROM checkpoints WHERE revision=?", (revision - 1,)).fetchone()
            chain = self.account._chain(meta, previous[0] if previous else "0" * 64, revision,
                        connection.execute("SELECT operation FROM checkpoints WHERE revision=?", (revision,)).fetchone()[0], digest)
            connection.execute("UPDATE checkpoints SET payload=?,digest=?,chain=? WHERE revision=?", (payload,digest,chain,revision))
            connection.execute("UPDATE head SET digest=?,chain=?", (digest,chain))

    def legacy_fixture(self):
        """Unreleased schema-1 SYNTHETIC fixture, copied without inventing state."""
        legacy = self.root / "synthetic-v1.sqlite3"
        with _sql(self.path) as current, _sql(legacy) as old:
            for sql in _SCHEMA_V1:
                old.execute(sql)
            old.execute(f"PRAGMA application_id={APPLICATION_ID}")
            old.execute("PRAGMA user_version=1")
            old.executemany("INSERT INTO meta VALUES (?,?)", current.execute("SELECT * FROM meta"))
            old.executemany("INSERT INTO checkpoints VALUES (?,?,?,?)", current.execute("SELECT revision,operation,payload,digest FROM checkpoints"))
            old.executemany("INSERT INTO processed VALUES (?,?,?)", current.execute("SELECT * FROM processed"))
            old.executemany("INSERT INTO head VALUES (?,?,?)", current.execute("SELECT singleton,revision,digest FROM head"))
        return legacy

    def child(self, body, expected):
        code = """
import json, os, sys
from config import Settings
from paper_trading.persistence import PersistentPaperBroker
from strategies.base import Signal
from tests.helpers import candle, synthetic_proposal
settings = Settings(**json.loads(sys.argv[2]))
account = PersistentPaperBroker.open(sys.argv[1], settings, symbol='SYNTHETIC-INR', data_kind='synthetic', allow_synthetic=True)
""" + body
        result = subprocess.run([sys.executable, "-c", code, str(self.path), state.canonical(self.settings)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result


class RecoveryAndAccountingTests(PersistenceFixture):
    def test_creation_and_resume_preserve_exact_genesis(self):
        snapshot = self.account.snapshot()
        self.assertEqual(snapshot.checkpoint.revision, 0)
        self.assertEqual(snapshot.state["cash"], "2000")
        self.assertEqual(snapshot.symbol,"SYNTHETIC-INR")
        self.assertEqual(snapshot.data_kind,"synthetic")
        self.assertEqual(snapshot.state_json, self.reopen().snapshot().state_json)

    def test_existing_path_is_never_reinitialized(self):
        self.buy()
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            PersistentPaperBroker.create(self.path, self.settings, **IDENTITY)
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_path_is_not_created_on_resume(self):
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(PersistenceError):
            PersistentPaperBroker.open(missing, self.settings, **IDENTITY)
        self.assertFalse(missing.exists())

    def test_empty_existing_file_is_rejected_without_schema_or_balance_reset(self):
        empty = self.root / "empty.sqlite3"
        empty.touch()
        with self.assertRaises(PersistenceError):
            PersistentPaperBroker.open(empty, self.settings, **IDENTITY)
        self.assertEqual(empty.stat().st_size, 0)

    def test_paper_mode_and_explicit_synthetic_opt_in_required(self):
        for settings, identity in ((replace(self.settings, mode="backtest"), IDENTITY),
                                   (self.settings, {**IDENTITY,"allow_synthetic":False}),
                                   (replace(self.settings, starting_capital=3000), IDENTITY)):
            with self.subTest(settings=settings, identity=identity), self.assertRaises(ValueError):
                PersistentPaperBroker.open(self.path, settings, **identity)

    def test_settings_symbol_kind_and_engine_mismatch_reject(self):
        with self.assertRaises(IncompatibleState):
            PersistentPaperBroker.open(self.path, replace(self.settings, leverage=2), **IDENTITY)
        with self.assertRaises(IncompatibleState):
            self.reopen(symbol="OTHER-INR")
        with self.assertRaises(IncompatibleState):
            self.reopen(data_kind="historical")
        with _sql(self.path) as connection:
            connection.execute("UPDATE meta SET value='incompatible-engine' WHERE key='engine'")
        with self.assertRaises(IncompatibleState):
            self.reopen()

    def test_open_position_fees_risk_and_audit_survive_real_child_restart(self):
        expected = self.buy().snapshot
        result = self.child("print(account.snapshot().state_json)\n", 0)
        self.assertEqual(result.stdout.strip(), expected.state_json)
        resumed = self.reopen().snapshot().state
        self.assertIsNotNone(resumed["position"])
        self.assertEqual(resumed["risk"]["entries_today"], 1)
        self.assertEqual(len(resumed["audit"]), 1)

    def test_accounting_matches_existing_broker_across_restart_and_exit(self):
        baseline = PaperBroker(self.settings)
        actions = ((candle(200),Signal.BUY), (candle(201,high="102",low="99",close="101"),Signal.HOLD),
                   (candle(202,open="101",high="102",low="100",close="101"),Signal.SELL),
                   (candle(203),Signal.BUY))
        for bar, action in actions:
            proposal = synthetic_proposal(self.settings, bar.timestamp, bar.open) if action == Signal.BUY else None
            baseline.process_bar(bar, action, entry=proposal)
            update = self.reopen().process_bar(bar, action, entry=proposal)
            self.assertEqual(update.snapshot.state_json, state._dump(baseline))
        resumed = self.reopen()
        result = resumed.finish(candle(203))
        baseline.finish(candle(203))
        self.assertEqual(result.snapshot.state_json, state._dump(baseline))
        self.assertEqual(len(result.snapshot.state["trades"]), 2)

    def test_returned_snapshot_cannot_mutate_durable_account(self):
        snapshot = self.buy().snapshot
        detached = snapshot.state
        detached["cash"] = "999999"
        detached["risk"]["entries_today"] = 0
        self.assertEqual(self.reopen().snapshot().state_json, snapshot.state_json)

    def test_duplicate_bar_after_restart_is_noop_without_gate_call(self):
        original = self.buy().snapshot
        with patch("risk.entry.approve_entry", side_effect=AssertionError("duplicate must not review or enter")):
            duplicate = self.buy(account=self.reopen())
        self.assertFalse(duplicate.applied)
        self.assertEqual(duplicate.snapshot, original)
        # Numeric-equivalent provider formatting is still the same candle.
        equivalent = replace(candle(200),open=D("100.0"),volume=D("1000.000"))
        self.assertFalse(self.reopen().process_bar(equivalent,Signal.BUY).applied)

    def test_duplicate_bar_with_changed_prices_is_rejected(self):
        original = self.buy().snapshot
        with self.assertRaises(CandleConflict):
            self.account.process_bar(candle(200,high="101",close="101"))
        self.assertEqual(self.reopen().snapshot(), original)

    def test_unprocessed_older_bar_is_rejected_without_money_change(self):
        original = self.buy().snapshot
        with self.assertRaises(PersistenceError):
            self.account.process_bar(candle(199))
        self.assertEqual(self.reopen().snapshot(), original)

    def test_risk_rejection_is_committed_and_gate_is_authoritative(self):
        proposal = synthetic_proposal(self.settings, candle(200).timestamp)
        proposal = replace(proposal,market=replace(proposal.market,eligible=False))
        with patch("risk.entry.approve_entry", wraps=approve_entry) as gate:
            result = self.buy(proposal=proposal)
        self.assertEqual(gate.call_count, 1)
        self.assertEqual(result.snapshot.state["cash"], "2000")
        self.assertEqual(self.reopen().snapshot().state["audit"][-1]["reason"], "MARKET_INELIGIBLE")

    def test_bare_buy_and_short_cannot_create_durable_positions(self):
        from strategies.base import Direction
        self.account.process_bar(candle(200), Signal.BUY)
        proposal = synthetic_proposal(self.settings,candle(201).timestamp)
        proposal = replace(proposal,decision=replace(proposal.decision,signal=Direction.SHORT,stop_loss_reference=D(102)))
        self.account.process_bar(candle(201), Signal.BUY, entry=proposal)
        recovered = self.reopen().snapshot().state
        self.assertIsNone(recovered["position"])
        self.assertEqual(recovered["risk"]["entries_today"], 0)
        self.assertEqual([record["reason"] for record in recovered["audit"]], ["ENTRY_PROPOSAL_REQUIRED","SHORT_ENTRY_UNSUPPORTED"])

    def test_wrong_market_context_cannot_be_persisted_as_this_account(self):
        proposal = synthetic_proposal(self.settings,candle(200).timestamp,symbol="OTHER-INR")
        with self.assertRaises(PersistenceError):
            self.buy(proposal=proposal)
        self.assertEqual(self.reopen().snapshot().checkpoint.revision, 0)

    def test_repeated_buy_still_enforces_one_open_position_after_restart(self):
        self.buy()
        self.buy(201, account=self.reopen())
        recovered = self.reopen().snapshot().state
        self.assertEqual(recovered["risk"]["entries_today"], 1)
        self.assertEqual(recovered["audit"][-1]["reason"], "one_open_position")

    def test_three_entries_and_fourth_rejection_survive_restart_then_utc_reset(self):
        for index in (200,202,204):
            self.buy(index,account=self.reopen())
            self.reopen().process_bar(candle(index+1),Signal.SELL)
        rejected = self.buy(206,account=self.reopen()).snapshot.state
        self.assertEqual(rejected["risk"]["entries_today"],3)
        self.assertEqual(rejected["audit"][-1]["reason"],"daily_trade_limit")
        reset = self.buy(300,account=self.reopen()).snapshot.state
        self.assertEqual(reset["risk"]["entries_today"],1)
        self.assertEqual(len(reset["trades"]),3)

    def test_no_credentials_or_freeform_signal_reason_enter_database(self):
        marker = "SYNTHETIC_CREDENTIAL_MUST_NOT_BE_SAVED"
        proposal = synthetic_proposal(self.settings,candle(200).timestamp)
        proposal = replace(proposal,decision=replace(proposal.decision,reason=marker))
        with patch.dict(os.environ,{"COINDCX_API_KEY":marker,"COINDCX_API_SECRET":marker}):
            self.buy(proposal=proposal)
        self.assertNotIn(marker.encode(),self.path.read_bytes())

    def test_finish_requires_exact_stored_candle_and_repeated_finish_is_noop(self):
        self.buy()
        with self.assertRaises(PersistenceError):
            self.account.finish(candle(200,high="101",close="101"))
        resumed = self.reopen()
        self.assertTrue(resumed.finish(candle(200)).applied)
        self.assertFalse(self.reopen().finish(candle(200)).applied)


class HaltPersistenceTests(PersistenceFixture):
    def leveraged(self):
        self.path = self.root / "leveraged.sqlite3"
        self.settings = replace(self.settings, leverage=3)
        self.account = PersistentPaperBroker.create(self.path,self.settings,**IDENTITY)

    def test_daily_loss_halt_and_overnight_equity_basis_survive_restart(self):
        self.leveraged()
        self.buy()
        lost = self.account.process_bar(candle(201,open="85",high="85",low="85",close="85")).snapshot
        self.assertTrue(lost.state["risk"]["daily_halted"])
        self.assertFalse(lost.state["risk"]["drawdown_halted"])
        refused = self.buy(202,account=self.reopen()).snapshot.state
        self.assertEqual(refused["audit"][-1]["reason"],"daily_loss_limit")
        reset = self.buy(300,account=self.reopen()).snapshot.state
        self.assertEqual(reset["risk"]["day_start_equity"],lost.state["equity"])
        self.assertFalse(reset["risk"]["daily_halted"])
        self.assertEqual(reset["risk"]["entries_today"],1)

    def test_drawdown_halt_persists_across_restart_and_utc_day(self):
        self.leveraged()
        self.buy()
        self.account.process_bar(candle(201,open="50",high="50",low="50",close="50"))
        refused = self.buy(300,account=self.reopen()).snapshot.state
        self.assertTrue(refused["risk"]["drawdown_halted"])
        self.assertEqual(refused["audit"][-1]["reason"],"max_drawdown")

    def test_emergency_flattening_is_durable_idempotent_and_blocks_reentry(self):
        self.buy()
        result = self.account.emergency_shutdown()
        self.assertTrue(result.snapshot.state["risk"]["emergency_halted"])
        self.assertIsNone(result.snapshot.state["position"])
        self.assertFalse(self.reopen().emergency_shutdown().applied)
        refused = self.buy(201,account=self.reopen()).snapshot.state
        self.assertEqual(refused["audit"][-1]["reason"],"emergency_shutdown")
        self.assertEqual(len(refused["trades"]),1)

    def test_emergency_before_first_candle_is_not_reset_on_restart(self):
        self.account.emergency_shutdown()
        self.assertEqual(self.buy(account=self.reopen()).snapshot.state["audit"][-1]["reason"],"emergency_shutdown")

    def test_midnight_exit_count_and_equity_reconcile(self):
        self.buy(287)
        result = self.account.emergency_shutdown().snapshot
        self.assertEqual(result.state["risk"]["day"],candle(288).timestamp.date().isoformat())
        self.assertEqual(result.state["risk"]["entries_today"],0)
        self.assertEqual(self.reopen().snapshot(),result)


class AtomicityAndConcurrencyTests(PersistenceFixture):
    def test_write_failure_rolls_back_position_and_processed_key_and_poisons_handle(self):
        original = self.account.snapshot()
        with patch.object(PersistentPaperBroker,"_commit",side_effect=sqlite3.OperationalError("synthetic disk failure")):
            with self.assertRaises(PersistenceError):
                self.buy()
        with self.assertRaises(PersistenceError):
            self.buy(201)
        self.assertEqual(self.reopen().snapshot(),original)
        self.assertTrue(self.buy(account=self.reopen()).applied)

    def test_failure_after_commit_has_one_fill_after_reopen_and_retry(self):
        def lost_ack(connection):
            connection.commit()
            raise sqlite3.OperationalError("synthetic lost acknowledgment")
        with patch.object(PersistentPaperBroker,"_commit",side_effect=lost_ack):
            with self.assertRaises(PersistenceError):
                self.buy()
        duplicate = self.buy(account=self.reopen())
        self.assertFalse(duplicate.applied)
        self.assertEqual(duplicate.snapshot.state["risk"]["entries_today"],1)

    def test_real_process_death_before_commit_recovers_last_valid_state(self):
        original = self.buy().snapshot
        self.child("""
original_connection = account._connection
def small_cache():
    wrapper = original_connection()
    wrapper.connection.execute('PRAGMA cache_size=1')
    return wrapper
account._connection = small_cache
def die_before_commit(connection):
    os._exit(73)
account._commit = die_before_commit
account.process_bar(candle(201), Signal.SELL)
""",73)
        journal = Path(str(self.path)+"-journal")
        self.assertTrue(journal.exists())
        self.assertGreater(journal.stat().st_size,0)
        self.assertEqual(self.reopen().snapshot(),original)
        self.assertTrue(self.reopen().process_bar(candle(201),Signal.SELL).applied)

    def test_real_process_death_after_commit_does_not_duplicate_exit(self):
        self.buy()
        self.child("""
def die_after_commit(connection):
    connection.commit()
    os._exit(74)
account._commit = die_after_commit
account.process_bar(candle(201), Signal.SELL)
""",74)
        duplicate = self.reopen().process_bar(candle(201),Signal.SELL)
        self.assertFalse(duplicate.applied)
        self.assertEqual(len(duplicate.snapshot.state["trades"]),1)

    def test_busy_database_fails_closed_and_no_entry_survives(self):
        with _sql(self.path,isolation_level=None) as locked:
            locked.execute("BEGIN IMMEDIATE")
            account = self.reopen(timeout=0)
            with self.assertRaises(PersistenceError):
                self.buy(account=account)
            locked.rollback()
        self.assertEqual(self.reopen().snapshot().checkpoint.revision,0)

    def test_two_independent_handles_reload_state_instead_of_lost_update(self):
        other = self.reopen()
        self.buy()
        self.buy(201,account=other)
        final = self.reopen().snapshot()
        self.assertEqual(final.state["risk"]["entries_today"],1)
        self.assertEqual(final.processed_candles,2)
        self.assertEqual(final.state["audit"][-1]["reason"],"one_open_position")

    def test_threaded_duplicate_attempts_commit_exactly_one_entry(self):
        accounts = [self.reopen(timeout=5) for _ in range(4)]
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda account:self.buy(account=account),accounts))
        self.assertEqual(sum(result.applied for result in results),1)
        self.assertEqual(self.reopen().snapshot().state["risk"]["entries_today"],1)

    def test_two_actual_processes_serialize_one_candle_and_one_entry(self):
        code = """
import sys
from config import Settings
from paper_trading.persistence import PersistentPaperBroker
from strategies.base import Signal
from tests.helpers import candle, synthetic_proposal
settings=Settings(mode='paper',min_history_bars=200)
account=PersistentPaperBroker.open(sys.argv[1],settings,symbol='SYNTHETIC-INR',data_kind='synthetic',allow_synthetic=True,timeout=5)
print('ready',flush=True)
sys.stdin.readline()
result=account.process_bar(candle(200),Signal.BUY,entry=synthetic_proposal(settings,candle(200).timestamp))
print(int(result.applied),flush=True)
"""
        children = [subprocess.Popen([sys.executable,"-c",code,str(self.path)],stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        try:
            for child in children:
                self.assertEqual(child.stdout.readline().strip(),"ready")
            for child in children:
                child.stdin.write("go\n")
                child.stdin.flush()
            results=[]
            for child in children:
                output,error=child.communicate(timeout=20)
                self.assertEqual(child.returncode,0,error)
                results.append(int(output.strip()))
            self.assertEqual(sum(results),1)
            self.assertEqual(self.reopen().snapshot().processed_candles,1)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()

    def test_logging_failure_aborts_durable_entry_and_poisons_handle(self):
        with patch("risk.audit.LOGGER.info",side_effect=RuntimeError("synthetic log failure")):
            with self.assertRaises(RuntimeError):
                self.buy()
        self.assertEqual(self.reopen().snapshot().checkpoint.revision,0)
        with self.assertRaises(PersistenceError):
            self.account.snapshot()

    def test_reentrant_callback_cannot_commit_even_if_callback_swallows_error(self):
        def nested(*args,**kwargs):
            with self.assertRaises(PersistenceError):
                self.account.process_bar(candle(201))
        with patch("risk.audit.LOGGER.info",side_effect=nested):
            with self.assertRaises(PersistenceError):
                self.buy()
        self.assertEqual(self.reopen().snapshot().checkpoint.revision,0)

    def test_closed_handle_cannot_be_used_for_an_entry(self):
        self.account.close()
        with self.assertRaises(PersistenceError):
            self.buy()


class CorruptionTests(PersistenceFixture):
    def test_incompatible_affinity_or_missing_constraints_reject_valid_looking_rows(self):
        backup=self.root/"valid.sqlite3"
        self.account.backup(backup)
        cases = (("meta","key TEXT,value TEXT NOT NULL"), ("meta","key TEXT PRIMARY KEY,value BLOB NOT NULL"),
                 ("processed","candle_id TEXT PRIMARY KEY,candle_json TEXT NOT NULL,revision INTEGER NOT NULL REFERENCES checkpoints(revision)"),
                 ("processed","candle_id TEXT PRIMARY KEY,candle_json TEXT NOT NULL,revision INTEGER NOT NULL UNIQUE"))
        for table, definition in cases:
            with self.subTest(table=table,definition=definition):
                shutil.copyfile(backup,self.path)
                with _sql(self.path) as connection:
                    connection.execute("ALTER TABLE "+table+" RENAME TO old_table")
                    connection.execute("CREATE TABLE "+table+" ("+definition+")")
                    connection.execute("INSERT INTO "+table+" SELECT * FROM old_table")
                    connection.execute("DROP TABLE old_table")
                with self.assertRaises(CorruptState):
                    self.reopen()

    def test_exit_timestamp_requires_a_processed_candle(self):
        self.buy()
        self.account.process_bar(candle(201),Signal.SELL)
        self.corrupt(lambda value:value["trades"][0].update(closed_at=candle(300).timestamp.isoformat()))
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_rehashed_approval_cannot_claim_funds_not_present_before_entry(self):
        self.buy()
        self.corrupt(lambda value:value["audit"][0].update(equity="3000"))
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_closed_trade_planned_risk_is_reconciled_to_actual_quantity_and_costs(self):
        self.buy()
        self.account.process_bar(candle(201),Signal.SELL)
        self.corrupt(lambda value:value["trades"][0].update(planned_stop_risk="0.01"))
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_checksum_mismatch_rejects_instead_of_resetting(self):
        self.buy()
        self.corrupt(lambda value:value.update(cash="9999"),rehash=False)
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_rehashed_cash_equity_realized_and_counter_corruption_reject(self):
        original=self.buy().snapshot
        backup=self.root/"valid.sqlite3"
        self.account.backup(backup)
        changes=(lambda value:value.update(cash="2000"),lambda value:value.update(equity="9999"),
                 lambda value:value.update(realized_pnl="10"),lambda value:value["risk"].update(entries_today=0),
                 lambda value:value["risk"].update(day_start_equity="9999"),
                 lambda value:value["risk"].update(entries_today=True),
                 lambda value:value["risk"].update(emergency_halted=True))
        for change in changes:
            with self.subTest(change=change):
                shutil.copyfile(backup,self.path)
                self.corrupt(change)
                with self.assertRaises(CorruptState):
                    self.reopen()
        self.assertEqual(PersistentPaperBroker.open(backup,self.settings,**IDENTITY).snapshot(),original)

    def test_rehashed_invalid_position_missing_approval_and_history_reject(self):
        self.buy()
        backup=self.root/"valid.sqlite3"
        self.account.backup(backup)
        for change in (lambda value:value["position"]["plan"].update(stop_price="0"),
                       lambda value:value["position"]["plan"].update(quantity="999"),
                       lambda value:value.update(audit=[]),lambda value:value.update(observations=[]),
                       lambda value:value.update(unexpected_secret="SYNTHETIC_ONLY")):
            with self.subTest(change=change):
                shutil.copyfile(backup,self.path)
                self.corrupt(change)
                with self.assertRaises(CorruptState):
                    self.reopen()

    def test_loss_halt_cannot_be_reset_by_rehashed_checkpoint(self):
        self.settings=replace(self.settings,leverage=3)
        self.path=self.root/"loss.sqlite3"
        self.account=PersistentPaperBroker.create(self.path,self.settings,**IDENTITY)
        self.buy()
        self.account.process_bar(candle(201,open="85",high="85",low="85",close="85"))
        self.corrupt(lambda value:value["risk"].update(daily_halted=False))
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_emergency_halt_cannot_be_removed_with_valid_checksums(self):
        self.account.emergency_shutdown()
        self.corrupt(lambda value:value["risk"].update(emergency_halted=False))
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_missing_trade_is_not_fabricated_from_balance(self):
        self.buy()
        self.account.process_bar(candle(201),Signal.SELL)
        self.corrupt(lambda value:value.update(trades=[]))
        with self.assertRaises(CorruptState):
            self.reopen()

    def test_processed_candle_or_tail_deletion_rejects(self):
        self.buy()
        backup=self.root/"valid.sqlite3"
        self.account.backup(backup)
        for sql in ("DELETE FROM processed", "DELETE FROM checkpoints WHERE revision=1",
                    "UPDATE processed SET candle_json='{}'", "DELETE FROM head"):
            with self.subTest(sql=sql):
                shutil.copyfile(backup,self.path)
                with _sql(self.path) as connection:
                    connection.execute(sql)
                with self.assertRaises(PersistenceError):
                    self.reopen()

    def test_invalid_json_duplicate_keys_nonfinite_values_and_raw_file_reject(self):
        backup=self.root/"valid.sqlite3"
        self.account.backup(backup)
        for payload in ("{",'{"cash":"2000","cash":"0"}',"NaN"):
            shutil.copyfile(backup,self.path)
            with _sql(self.path) as connection:
                connection.execute("UPDATE checkpoints SET payload=?,digest=?",(payload,_hash(payload)))
            with self.assertRaises(PersistenceError):
                self.reopen()
        self.path.write_bytes(b"not a sqlite database")
        with self.assertRaises(PersistenceError):
            self.reopen()
        self.assertEqual(self.path.read_bytes(),b"not a sqlite database")

    def test_unexpected_trigger_or_future_schema_is_rejected(self):
        with _sql(self.path) as connection:
            connection.execute("CREATE TRIGGER sqliteXunsafe AFTER INSERT ON checkpoints BEGIN DELETE FROM processed; END")
        with self.assertRaises(CorruptState):
            self.reopen()
        with _sql(self.path) as connection:
            connection.execute("DROP TRIGGER sqliteXunsafe")
            connection.execute("PRAGMA user_version=999")
        with self.assertRaises(IncompatibleState):
            self.reopen()

    def test_seen_account_cannot_be_replaced_or_rolled_back_to_an_old_backup(self):
        backup=self.root/"old.sqlite3"
        self.account.backup(backup)
        expected=self.buy().snapshot.checkpoint
        shutil.copyfile(backup,self.path)
        with self.assertRaises(CorruptState):
            self.account.snapshot()
        with self.assertRaises(CorruptState):
            self.reopen(expected_head=expected)


class BackupAndMigrationTests(PersistenceFixture):
    def test_valid_backup_recovers_exact_last_known_state_without_missing_trades(self):
        self.buy()
        self.account.process_bar(candle(201),Signal.SELL)
        expected=self.account.snapshot()
        backup=self.root/"backup.sqlite3"
        receipt=self.account.backup(backup)
        self.corrupt(lambda value:value.update(cash="9999"))
        with self.assertRaises(CorruptState):
            self.reopen()
        damaged=self.path.read_bytes()
        recovered=PersistentPaperBroker.restore_backup(backup,self.root/"recovered.sqlite3",self.settings,
                                                      expected_head=receipt,**IDENTITY)
        self.assertEqual(recovered.snapshot(),expected)
        self.assertEqual(self.path.read_bytes(),damaged)
        self.assertFalse(recovered.process_bar(candle(201),Signal.SELL).applied)

    def test_stale_backup_cannot_replace_last_known_newer_trade(self):
        backup=self.root/"old.sqlite3"
        self.account.backup(backup)
        receipt=self.buy().snapshot.checkpoint
        destination=self.root/"recovered.sqlite3"
        with self.assertRaises(CorruptState):
            PersistentPaperBroker.restore_backup(backup,destination,self.settings,expected_head=receipt,**IDENTITY)
        self.assertFalse(destination.exists())

    def test_backup_never_overwrites_existing_file(self):
        destination=self.root/"user.backup"
        destination.write_bytes(b"preserve user file")
        with self.assertRaises(PersistenceError):
            self.account.backup(destination)
        self.assertEqual(destination.read_bytes(),b"preserve user file")
        self.assertEqual(self.reopen().snapshot().checkpoint.revision,0)

    def test_restore_requires_explicit_checkpoint_and_new_destination(self):
        backup=self.root/"backup.sqlite3"
        receipt=self.account.backup(backup)
        with self.assertRaises(ValueError):
            PersistentPaperBroker.restore_backup(backup,self.root/"new.sqlite3",self.settings,expected_head=None,**IDENTITY)
        with self.assertRaises(PersistenceError):
            PersistentPaperBroker.restore_backup(backup,self.path,self.settings,expected_head=receipt,**IDENTITY)

    def test_v1_migration_preserves_every_balance_trade_halt_and_processed_key(self):
        self.buy()
        self.account.emergency_shutdown()
        original=self.account.snapshot()
        legacy=self.legacy_fixture()
        with self.assertRaises(IncompatibleState):
            PersistentPaperBroker.open(legacy,self.settings,**IDENTITY)
        migrated=PersistentPaperBroker.migrate(legacy,self.settings,**IDENTITY)
        self.assertEqual(migrated.snapshot(),original)
        self.assertFalse(migrated.process_bar(candle(200),Signal.BUY).applied)
        with _sql(legacy) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],2)

    def test_failed_migration_rolls_back_schema_version_and_all_state(self):
        self.buy()
        legacy=self.legacy_fixture()
        with patch.object(PersistentPaperBroker,"_commit",side_effect=RuntimeError("synthetic interrupted migration")):
            with self.assertRaises(RuntimeError):
                PersistentPaperBroker.migrate(legacy,self.settings,**IDENTITY)
        with _sql(legacy) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],1)
            self.assertNotIn("chain",[row[1] for row in connection.execute("PRAGMA table_info(checkpoints)")])
        code = """
import os,sys
from config import Settings
from paper_trading.persistence import PersistentPaperBroker
PersistentPaperBroker._commit=staticmethod(lambda connection:os._exit(75))
PersistentPaperBroker.migrate(sys.argv[1],Settings(mode='paper',min_history_bars=200),
    symbol='SYNTHETIC-INR',data_kind='synthetic',allow_synthetic=True)
"""
        child=subprocess.run([sys.executable,"-c",code,str(legacy)],capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,75,child.stderr)
        with _sql(legacy) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],1)
            self.assertNotIn("chain",[row[1] for row in connection.execute("PRAGMA table_info(checkpoints)")])
        recovered=PersistentPaperBroker.migrate(legacy,self.settings,**IDENTITY)
        self.assertEqual(recovered.snapshot(),self.account.snapshot())

    def test_migration_rejects_corrupted_history_instead_of_repairing_money(self):
        self.buy()
        legacy=self.legacy_fixture()
        with _sql(legacy) as connection:
            connection.execute("DELETE FROM processed")
        with self.assertRaises(PersistenceError):
            PersistentPaperBroker.migrate(legacy,self.settings,**IDENTITY)
        with _sql(legacy) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],1)

    def test_current_schema_migration_is_noop(self):
        original=self.buy().snapshot
        migrated=PersistentPaperBroker.migrate(self.path,self.settings,**IDENTITY)
        self.assertEqual(migrated.snapshot(),original)
