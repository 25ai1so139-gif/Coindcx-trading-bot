# CoinDCX trading bot — strategies and simulation

Python 3.12 foundation for **historical backtesting and paper simulation only**.
Real-money trading is disabled: the public-data client cannot authenticate or
access account/order endpoints, and there is no live mode or live-order command. No CoinDCX account or API
key is needed. Strategies are examples, with no profitability claim.

Phase 6A adds an explicit [restart-safe paper-account API](docs/PHASE6A_PERSISTENCE.md).
Phase 6B adds [continuous public-data paper sessions](docs/PHASE6B_PAPER.md) with
durable start/status/stop controls. The existing CSV paper replay stays stateless.
Real-market entries remain blocked by missing liquidity/instrument qualification;
public API connectivity alone never establishes eligibility. See the
[Phase 6B audit](docs/PHASE6B_AUDIT.md) for exact evidence and limitations.

Phase 7 adds [public instrument inspection and offline exchange readiness](docs/PHASE7_READINESS.md).
Order requests and reconciliation are tested with synthetic mocks only. Private
transport and real execution remain unavailable; [Phase 7's audit](docs/PHASE7_AUDIT.md)
does not certify exchange or Phase 8 readiness.

Phase 8's [final validation audit](docs/PHASE8_AUDIT.md) records **584 passed,
0 failed, 0 errors, 0 skipped on Linux**, a measured 60.69-second public-data run
and offline replay of its actual HTTP responses. Zero-volume history was rejected;
equity stayed ₹2,000 with zero processed candles or simulated entries. Real-market
performance, qualified fills and current native Windows execution remain
unverified. **Live readiness is BLOCKED; real execution stays disabled.**

The [Phase 8B qualification audit](docs/PHASE8B_AUDIT.md) records:
**586 passed, 0 failed, 0 errors, 0 skipped on Linux**. Four actual 2,882-candle
INR histories (BTC, ETH, SOL, DOGE) all failed zero-volume and liquidity checks.
The 63.69-second public rejection diagnostic made no signals or simulated trades
and preserved ₹2,000. Native Windows remains UNVERIFIED; historical evaluation
and eligible-data paper qualification remain BLOCKED. The report includes exact
PowerShell commands and clarifies documented spot-stream fee/cancellation fields.

[Phase 8C diagnosis](docs/PHASE8C_AUDIT.md) traces all 38 archived zero-volume
bars to explicit, flat upstream records rather than missing-value substitution.
Fresh 15m/1m comparisons reproduce the sampled zeros; genuine inactivity remains
unverified, and a separate ETH interval-volume mismatch is quarantined. New
per-record quality diagnostics retain zeros for analysis while trading checks
stay strict. **616 Linux tests passed; genuine backtests remain BLOCKED and all
four ₹100-margin sizing checks return NO_TRADE.** No live operation is enabled.

The [Phase 8D readiness audit](docs/PHASE8D_AUDIT.md) records **616 passed,
0 failed, 0 errors, 0 skipped on Linux**. Four genuine 120-day INR histories each
contain 11,520 candles with no gaps/duplicates/incomplete bars, but all fail strict
zero-volume and verified-liquidity requirements; the ETH source discrepancy also
persists. Fresh ₹100-margin checks all return NO_TRADE after quantity rounding.
Backtests/OOS remain BLOCKED; no performance is fabricated or risk limit changed.
The report includes exact observations, costs, source hashes and Windows commands.
Native Windows remains UNVERIFIED; private/live operations remain disabled.

The [Phase 8E source audit](docs/PHASE8E_AUDIT.md) records **634 passed,
0 failed, 0 errors, 0 skipped on Linux**. Fresh ETH responses agree on OHLC but
retain a 0.001239 ETH interval-volume difference already present upstream; no
local resampling or supported source repair was found. A separate diagnostic
completion-check defect was fixed, with 18 new synthetic regressions. New
read-only OHLCV tracing and offline replay preserve original values and quarantine
known mismatches. All four fresh 120-day histories and ₹100-margin configurations
remain ineligible/NO_TRADE. The audit documents minimum qualification evidence;
no liquidity, backtest, Windows or live-readiness claim is inferred.

The [Phase 8F evaluation audit](docs/PHASE8F_AUDIT.md) records **634 passed,
0 failed, 0 errors, 0 skipped on Linux**, with exact [trading rules](docs/PHASE8F_RULES.md)
recorded before tests. Actual stored histories verify 11,520 candles per symbol;
all eight SMA/momentum symbol preflights remain BLOCKED by source/zero-volume/
liquidity exclusions. No strategy signals, backtests, OOS returns or benchmarks
were manufactured. The report includes period quality counts and original public
replay inputs. All existing application code, tests and risk limits are preserved;
live trading stays disabled and current native Windows remains UNVERIFIED.

The [Phase 8G archive audit](docs/PHASE8G_AUDIT.md) independently checks
the original ZIP, reproduces ETH's 0.001239 ETH volume difference and verifies all
46,080 raw/normalized records. No local implementation defect is proven; provider
aggregation semantics remain UNVERIFIED. An unchanged-value ETH quarantine copy
stays ineligible through validation and re-import. All four symbols remain
BLOCKED for historical evaluation, with no performance experiment executed.
**634 Linux tests passed, 0 failed, 0 errors, 0 skipped.** Original evidence,
strategies and risk limits are preserved; native Windows remains UNVERIFIED.

The [Phase 8H semantics audit](docs/PHASE8H_AUDIT.md) checks the current
official public documentation and independently retains ETH quarantine. The
0.001239 ETH difference is reproducible arithmetic; a provider-contract violation
is UNVERIFIED because common trade coverage and revision/aggregation rules are
undocumented. Fresh public constraints and completed-candle snapshots still give
NO_TRADE for all four symbols at unchanged ₹100 margin/1x. Historical eligibility
remains BLOCKED. **634 Linux tests passed, 0 failed, 0 errors, 0 skipped.** No
application code, strategy, risk rule or original dataset changed; live trading
stays disabled and native Windows remains UNVERIFIED.

The latest [Phase 8I Windows/feasibility audit](docs/PHASE8I_AUDIT.md) records
**634 Linux tests passed, 0 failed, 0 errors, 0 skipped**. Native Windows was
not available and remains UNVERIFIED; exact PowerShell commands use this
checkout's `Coindcx-trading-bot` directory and Python 3.12. Original Phase 8H
sizes reproduce exactly, and new public snapshots still return NO_TRADE: after
quantity-step rounding no compliant minimum order fits the unchanged ₹100 margin
ceiling at 1x. No limit was raised; ETH data and all quarantines are preserved.

## Project layout

```text
config.py               Validated settings and BOT_* environment overrides
cli.py                  backtest, paper, verify/manual, and strategies commands
data/                   Public data client, raw cache, normalization, quality, CSVs
strategies/             Validated LONG/SHORT/NO_TRADE decisions and manual review
backtesting/            Closed-candle historical replay and result accounting
paper_trading/          Simulated fills plus explicit transactional SQLite accounts
exchange/               Public constraints, offline requests and mock reconciliation
risk/                   Shared entry review, account snapshots, margin/stops/halts
tests/                  Standard-library unittest suite
tools/                  Synthetic generator and bounded public-data audit runner
requirements.txt        No third-party packages required
.env.example            Variable names only; no values or credentials
```

## Windows setup (PowerShell)

Install Python 3.12 with the Windows Python launcher. From the parent directory
of your existing checkout, run the following (skip Set-Location if already in
the repository root). The Windows absolute parent path depends on your machine;
the actual checkout directory name is `Coindcx-trading-bot`.

```powershell
Set-Location -LiteralPath '.\Coindcx-trading-bot'
py -3.12 -c "import platform, sys; print(platform.platform(), sys.version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3, 12)"
if ($LASTEXITCODE -ne 0) { throw "Native Windows and Python 3.12 are required" }
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed" }
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency check failed" }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
```

Using the virtual environment's Python directly avoids activation and PowerShell
execution-policy changes. SQLite is included with Python; no external database
service, API credentials or third-party dependencies are needed. On Linux/macOS,
use `python3.12` to create the environment and `.venv/bin/python` for the following
commands.

These Windows instructions have not been executed for the current source.
Default discovery skips the opt-in public integration test; see the
[Phase 8I audit](docs/PHASE8I_AUDIT.md) for the separate public-enabled command
and exact measured Linux counts. Linux/WSL success does not establish Windows PASS.

## Try the commands with synthetic data

Generate 3,072 deterministic demo candles, clearly labeled as synthetic. This is
only a wiring check; it is not a market backtest. The generator refuses to
overwrite an existing CSV or sidecar; reuse the existing sample on later runs.

```powershell
.\.venv\Scripts\python.exe -m tools.generate_sample_data
.\.venv\Scripts\python.exe -m cli strategies
.\.venv\Scripts\python.exe -m cli backtest --data data/local/sample.csv --strategy sma_cross --margin-amount 100 --leverage 1 --allow-synthetic
.\.venv\Scripts\python.exe -m cli paper --data data/local/sample.csv --strategy momentum --margin-amount 100 --leverage 3 --allow-synthetic
.\.venv\Scripts\python.exe -m cli verify --data data/local/sample.csv --strategy sma_cross --allow-synthetic
.\.venv\Scripts\python.exe -m cli manual --data data/local/sample.csv --strategy momentum --allow-synthetic
```

`paper --data` replays a local dataset through simulated orders. Each invocation
starts a fresh account; that CSV replay does not persist balances or risk lockouts.
`paper start/status/stop --db ...` instead uses the durable continuous worker
described above. It polls public data and retains its existing quality blocks.
Results are printed as JSON; local datasets and `reports/` are Git-ignored.

`verify` and its `manual` alias check data eligibility/freshness and print
LONG, SHORT or NO_TRADE analytical evidence. **They submit zero orders, including
paper orders.** They now require a supplied, recent simulated-account snapshot
before returning a LONG entry review; they never assume a fresh account. Missing,
stale, ineligible or risk-blocked inputs return NO_TRADE. The historical sample
commands above normally return NO_TRADE because they omit an explicit evaluation
time/account context. See the Phase 3 commands below for a labelled offline example.

For reviewed historical data, use the same commands with your CSV and omit
`--allow-synthetic`. See [data/README.md](data/README.md) for the required format
and provenance review. No historical market dataset is bundled; public downloads
occur only through explicit data commands.

## Defaults and risk rules

| Setting | Default | Meaning |
| --- | --- | --- |
| Starting capital | ₹2,000 | Simulated INR equity |
| Amount type | `margin` | `--margin-amount` is collateral, never notional |
| Requested margin | ₹100 | A ceiling; sizing can reduce it |
| Leverage | 1x | Configurable up to a hard maximum of 3x |
| Timeframe | 15 minutes | Other intervals rejected in this version |
| Risk per trade | 0.5% of equity (₹10 initially) | Planned loss including modeled costs, with a hard ₹20 ceiling |
| Stop distance | 2% of entry fill | Always active, including the entry candle |
| Maximum margin | 25% of equity | One long position at a time |
| Daily loss limit | Lower of 2% or ₹40 | Net equity loss; blocks entries until next UTC day |
| Maximum daily trades | 3 entries | Counts winners and stopped positions; resets at UTC midnight |
| Maximum drawdown | 5% from peak equity | Exits and latches for the rest of that simulation |
| Fee rate | 0.1% per fill | Illustrative, charged on entry and exit notional |
| Slippage | 0.1% per fill | Illustrative; increases buys and decreases sells |
| Minimum history | 2,880 bars | 30 days of continuous completed 15-minute candles |

For example, a requested ₹100 margin at 3x permits up to ₹300 notional before the
risk, margin, and affordability caps reduce it. Entry fees are paid separately
from reserved margin. Decimal arithmetic is used, with quantity rounded down to
eight decimal places. Reports serialize monetary numbers as decimal strings.

The ₹10–₹20 policy describes maximum planned budgets, never a minimum loss or a
minimum position size. Actual planned risk can be smaller. Sizing uses the lower
of the equity percentage, the ₹20 hard ceiling, and the remaining daily/drawdown
budget. Daily net loss is measured against that UTC day's starting equity, so
profits can offset losses within the day. The third entry can remain open and
exit normally; a fourth entry is blocked. The trade cap does not force liquidation.

Signals use completed candles and fill at the **next candle's open**. There is no
fill for the final candle's new signal. A new entry is rejected if its next-open
reference is already at or below the analytical stop. Stops use candle lows; a gap below a stop
fills at the worse open, followed by adverse slippage. The stricter of the
position stop and account loss limit triggers an exit. OHLC observations use the
UTC day of the candle's opening time. Remaining positions are closed at the last
close, including exit costs. Fees and slippage reduce equity and affect lockouts;
account exit triggers reserve both modeled exit costs before reaching the limit.

Handled Ctrl+C during replay requests an emergency shutdown: new entries latch
off, the simulated position is closed once at the last available candle close
with fees/slippage, and partial JSON results return exit status 130 with
`interrupted: true`. Strategy errors also request cleanup before propagating as
errors. This is best-effort, in-memory simulation cleanup. Forced process kills,
power loss, a second interrupt, or interruption between account mutations cannot
be guaranteed safe or recoverable. It is not an exchange emergency-stop service.

Loss thresholds are triggers, not guaranteed loss caps: gaps, fees, and slippage
can exceed them. Drawdown observes bar opens, lows, and closes, not tick-level
paths. No shorts, liquidation engine, funding/borrowing charges, taxes, partial
fills or order-book liquidity are modeled. Exchange quantity steps/minimums are
enforced only when reviewed instrument metadata is explicitly supplied; the
synthetic eight-decimal rule is an abstract fixture assumption.
Do not treat leveraged results as an exchange-exact derivatives simulation. The
fee/slippage defaults are assumptions, not verified CoinDCX charges.

## Configuration and strategies

Defaults live in `Settings` in `config.py`. Supported OS environment variables
match the field names with a `BOT_` prefix. For example:

```powershell
$env:BOT_MODE = "paper"
$env:BOT_STRATEGY = "momentum"
$env:BOT_MARGIN_AMOUNT = "100"
$env:BOT_LEVERAGE = "2"
$env:BOT_FEE_RATE = "0.001"
$env:BOT_SLIPPAGE_RATE = "0.001"
```

CLI strategy, margin, and leverage options override those settings. The `paper`
and `backtest` commands select their respective simulation mode. An invalid
environment setting such as `BOT_MODE=live` fails before any command runs. To
restore a default in PowerShell, use `Remove-Item Env:BOT_LEVERAGE` (substitute
the variable name).

`.env.example` lists variable names only. It is not automatically loaded; do not
export its blank values. An explicitly empty variable is rejected. Credentials
are not required and must never be committed or added to these settings.

Settings reject nonfinite numbers, nonpositive capital/margin, unsupported
currencies or timeframes, notional amount mode, invalid fractions, risk per trade
above the daily limit, and a daily limit above maximum drawdown. History can be
increased or explicitly lowered, with a hard floor of 200 bars; lowering it weakens
the data gate. Leverage cannot exceed 3x even if `BOT_MAX_LEVERAGE` is changed.

`BOT_MAX_PLANNED_RISK` defaults to `20`, `BOT_DAILY_LOSS_AMOUNT` to `40`, and
`BOT_MAX_TRADES_PER_DAY` to `3`. These ceilings may be tightened but cannot be
raised through settings. Existing percentage controls can make limits stricter.
Starting capital still accepts other positive values for independent simulations;
this project retains the requested ₹2,000 default. All daily counters and halts
are scoped to one simulation account and do not survive restarting the program.

Available strategies are `sma_cross` (5/20-bar crossing, configurable with
`--fast`/`--slow`) and `momentum` (12-bar, 1% threshold, configurable with
`--lookback`/`--threshold`). Add a class implementing `strategies.base.Strategy`
and register it in `strategies/__init__.py`. Both produce LONG/SHORT/NO_TRADE
analytical decisions. The preserved simulator is long-only: a SHORT decision maps
to the original SELL action, closing a long without opening a short. Manual entry
review rejects SHORT with NO_TRADE / SHORT_ENTRY_UNSUPPORTED.

## Validation

Run the complete automated suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover settings, the 3x ceiling, margin versus notional, risk-budget sizing,
fee/slippage accounting, intrabar and gap stops, account loss exits, UTC daily
lockouts, persistent drawdown lockouts, data integrity/eligibility, strategies,
next-open execution, simulation commands, and zero-order manual verification.
Phase 1 added tests for absolute INR caps, daily entry counts, emergency cleanup,
network-free commands, and Git secret-file exclusions. Git must be installed
for the repository-hygiene tests.
The run record is in [VALIDATION.md](VALIDATION.md). No historical performance
has been established. The complete 81-test suite passed on Linux/Python 3.12.14
and on native Windows Server 2022/Python 3.12.10 through GitHub Actions. The
Windows CI run is linked below; manual installation through the Windows Python
launcher has not been tested end-to-end on a personal computer.

The Phase 1 audit and its limitations are recorded in [PHASE1_AUDIT.md](PHASE1_AUDIT.md).

## Native Windows CI verification

[.github/workflows/windows-phase1.yml](.github/workflows/windows-phase1.yml)
runs a native Windows Server 2022 / Python 3.12 job on GitHub Actions. It
asserts `sys.platform == 'win32'`, requires the complete Phase 1 suite (at least
81 tests), installs requirements with package downloads disabled, and runs the
same full unittest command. The workflow has read-only repository permissions,
does not persist checkout credentials, and needs no CoinDCX keys or connection.

The job starts when the complete project and workflow are pushed to the
`phase1-windows-verification` branch. It also supports **Actions → Phase 1 - native
Windows verification → Run workflow** once the workflow exists on the default
branch. Inspect the job's actual unittest counts before recording Windows as
passed. A workflow file alone is not evidence of successful Windows execution.
WSL/Linux test results do not validate native Windows execution.

Verified native Windows result: **81 passed, 0 failures, 0 errors, 0 skipped**
for source commit `6f96dfc76a9e5d80c1f9b55601577a798df2df16` in
[GitHub Actions run 39011498680](https://github.com/25ai1so139-gif/Coindcx-trading-bot/actions/runs/39011498680).
The public job step named `Test result: Windows / Python 3.12.10 / Ran 81 tests
in 0.574s / OK / exit 0` exposes the actual runner outcome without requiring
access to detailed logs. This is the historical Phase 1 result; live trading remains disabled.

## Phase 2 — public data pipeline

Phase 2 adds public market discovery, bounded historical candle retrieval, raw
response caching, normalized CSV export, and deterministic eligibility reports.
Phase 2 retained the Phase 1 risk limits. Phase 3 extends the strategy and
verification interfaces below while preserving those limits. Live trading
remains disabled.

The official API contract and limitations are recorded in
[docs/COINDCX_API.md](docs/COINDCX_API.md), using CoinDCX's official documentation
source and current deployed documentation. Phase 3 Gate 0 reached the current
site and passed unsigned discovery/recent-candle integration after aligning the
candle URL to `https://api.coindcx.com/market_data/candles`. Historical range
queries are documented, but
retention, actual market coverage, and current numeric rate quotas are not guaranteed.

```text
Public market discovery → unsigned GET candle pages → raw response cache
                                                       ↓
CSV + sidecar → UTC/Decimal normalization → quality/eligibility report
                                                       ↓
                     raw evidence + normalized CSV + new unapproved sidecar
                                                       ↓
                  operator provenance review → strict Phase 1 loader → simulation
```

`CandleRecord` includes `timestamp,open,high,low,close,volume,symbol,timeframe`.
`quote_volume` is optional and must be separately attested when used as reliable
quote turnover. A data report's `eligible` means it meets the selected data policy;
it is not order authorization or automatic provenance approval.

### Offline sample import and inspection (PowerShell)

Use the Windows setup above; no dependencies were added. Run these from the
repository root. Reuse existing generated files on a later run or choose a new
output filename; the tools refuse to overwrite data.

```powershell
.\.venv\Scripts\python.exe -m tools.generate_sample_data --output data/local/phase2-sample.csv
.\.venv\Scripts\python.exe -m cli data import --input data/local/phase2-sample.csv --output data/local/phase2-normalized.csv --as-of "2024-02-02T00:00:00Z"
.\.venv\Scripts\python.exe -m cli data validate --input data/local/phase2-normalized.csv --as-of "2024-02-02T00:00:00Z"
```

The sample is synthetic. With the default strict policy, import/validate return
**exit 2** and `LIQUIDITY_REVIEW_REQUIRED`: its 3,072 continuous candles are not
evidence of real quote liquidity. Files are still exported for inspection.
[The actual synthetic report](docs/examples/eligibility.synthetic.json) is bundled.
`--as-of` explicitly evaluates this historical fixture at its endpoint; it does
not claim that January 2024 candles are fresh today. Omit `--as-of` to test
freshness against the current UTC time.

For synthetic/research inspection only, an explicit policy may leave liquidity
unassessed. This retains the warning and makes no real-market suitability claim:

```powershell
.\.venv\Scripts\python.exe -m cli data import --input data/local/phase2-sample.csv --output data/local/phase2-research.csv --policy data/research-policy.example.json --as-of "2024-02-02T00:00:00Z"
.\.venv\Scripts\python.exe -m cli verify --data data/local/phase2-research.csv --allow-synthetic
```

The last command submits zero orders. See [data/README.md](data/README.md) for
real CSV metadata and review requirements. Do not relabel synthetic files.

### Public historical fetch (PowerShell; network access required)

Discovery returns native pairs and their quote currencies; this example selects
an active INR market rather than assuming that a particular ticker is listed:

```powershell
$discovery = .\.venv\Scripts\python.exe -m cli data markets | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Public discovery failed; inspect the JSON error." }
$market = $discovery.markets | Where-Object { $_.active_confirmed -and $_.quote_currency -eq "INR" } | Select-Object -First 1
if (-not $market) { throw "No active INR market was returned. USDT cannot be relabeled as INR." }
$clock = [DateTimeOffset]::UtcNow
$end = [DateTimeOffset]::new($clock.Year, $clock.Month, $clock.Day, $clock.Hour, ($clock.Minute - ($clock.Minute % 15)), 0, [TimeSpan]::Zero)
$startIso = $end.AddDays(-30).ToString("o")
$endIso = $end.ToString("o")
.\.venv\Scripts\python.exe -m cli data fetch --pair $market.pair --start $startIso --end $endIso --output data/local/public-history.csv
```

The default report can return exit 2 for insufficient coverage, missing intervals,
unverified quote liquidity, or other exclusions. That is not a successful
eligibility result. Inspect the `.report.json`, raw evidence, and sidecar. A
public API's asset-volume field is not verified quote turnover; no production
liquidity threshold is invented. Fetch evaluates a historical window relative
to the earlier of its requested end and the current time. All API requests are
unsigned public GETs; no API keys are accepted or requested.

### Policy, review, and test commands

[data/policy.example.json](data/policy.example.json) lists the validated defaults:
2,880 bars, 100% completeness, at most 30 minutes stale relative to the evaluation
time, zero tolerance for zero-volume bars, and verified liquidity required.
Choose `min_quote_volume_per_bar` only with supporting quote-denominated data and
a documented rationale; it is unset by default. Setting an arbitrary positive
number does not prove market liquidity. The default fails closed until that
review can be supported. Each export resets `quality_reviewed` to false.

Legacy six-column CSVs remain compatible with the original Phase 1 review and
strict structural checks; re-import them to opt into the version-2 ingestion
policy. Version-2 files must pass ingestion, manual provenance review for
historical data, and a fresh quality recheck in the loader. Relaxing a report's
completeness/volume rules does not weaken the backtester's gap-free, positive-volume
requirements. Raw USDT data remains ineligible for the INR simulator without a
separate verified conversion. Newly listed coins use the same rules as established
coins; too little history produces `INSUFFICIENT_HISTORY`.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The historical Phase 2 final audit on Linux/Python 3.12.14 reported **150 passed, 0 failures, 0 errors,
1 skipped** out of 151 discovered tests. The skip is the separate opt-in public
integration test. An additional explicit integration attempt produced **0 passed,
0 failures, 1 error, 0 skipped** because the proxy denied CONNECT with HTTP 403;
live verification was then **BLOCKED**. See [that audit](docs/PHASE2_AUDIT.md).
Phase 3 Gate 0 subsequently resolved connectivity and rechecked the current
documentation; the newer result supersedes that connectivity status.
All unit HTTP responses, clocks/delays, and retry scenarios are
mocked or fixed fixtures. The earlier 81-test native Windows result applies to
Phase 1; Phase 2 has not been run on Windows yet.

Optional **read-only** integration, disabled by default:

```powershell
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_coindcx_public -v
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION
```

This explicitly contacts public discovery/candles only. Runtime access was
successful during Phase 3 Gate 0; it may still fail with network/server errors.
No private endpoint or strategy optimization was introduced.

## Phase 3 — validated strategy engine

[Interface, parameters, snapshot schema and limitations](docs/PHASE3_STRATEGIES.md)
and [executed verification results](docs/PHASE3_VALIDATION.md) describe this phase.
No Phase 4 work has started.

Strategies reject unordered/gapped/duplicate, incomplete, future or malformed
candles before computing indicators. The signal timestamp is the latest candle's
close; a replay executes its decision at the next candle's open. Entry/stop
references are proposals, not guaranteed fills. Verified LONG previews use the
existing fee/slippage-aware position plan and its adjusted stop.

From the repository root in Windows PowerShell:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

Generate a new labelled synthetic sample once, or reuse that exact existing
file. The generator refuses to overwrite:

~~~powershell
.\.venv\Scripts\python.exe -m tools.generate_sample_data --output data/local/phase3-sample.csv
.\.venv\Scripts\python.exe -m cli backtest --data data/local/phase3-sample.csv --strategy sma_cross --fast 5 --slow 20 --margin-amount 100 --leverage 1 --allow-synthetic
.\.venv\Scripts\python.exe -m cli paper --data data/local/phase3-sample.csv --strategy momentum --lookback 12 --threshold 0.01 --margin-amount 100 --leverage 3 --allow-synthetic
.\.venv\Scripts\python.exe -m cli manual --data data/local/phase3-sample.csv --symbol SYNTHETIC-INR --timeframe 15m --strategy momentum --lookback 12 --threshold 0.01 --as-of "2024-02-02T00:00:00Z" --risk-state docs/examples/phase3-account.synthetic.json --allow-synthetic
.\.venv\Scripts\python.exe -m cli verify --data data/local/phase3-sample.csv --symbol SYNTHETIC-INR --timeframe 15m --strategy sma_cross --fast 5 --slow 20 --as-of "2024-02-02T00:00:00Z" --risk-state docs/examples/phase3-account.synthetic.json --allow-synthetic
~~~

The account JSON is fabricated and labelled for this historical synthetic example
only. Never use it as an actual account record or relabel it as a paper account.
For reviewed real data, omit `--allow-synthetic` and `--as-of` to check freshness
now, supply a current actual simulated-account snapshot with kind `paper`, and
retain strict liquidity/provenance gates. Legacy files also undergo Phase 2
quality checks in manual verification.

A completed review returns exit 0 even when its verdict is NO_TRADE; inspect
`signal`, `entry_candidate`, `reasons`, `candidate` and `risk_preview`. Invalid
configuration/strategy parameters return exit 2; manual configuration failures
also print NO_TRADE with zero orders. Invalid command syntax returns argparse
exit 2. `--as-of` is an explicit historical clock, never a claim of freshness now.

Snapshots are read-only operator attestations. They must include all counters
and halt latches and be no more than 30 minutes old (or the stricter dataset
policy) in the same UTC day. Verification uses a copy of the existing RiskControls
and the shared entry review; it never increments entries, clears latches, resets
the day or persists an account. Repeating a review is idempotent. Existing paper
replays still start independent simulated accounts.

Final strategy audit on Linux/Python 3.12.14: **205 passed, 0 failures, 0 errors,
1 skipped** from 206 discovered tests. The skip is the optional public
integration check. The final complete run with `COINDCX_RUN_PUBLIC_INTEGRATION=1`
passed **206 tests, 0 failures, 0 errors, 0 skipped**. See the
[final audit](docs/PHASE3_AUDIT.md) for exact commands, fixes and remaining limits.
The audit added validation of returned strategy decisions and refuses stops whose
protective distance disappears at Decimal precision; no numeric risk limits or
strategy thresholds changed. No Phase 3 native Windows run has been performed. The earlier Windows
result applies to the original Phase 1 tests only.

## Phase 4 — chronological backtesting and reproducible reports

The existing replay/broker now records cost reconciliation, realized/unrealized
equity samples, margin versus notional exposure and risk activations. The new
`evaluate` command runs fixed SMA or momentum parameters on separate chronological
train, validation and test periods. It writes JSON, metrics/trades/equity/risk CSVs
and Markdown. [Phase 4 design](docs/PHASE4_BACKTESTING.md) explains metrics,
boundary rules, assumptions and configuration; [the audit](docs/PHASE4_AUDIT.md)
records actual tests, changed files and blockers.

**Real-market evaluation is BLOCKED:** no local real dataset has qualified
history/liquidity evidence. Public candles contain asset volume, not verified
quote turnover. Synthetic examples below test software only. They are not
evidence of returns, win rates or out-of-sample market performance.

Backtest and paper commands now apply strict Phase 2 quality/liquidity assessment
even to legacy reviewed historical files. A research policy cannot bypass real
liquidity verification. Historical freshness uses the recorded dataset-end cutoff
or `--data-as-of`; it does not claim freshness now. The old loader API remains
compatible. No numerical risk limits or SMA/momentum defaults changed.

Exact PowerShell setup/tests, from this working tree (Git and Python 3.12 required):

~~~powershell
Set-Location C:\path\to\Coindcx-trading-bot
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }
~~~

The following fresh-file smoke example uses 11,520 **synthetic** 15-minute bars:
30 days of warm-up, then three 30-day periods. Both dataset creation and report
export refuse existing destinations; choose new paths for additional runs.

~~~powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from tools.generate_sample_data import generate; generate(Path('data/local/phase4-synthetic.csv'), 11520)"
.\.venv\Scripts\python.exe -m cli evaluate --data data/local/phase4-synthetic.csv --strategy sma_cross --fast 5 --slow 20 --margin-amount 100 --leverage 1 --fee-rate 0.001 --slippage-rate 0.001 --plan docs/examples/phase4-splits.synthetic.json --sensitivity docs/examples/phase4-sma-sensitivity.synthetic.json --output reports/phase4-sma-synthetic-final --allow-synthetic
if ($LASTEXITCODE -ne 0) { throw "Synthetic SMA evaluation failed." }
.\.venv\Scripts\python.exe -m cli evaluate --data data/local/phase4-synthetic.csv --strategy momentum --lookback 12 --threshold 0.01 --margin-amount 100 --leverage 1 --fee-rate 0.001 --slippage-rate 0.001 --plan docs/examples/phase4-splits.synthetic.json --output reports/phase4-momentum-synthetic-final --allow-synthetic
if ($LASTEXITCODE -ne 0) { throw "Synthetic momentum evaluation failed." }
~~~

Costs above are explicitly unverified assumptions: 0.1% fee and 0.1% adverse
slippage on each entry and exit. The default stress scenario doubles both.
`--stress-multiplier` can change that scenario; invalid rates fail validation.
Spread, funding, partial fills, taxes, borrow costs, liquidation and exchange
quantity rules are not modeled without supporting evidence. Leverage represents
abstract simulated collateral, not a verified CoinDCX product.

`evaluate` requires starting capital ₹2,000; existing independent `backtest`/`paper`
settings remain configurable. All numerical Phase 1 ceilings remain unchanged:
3x leverage, initial ₹10 risk budget, ₹20 hard per-trade ceiling, ₹40 daily limit,
three entries per UTC day and one open long. Short signals only exit longs;
manual/verify still submit zero orders. No live command or private client exists.

Final Linux/Python 3.12.14 verification: **269 passed, 0 failed, 0 errors, 0 skipped**
with public integration enabled. Default discovery: **268 passed, 0 failed,
0 errors, 1 optional public-integration skip**. This is not native Windows
execution; the PowerShell commands above have not been run on Windows for Phase 4.
Phase 5 has not been started.

## Phase 5 remediation — mandatory central entry approval

The current [remediation report](docs/PHASE5_REMEDIATION.md) supersedes the earlier
"central risk gate missing" finding. `risk.entry.approve_entry` now receives the
signal, completed history, market eligibility, instrument/cost assumptions and
current account state. It rechecks the calculated plan and logs approval or
rejection before the broker can change a position. Replay, paper replay and
manual/verify use this same function. No Phase 6 loop or commands were added.

**Behavior changes explained during remediation:** entries now require initial
capital ₹2,000, risk percentage at most 0.5% (₹10 initially, capped at ₹20 as equity
grows) and daily percentage at most 2% with the existing ₹40 ceiling. Larger
legacy configuration overrides may still be parsed or used in pure calculations,
but receive no entry permission. Smaller limits remain supported. Strategy
algorithms, numeric defaults and existing halt/reset rules were preserved.

Direct `PaperBroker.process_bar(..., Signal.BUY)` without an `EntryProposal` now
records a rejection. A proposal must include a validated decision, sufficient
completed prior candles, the matching MarketContext and the actual entry
reference. `_open` cannot fill outside processing the current validated candle,
and constructing a PositionPlan is never permission to enter. The position
property is read-only; in-process calls are serialized. This protects supported
APIs, not arbitrary code that edits private fields or replaces Python functions.

Historical data requires reviewed eligibility/liquidity plus explicit instrument
and cost metadata. Missing evidence produces NO_TRADE/rejected entries. Only 1x
reviewed spot instruments are supported for historical entry approval; real
margin/funding/liquidation is unimplemented. Synthetic fixtures explicitly use an
abstract model up to 3x and are never evidence of real execution or profitability.

Results now include `risk_decisions`. Chronological report exports additionally
write `risk_decisions.csv`. Records include UTC time, reason, symbol/strategy,
analytical and modeled stop references, planned/permitted risk, margin/notional,
leverage, estimated costs and daily account state. Unavailable values are null.
The standard logger is `coindcx.risk` (INFO); records also remain in returned JSON
and report CSV regardless of a configured logging handler. Durable account/log
recovery, cross-process coordination and continuous operation remain Phase 6 work.

The [Phase 5 final audit](docs/PHASE5_REMEDIATION.md) additionally blocks nested
candle processing from logging callbacks and rejects instrument lot calculations
that cannot be represented safely. Audit `leverage` is notional divided by margin;
`effective_leverage` is proposed notional divided by current account equity before
entry costs, or null when unavailable. The default quantity step remains 0.00000001;
serialized Decimal values need not retain trailing zeros. Restart recovery, current
native Windows execution and real-market qualification remain unverified. No
Phase 6 functionality is included.
Empty risk-audit CSV exports also retain unique column names and the full schema.

## Phase 6A — restart-safe paper state

Use paper_trading.persistence.PersistentPaperBroker for explicit create/open,
one-candle operations, snapshots, emergency shutdown, backup and recovery. It
reuses the existing broker and mandatory Phase 5 risk gate. SQLite commits cash,
equity, positions, histories, candle IDs, UTC counts and halt state together;
duplicate candles cannot create another entry after restart. Errors block the
handle until explicit validated reopen. No balance-reset fallback exists.

See the [storage/API guide](docs/PHASE6A_PERSISTENCE.md) and
[Phase 6A audit](docs/PHASE6A_AUDIT.md) for schema, recovery limits and evidence.
The original CSV paper/backtest CLI commands still start independent simulations.
This Phase 6A section describes the explicit storage API; Phase 6B commands are
documented below. No credentials/dependencies
are required. Use the ignored paper_trading/local/ directory for local accounts,
backups and checkpoint receipts. Never recreate an account when resume fails.

Windows PowerShell verification from the repository root (instructions only):

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest tests.test_persistence -v
if ($LASTEXITCODE -ne 0) { throw "Persistence verification failed." }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Regression verification failed." }
~~~

Actual persistence/restart/concurrency tests ran on Linux. Native Windows and
real-market qualification remain unverified. Phase 6B evidence follows.

## Phase 6B — continuous paper sessions

From PowerShell at the repository root, discover a currently active INR pair:

~~~powershell
$markets = .\.venv\Scripts\python.exe -m cli data markets | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Public discovery failed." }
$pair = ($markets.markets | Where-Object { $_.active_confirmed -and $_.quote_currency -eq "INR" -and $_.asset_currency -eq "BTC" } | Select-Object -First 1).pair
if (-not $pair) { throw "No confirmed active BTC/INR pair; do not invent one." }
.\.venv\Scripts\python.exe -m cli paper start --create --db paper_trading/local/paper.sqlite3 --symbol $pair --strategy momentum --lookback 12 --threshold 0.01 --margin-amount 100 --leverage 1 --fee-rate 0.001 --slippage-rate 0.001
~~~

This runs in the foreground. The rates are declared modeling assumptions.
In another terminal in the same checkout, inspect or stop that simulated account:

~~~powershell
.\.venv\Scripts\python.exe -m cli paper status --db paper_trading/local/paper.sqlite3
.\.venv\Scripts\python.exe -m cli paper stop --db paper_trading/local/paper.sqlite3
~~~

Ctrl+C also stops. A successful stop persistently latches the emergency halt and
simulates closing any position at its last known completed close, with modeled
exit costs. That price may be stale. There is no unhalt command or automatic reset.
After an abrupt crash, resume the same non-emergency-halted account without
--create; an old ownership lease must expire (up to 300 seconds):

~~~powershell
.\.venv\Scripts\python.exe -m cli paper start --db paper_trading/local/paper.sqlite3
~~~

Resume preserves stored settings and strategy parameters. Startup and catch-up
never open positions. Only completed 15-minute candles are processed. All proposed
entries pass the central gate; shorts/live orders remain disabled. The current
public feed cannot supply verified quote turnover or reviewed instrument details,
so it reports NO_TRADE or DATA_BLOCKED rather than inventing qualification.

Local Windows verification (not a claim of Windows execution here):

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v
if ($LASTEXITCODE -ne 0) { throw "Paper/risk/persistence verification failed." }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Full regression failed." }
~~~

Keep the host awake and the database on durable local storage. Monitor session
heartbeat, lease, health, last successful data time, accounting day and position;
retain logs and validated backups. Publication does not keep a worker running or
establish 24/7 availability. See the [operating guide](docs/PHASE6B_PAPER.md) for
failure/recovery behavior and hosting requirements. Phase 6C is not implemented.

Exact local PowerShell verification, from this checkout:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest tests.test_central_risk -v
if ($LASTEXITCODE -ne 0) { throw "Central risk tests failed." }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Regression tests failed." }
~~~

These are Windows instructions, not native Windows execution evidence. Actual
remediation tests ran on Linux/Python 3.12.14; exact totals and public-integration
commands are in the report. Real-market eligibility/execution evidence remains
unqualified. This historical Phase 5 note predates the Phase 6 and Phase 7 work.

## Phase 7 — offline exchange readiness

Public metadata inspection reuses the existing unsigned client. Order construction,
secret-handling and durable reconciliation are tested with synthetic mocks only.
No private network transport, real-order command or live/short mode is available.

PowerShell commands from this checkout, using a pair confirmed by discovery:

~~~powershell
$markets = .\.venv\Scripts\python.exe -m cli data markets | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Public discovery failed." }
$pair = ($markets.markets | Where-Object { $_.active_confirmed -and $_.quote_currency -eq "INR" -and $_.asset_currency -eq "BTC" } | Select-Object -First 1).pair
if (-not $pair) { throw "No confirmed active BTC/INR pair." }
.\.venv\Scripts\python.exe -m cli exchange instrument --pair $pair
if ($LASTEXITCODE -ne 0) { throw "Instrument metadata unavailable." }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest tests.test_exchange_adapter tests.test_order_reconciliation tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v
if ($LASTEXITCODE -ne 0) { throw "Safety verification failed." }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Full regression failed." }
~~~

PUBLIC_METADATA_ONLY is not market qualification. Real-market entries remain
blocked; actual auth/permissions, server precision and fee-currency semantics,
partial-cancellation resolution and native Windows remain unverified. No keys
are needed for the public commands/tests. Do not put keys in chat or Git.

The [Phase 7 guide](docs/PHASE7_READINESS.md) documents the interfaces, official
sources, conservative mock model, exact native Windows verification, durable
unknown-request safeguards and Phase 8 prerequisites. See the
[audit](docs/PHASE7_AUDIT.md) for all changed files and final test counts. No Phase 8
work, service deployment or 24/7 availability is claimed.
