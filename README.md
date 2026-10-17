# CoinDCX trading bot foundation

Python 3.12 foundation for **offline historical backtesting and paper simulation only**.
Real-money trading is disabled: there is no exchange client, credential handling,
network order transport, live mode, or live-order command. No CoinDCX account or API
key is needed. Strategies are examples, with no profitability claim.

## Project layout

```text
config.py               Validated settings and BOT_* environment overrides
cli.py                  backtest, paper, verify/manual, and strategies commands
data/                   Candle validation, reviewed CSV loading, local datasets
strategies/             SMA crossover, momentum, and the strategy registry
backtesting/            Closed-candle historical replay and result accounting
paper_trading/          Simulated positions, fills, fees, and trade records
risk/                   Margin sizing, gap-aware stops, daily loss/drawdown limits
tests/                  Standard-library unittest suite
tools/                  Explicitly synthetic smoke-check data generator
requirements.txt        No third-party packages required
.env.example            Variable names only; no values or credentials
```

## Windows setup (PowerShell)

Install Python 3.12 with the Windows Python launcher, then run from this checkout:

```powershell
cd Coindcx-trading-bot
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Using the virtual environment's Python directly avoids activation and PowerShell
execution-policy changes. There are no services, database, API credentials, or
third-party dependencies to configure. On Linux/macOS, use `python3.12` to create
the environment and `.venv/bin/python` for the following commands.

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

`paper` replays a local dataset through simulated orders. Each invocation starts a
fresh account; balances and risk lockouts are not persisted between runs. There is
no real-time price feed or unattended trading service in this initial version.
Results are printed as JSON; local datasets and `reports/` are Git-ignored.

`verify` and its `manual` alias evaluate the latest completed candle and print the
signal, dataset eligibility, and a sizing preview. **They submit zero orders,
including paper orders.** The preview assumes a fresh account, not an existing
portfolio, and is not permission to trade. It can print a preview even for HOLD or
SELL; `entry_candidate` distinguishes a BUY signal.

For reviewed historical data, use the same commands with your CSV and omit
`--allow-synthetic`. See [data/README.md](data/README.md) for the required format
and provenance review. No historical market dataset is bundled or downloaded.

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
fill for the final candle's new signal. Stops use candle lows; a gap below a stop
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
fills, order-book liquidity, or exchange lot-size/minimum-order rules are modeled.
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

Available strategies are `sma_cross` (5/20-bar crossing) and `momentum` (12-bar,
1% threshold). Add a class implementing `strategies.base.Strategy` and register
it in `strategies/__init__.py` to expose it by command. Both strategies are
long-only: SELL closes a position, never opens a short.

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
access to detailed logs. Phase 2 has not started, and live trading remains disabled.
