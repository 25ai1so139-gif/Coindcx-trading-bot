# Phase 6B continuous paper sessions

This is a completed-candle simulator, with no authenticated client, exchange order
method, live mode or short positions. It needs Python 3.12 and its standard library
only. All fill prices, fees, slippage and P&L are **simulated estimates**. Synthetic
tests are labeled and never qualify a real market.

## Timing and data contract

The default 30-second poll uses PublicClient's documented unsigned HTTPS GETs:

| Purpose | URL | Documentation |
| --- | --- | --- |
| Active names | https://api.coindcx.com/exchange/v1/markets | https://docs.coindcx.com/#markets |
| Native pairs/status | https://api.coindcx.com/exchange/v1/markets_details | https://docs.coindcx.com/#markets-details |
| OHLCV | https://api.coindcx.com/market_data/candles | https://docs.coindcx.com/#candles |

The live documentation was re-read during this phase. Current documented candle
intervals are 1m, 15m, 1h, 1d; this engine fixes 15m. Candles have open/high/low/
close/volume/time; time is opening Unix milliseconds, volume is target-asset units.
The server returns descending times. Existing pagination normalizes ascending UTC
but preserves duplicate/order/coverage defects for assessment. TLS and redirect
restrictions remain enabled. No credentials are requested or passed.

Requests cover an explicit aligned [start, end) window ending at the current UTC
15-minute boundary. The Phase 2 assessor rejects missing edges/internal intervals,
duplicates, invalid prices, out-of-order/future data, zero-volume history,
insufficient history and stale candles. Incomplete candles are excluded. The loop
also requires the latest completed bar and rejects changed processed candles.
It never pads history or creates substitute market prices.

Default history is 2,880 bars; the loop's upper configuration bound is 10,000.
The source adapter caps pagination at 12 pages. Each request times out after 10
seconds and tries at most three times for network/transient/429 failures. Backoff
is 1 then 2 seconds unless Retry-After supplies a delay within the five-second
continuous-mode budget; larger waits abort that poll. Requests retain the existing
0.5-second local spacing. This is a local policy, not a published provider quota.
Network errors block processing and retry on a later poll; data failures preserve
the last position/equity and block new entries. Long requests can expire ownership;
an expired worker exits rather than renewing ownership after the fact.

On initial startup only the latest completed candle is processed as HOLD.
Historical candles warm the indicators; they do not open historical paper entries.
For a subsequent single new completed bar, the selected SMA/momentum strategy sees
only candles that closed by that bar's opening time. Any LONG uses that following
bar's open plus adverse entry slippage, then its completed OHLC for stops/marking.
This deliberately preserves the existing next-bar simulation model: it is a
retrospectively estimated paper fill, not an assertion that an order was submitted
at a price 15 minutes earlier. The newest candle never enters its own indicator
window. Signals at the most recent close wait for the following bar to complete.

A restart/catch-up processes at most 96 consecutive missed bars for position
valuation/stops, with HOLD actions throughout multi-bar catch-up. No catch-up
entries occur. Larger gaps and unavailable intervals require operator review;
they never silently skip an open position or reset state. Data/model assumptions
remain subject to the central gate even when the newest bar is structurally clean.

## Real-market qualification remains blocked

The public candle feed does **not** supply verified quote volume, independently
reviewed liquidity or a validated execution instrument. PublicFeed explicitly
sets quote_volume_verified=false and quality_reviewed=false and does not invent an
InstrumentSpec. No CLI switch overrides those protections. With structurally valid
real data, a proposal is rejected by the central gate and health is NO_TRADE /
UNQUALIFIED_MARKET. Structurally invalid data reports DATA_BLOCKED. Fetch success
alone is not eligibility. Spot instrument qualification, if later implemented,
must preserve the existing real-spot 1x rule; the global ceiling is 3x, not a claim
that public spot candles validate leveraged trading.

Independent trustworthy liquidity/instrument evidence and its integration remain
work requiring review before real-market paper entries can be qualified. Do not
relax zero-volume, coverage or liquidity checks to make a market appear eligible.

## Atomic persistence, ownership and stopping

The existing central gate is unchanged. Settings remain ₹2,000 initial equity,
margin sizing, leverage <=3x, initial 0.5% planned risk (₹10 at ₹2,000), hard risk
ceiling ₹20, daily loss budget min(₹40, 2% of applicable daily starting equity),
three UTC-day entries, one position, no short entry, drawdown and emergency halts.
Fees and adverse slippage count in planned stop risk. A price gap can exceed that
planned loss; the simulated stop is not an exchange guarantee.

The first paper start explicitly extends a validated schema-2 account to schema 3
in one BEGIN IMMEDIATE transaction. It adds one table:

~~~sql
CREATE TABLE runtime (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    payload TEXT NOT NULL,
    digest TEXT NOT NULL
);
~~~

The canonical JSON payload contains format, bound strategy/parameters/poll period/
implementation fingerprint, owner UUID, lease_until, updated_at, entry_after,
stop_requested, health, last_success, reason and a bounded 256-event operational
history. It contains no arbitrary provider bodies, secrets or credentials. Financial
checkpoint/processed-candle tables, hashes and account identity are unchanged.
Equity, realized P&L, positions, day/counts/halts and all trade/risk audit records
stay in Phase 6A's reconciled financial checkpoints. The processed table is the
durable processing cursor, not an in-memory-only marker.

Version 2 remains supported for independent explicit-API accounts. Version 1 must
first use its existing explicit migration. Unknown, malformed, corrupted or
configuration/engine-incompatible state is rejected. No implicit reset occurs.
Session extension preserves financial payload bytes and checkpoint chains; tests
kill a real child process during extension and prove rollback to schema 2.

A worker claims a 300-second durable lease; poll_seconds must be 1..120. Every
financial update rechecks the UUID, unexpired lease and stop flag under SQLite's
writer lock, including after public fetch I/O. Financial state, processed ID and
session health commit together. An expired owner cannot write after takeover.
Direct process_bar/finish calls on managed accounts are blocked; only the session
interface can process bars, still through the original PaperBroker/approve_entry.
The existing emergency API remains available and atomically stops the session.
No caller-provided position plan is an entry permission.

paper stop and Ctrl+C/SIGTERM persist the emergency halt and simulate a single
close at the **last known completed close**, charging modeled exit costs. That
reference may be stale and is not a current executable price. stop is idempotent;
an external stop causes normal worker exit. Local status/stop validate settings
from the database, so a malformed environment cannot prevent an emergency stop.
No unhalt command or automatic balance/risk reset is provided. A stopped account
cannot resume entries. Review/reconcile it rather than deleting or recreating it.

An abrupt crash preserves any open position and all financial limits. Resume
without --create, on the same DB/settings/parameters, after the old lease expires.
No new entry occurs on the ownership-acquisition boundary. Persistence errors,
ambiguous commits, engine mismatch and storage lock failure poison the handle and
terminate the worker; it never auto-reopens or acknowledges a successful stop.
An explicit validated reopen is required to determine what actually committed.

Use Phase 6A's SQLite online backup method to a new destination; never copy a live
database file casually. Schema-3 backups include runtime state and financial
history. Existing anchored-restore restrictions remain: no fallback to older
balances or invented missing trades. A financial checkpoint receipt anchors the
financial history, not every operational heartbeat; runtime digest is corruption
detection, not an authenticated security boundary. A valid older whole-file
rollback cannot be discovered in a fresh process without trusted latest evidence.

## Commands and Windows verification

Run from the checkout. These are PowerShell instructions; native Windows is
UNVERIFIED for this revision. Set up Python 3.12:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
$markets = .\.venv\Scripts\python.exe -m cli data markets | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Public discovery failed." }
$pair = ($markets.markets | Where-Object { $_.active_confirmed -and $_.quote_currency -eq "INR" -and $_.asset_currency -eq "BTC" } | Select-Object -First 1).pair
if (-not $pair) { throw "No confirmed active BTC/INR pair." }
.\.venv\Scripts\python.exe -m cli paper start --create --db paper_trading/local/paper.sqlite3 --symbol $pair --strategy momentum --lookback 12 --threshold 0.01 --margin-amount 100 --leverage 1 --fee-rate 0.001 --slippage-rate 0.001
~~~

The rates are explicitly assumed fractions on each fill, not a verified fee tier.
SMA alternative on a **different new simulated account**:

~~~powershell
.\.venv\Scripts\python.exe -m cli paper start --create --db paper_trading/local/sma.sqlite3 --symbol $pair --strategy sma_cross --fast 5 --slow 20
~~~

Another terminal in the same checkout can run:

~~~powershell
.\.venv\Scripts\python.exe -m cli paper status --db paper_trading/local/paper.sqlite3
.\.venv\Scripts\python.exe -m cli paper stop --db paper_trading/local/paper.sqlite3
~~~

After an **abrupt crash**, not an intentional emergency stop:

~~~powershell
.\.venv\Scripts\python.exe -m cli paper start --db paper_trading/local/paper.sqlite3
~~~

The old paper --data path is still independent CSV replay. manual/verify remain
zero-order reviews. This phase does not turn CSV replay into a persistent account.

~~~powershell
.\.venv\Scripts\python.exe -c "import sys,platform,sqlite3; print(platform.platform(),sys.version,sqlite3.sqlite_version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3,12)"
if ($LASTEXITCODE -ne 0) { throw "Native Windows/Python 3.12 required for Windows evidence." }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v
if ($LASTEXITCODE -ne 0) { throw "Safety verification failed." }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Full regression failed." }
# Optional unsigned public smoke; requires network, no credentials:
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_coindcx_public -v
if ($LASTEXITCODE -ne 0) { throw "Public smoke failed; do not infer market eligibility." }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
~~~

Record actual platform/revision/counts before changing the Windows status.

## Hosting and health monitoring

Run one foreground worker per database on an always-awake host with reliable UTC
clock synchronization, outbound verified HTTPS to api.coindcx.com, sufficient disk
space and durable **local** SQLite storage. Do not use network shares, shared
cloud-sync folders or ephemeral container filesystems for the active database.
Restrict filesystem permissions, retain validated backups separately and rotate
JSON-line stderr logs. No background service or external monitor is installed.

Use a process supervisor (Windows Task Scheduler/service or a Linux service) only
after local verification and explicit operator configuration. It must preserve the
same account path and settings; it must never delete/reset a failed database,
clear halts or start competing workers. A normal stop is terminal for entries;
only abrupt-process recovery can resume an unhalted account after lease expiry.

paper status reports health/reason, owner/lease/update time, last successful safe
market-data time, last completed candle, cash/equity, open position, realized P&L,
current UTC accounting day, marked/realized daily P&L and all risk latches. Daily
P&L is null when the last accounting day is not today; it is never a fabricated
fresh balance. Marks use the recorded completed candle and may lag current time.
STALE_OR_OFFLINE is derived from expired ownership or successful data older than
30 minutes. Also alert on DATA_BLOCKED/NETWORK_ERROR/NO_TRADE, last-candle lag,
stalled processed count, open position with missing data, disk/DB errors and any
daily/drawdown/emergency halt. A database owner UUID alone is not liveness proof.

Long-duration capacity, physical power-loss, real provider outages and native
Windows have not been stress tested. The inherited full-checkpoint history grows
and recovery revalidates it; memory/disk/recovery cost increase with session length.
No retention/compaction or authenticated remote health service is implemented.
Publishing this workspace saves files; it does not keep processes running, migrate
accounts to durable hosting or establish 24/7 availability. No Phase 6C work is
included. See PHASE6B_AUDIT.md before approving further development.
