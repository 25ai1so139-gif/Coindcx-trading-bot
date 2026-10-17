# Phase 6A — durable paper accounts

Historical Phase 6A scope: Phase 6B now extends this API with explicitly managed
sessions and schema 3; see [the current paper-session guide](PHASE6B_PAPER.md).
The Phase 6A financial checkpoint format and standalone schema-2 API remain supported.

This is an explicit Python API for finite paper operations. The existing CLI
paper/backtest CSV replays remain independent, in-memory simulations. No continuous
loop, polling, service, live/private API, order transport or Phase 6B command exists.
Use PersistentPaperBroker for recoverable paper state; the old PaperBroker and
CLI paper command do not gain persistence automatically.

## Account boundary and API

All processes using one paper account must share the same local SQLite file.
One database binds one account UUID, symbol, 15m timeframe, INR, data kind, complete
Settings and trading-engine fingerprint. Multiple databases are explicitly separate
simulated accounts, not failover copies sharing capital or global position limits.
Multi-symbol portfolios and shared-equity accounts across files are unsupported.

Create once, at a new path. Later calls must open the existing file. Never implement
an "open failed -> create fresh" fallback. Settings must use paper mode, INR 2000
initial equity and the existing Phase 5 risk policy. Smaller risk limits remain
valid; defaults and the central approval function are unchanged.

Example initialization only, explicitly synthetic and submitting no orders:

~~~python
from config import Settings
from paper_trading.persistence import PersistentPaperBroker

settings = Settings(mode="paper")  # Existing defaults, including 2880 history bars.
identity = dict(symbol="SYNTHETIC-INR", data_kind="synthetic", allow_synthetic=True)
path = "paper_trading/local/example.synthetic.sqlite3"
account = PersistentPaperBroker.create(path, settings, **identity)  # Once only.
initial = account.snapshot()
account.close()  # Releases this handle; does not flatten or reset the account.

resumed = PersistentPaperBroker.open(path, settings,
                                    expected_head=initial.checkpoint, **identity)
assert resumed.snapshot().state["cash"] == "2000"
resumed.close()
~~~

APIs:

| Method | Behavior |
| --- | --- |
| create(path, settings, symbol=..., data_kind=..., allow_synthetic=...) | Exclusive creation only; existing/partial files are never overwritten |
| open(..., expected_head=None, timeout=1) | Existing-file mode only; fully validate before returning a usable handle |
| process_bar(candle, signal=Signal.HOLD, entry=None) | One atomic completed-candle operation; BUY requires the existing rich EntryProposal and Phase 5 approval |
| snapshot() | Immutable Snapshot with account checkpoint, symbol, data_kind, processed count and state_json; state returns a detached JSON dictionary |
| emergency_shutdown() | Atomically latch emergency and flatten through existing simulation logic; successful halt survives restart; repeat is a no-op |
| finish(candle) | Existing offline end-of-data close; requires the identical last processed candle |
| close() | Disable this handle; does not simulate an exit or change durable state |
| backup(new_path) | Consistent SQLite online backup; returns its Checkpoint; never overwrite a destination |
| restore_backup(source, new_path, settings, expected_head=..., identity...) | Explicit recovery to a new destination, requiring the exact independently known last committed checkpoint |
| migrate(path, settings, identity...) | Explicit, transactional schema 1 -> 2 migration; current version is a no-op |

process_bar returns Update(applied, snapshot). A previously processed candle with
numerically identical OHLCV is a no-op, regardless of a changed signal or Decimal
zero-padding. The gate is not called again. Changed OHLCV at the same opening time
raises CandleConflict. An older, never-processed candle is rejected. A normal gate
rejection still commits its audit and processed-candle ID, so retries cannot turn
that same candle into another entry. Invalid requests/exceptions roll back.

No mutable recovered broker or executable approval token is exposed. A new BUY
always follows the existing PaperBroker.process_bar -> _open -> approve_entry
path. Recovery restores an already recorded position without charging another
entry fee or incrementing the counter. All restored fills require their matching
approval history and processed entry/exit candles. New entries still require new
validated proposal/context, costs/instrument details and completed prior history.
SHORT cannot open a position. manual/verify remain read-only and submit no orders.

## SQLite schema and transaction contract

Application ID 0x43445850; PRAGMA user_version=2; state JSON format=1.
Connections use foreign_keys=ON, trusted_schema=OFF, synchronous=FULL and DELETE
rollback journaling. Other journal modes are rejected. Writer operations use
BEGIN IMMEDIATE; readers use a stable read transaction. Connections always close.
The SQLite lock serializes independent processes; no cached balance is reused.

| Table | Stored fields and purpose |
| --- | --- |
| meta | Strict key/value whitelist: account_id, symbol, data_kind, settings, engine, created_at UTC |
| checkpoints | Contiguous revision, operation(create/bar/finish/emergency), full canonical state payload, SHA-256 payload digest and chained digest |
| processed | Unique UTC candle opening identifier, canonical OHLCV and unique checkpoint revision; symbol/timeframe are bound by metadata |
| head | Exactly one row identifying the latest revision, payload digest and chain; detects missing/truncated tail or mismatched head |

Each checkpoint stores cash, marked equity, original broker realized_pnl, open
PositionPlan/entry reference/time, last candle, exposed bars, complete RiskControls,
closed trades, equity observations, activation events and whitelisted RiskRecords.
RiskControls includes UTC day/start equity, filled-entry count, daily/drawdown/
emergency latches, peak/last equity and maximum observed drawdown. Decimal amounts
are finite text; timestamps are timezone-aware UTC. No pickle, float balances,
credentials, environment dumps, raw proposal metadata or free-form signal reasons
are saved. The existing realized_pnl attribute is closed-trade net P&L; while open,
entry fees already reduce cash/equity and observation realized P&L separately.

Every operation validates SQLite integrity/schema/constraints, metadata, engine
compatibility, the entire checkpoint chain and append-only histories. It then
reconciles fills/costs/cash/equity/approval budgets, processed candles, daily entry
counts and observation-derived risk state before permitting new work. The trading
fingerprint binds the current broker/config/data/risk code bytes; schema-only
storage upgrades use schema/format versions. Unreviewed engine changes reject
resume. Source line-ending changes can also change that strict fingerprint.

A writer recovers under the SQLite lock, runs the original broker privately,
inserts the checkpoint and candle key, updates head, revalidates the new state and
commits. No successful Update is returned before commit. Rollback discards the
whole candidate. Standard Phase 5 APPROVED logs are proposal reviews, not fill
acknowledgments: a later database failure can abort them. The committed database
is the execution-history authority.

## Failures, restart and backups

Any operation error blocks that handle. Correct the input/storage problem, discard
it and explicitly reopen the existing database for complete validation; do not
create another account or retry blindly. Lock timeout and SQLite write errors do
not permit an entry. A commit acknowledgment can be lost: inspect resumed state
and retry the same candle ID, which cannot fill twice.

| Situation | Recovery behavior |
| --- | --- |
| Process dies before commit | SQLite rolls back its hot journal to the last committed state; candidate trades/counters/candle IDs disappear together |
| Process dies after commit but before acknowledgment | Resume sees that committed candle/trade; duplicate processing is a no-op |
| Corrupt/inconsistent latest history | Reject; no automatic fallback to an earlier checkpoint, no silent balance/counter/halt reset |
| Unknown schema/engine/settings/market | Reject; no automatic account recreation or engine migration |
| Backup matches independently known latest committed Checkpoint | Validate and restore to a new destination, preserving the original damaged file |
| Backup is stale or latest state cannot be established | Recovery is BLOCKED; do not manufacture missing trades/balances or assume an old backup is complete |

Use backup() rather than copying an active database or its transient journal.
Backup holds a stable SQLite read snapshot. Keep it and the latest successful
operation's Checkpoint(account_id, revision, chain) independently. A backup's old
receipt alone is not proof that it contains all later committed operations.
restore_backup requires an explicitly supplied trusted latest checkpoint, rejects
a different account/stale backup, and never overwrites an existing destination.
Do not remove a hot journal manually. Failed creation/backup files are retained
and rejected if incomplete, rather than silently deleted/reinitialized.

Receipts/hashes are integrity checks, not authentication. A fresh process cannot
detect replacement by an entirely valid older database without a trusted external
checkpoint; open(expected_head=...) checks that anchor. A live handle also pins
its last observed account/revision. If the primary is unreadable and an ambiguous
write may have committed beyond the known receipt, completeness is unknown and
backup recovery must remain blocked. No API can reconstruct missing facts.

Schema 1 is the explicitly defined unchained compatibility format, exercised on
labelled synthetic fixtures. Migration validates every old checkpoint first, adds
chain columns/digests and advances user_version in one transaction. It does not
alter payloads, balances, trades, counts or halts. Interruption rolls back DDL and
version together. This is not a claim that a deployed legacy database was migrated;
Phase 5 had no durable account to recover. Other versions/engine changes reject.

## Verification and limits

See [Phase 6A audit](PHASE6A_AUDIT.md) for exact executed commands/counts.
SQLite/Python standard library only; requirements and .env.example are unchanged.
Local database/backup/receipt directories and SQLite sidecars are excluded from Git.

Native Windows, physical power-loss/storage-controller behavior, network/shared
filesystems, multi-host ownership and real-market qualification remain UNVERIFIED.
Use a local filesystem whose SQLite locks and fsync are reliable; this is not a
distributed store. Tests kill real processes, not hardware. No encryption or
cryptographic anti-tamper mechanism is claimed. Successful committed halts survive
restart; an uncommitted/failed emergency request cannot be promised durable when
storage is unavailable. New entries remain blocked on that failed handle.

Full snapshots repeat histories; disk growth and validation cost increase with
session length. There is no retention/compaction service or long-running capacity
benchmark yet. Exhaustion fails closed; operational sizing/retention must be
reviewed before Phase 6B. OHLC gap, stop-fill, liquidity and execution-model limits
from Phase 5 remain. No real trades, profitability or continuous readiness claim.
