# Phase 8I — native Windows verification and order feasibility

17 October 2026. **Native Windows remains UNVERIFIED; snapshot order action
NO_TRADE; historical qualification remains BLOCKED.** Only Linux is attached.
The complete public-enabled suite passed **634 tests, 0 failures, 0 errors,
0 skipped** there. No Windows tests were executed and no Windows pass/fail/error/
skip counts are available. Linux, WSL, command availability or old CI results
cannot establish current native Windows PASS.

Inspected Phase 8H's report, actual source, original archived inputs and public
constraint evidence before changes. All application/config/test/risk code is
preserved. Initial simulated capital INR 2000, requested margin INR 100, default
1x/maximum 3x, 15m, initial planned-risk budget INR 10/hard cap INR 20, daily
lower of INR 40 or 2% of daily starting equity, three entries/UTC day, one long
and emergency/drawdown controls are unchanged. Live and short entries remain
disabled. No account was created/reset, private request, credential or real
order used, worker started, trading parameter tuned or Phase 9 begun.

## Status matrix

| Requirement | Status | Evidence / scope |
| --- | --- | --- |
| Actual environment and supported Python identified | PASS | `/workspace/Coindcx-trading-bot`, Linux 6.18.55 x86_64/glibc 2.41, CPython 3.12.14, SQLite 3.53.1; `.python-version` pins 3.12 |
| Native Windows execution | UNVERIFIED | No native Windows environment/runner exposed; Windows counts unavailable, not zero |
| Native Windows commands | Provided; execution UNVERIFIED | Exact existing directory name and Python 3.12 commands below, including a win32 guard |
| Full available Linux tests | PASS | Final 634 passed, 0 failed, 0 errors, 0 skipped; baseline and focused counts below |
| Documented/public instrument representation | PASS | Current official sections and six public GETs captured; does not certify server acceptance or fills |
| Explain/reproduce Phase 8H size rejection | PASS | All four saved size records reproduced exactly; independent rational arithmetic agrees |
| Feasible order at unchanged snapshot settings | BLOCKED | No compliant lot fits INR 100 margin at 1x in either snapshot; all four NO_TRADE |
| Preserve original ETH and other quarantines | PASS | Original ZIP/85 source files and existing quarantine bytes/flags preserved; guarded eligibility checks reject all four |
| ETH target-asset volume units | PASS for documented units | Source defines target currency; for I-ETH_INR this is ETH, not INR turnover |
| ETH aggregation/revision/zero-activity semantics | UNVERIFIED | Documentation unchanged; numerical difference cannot prove a provider-contract violation; quarantine retained |
| Risk/live safeguards | PASS for preservation and offline regressions | Existing source fingerprints and complete regression suite unchanged/passing; no live execution claim |
| Historical backtest / executable liquidity | BLOCKED | Unqualified source/zero-volume/liquidity evidence remains; no experiment or performance result |

## 1. Native Windows: actual availability and local commands

The available execution environment reports `sys.platform=linux`. It has no
`py`, `pwsh`, `powershell`, `cmd.exe` or `wine` executable, and no tool exposes a
native Windows runner. PowerShell on Linux or Wine would not prove native
Windows compatibility anyway. The repository's existing
`.github/workflows/windows-phase1.yml` is historical configuration; it was not
dispatched or republished. Its older Phase 1 result is not current-suite evidence.

The Windows absolute checkout location is unknown; no `C:\...` path is invented.
The actual directory is **Coindcx-trading-bot**, Python **3.12**. Start PowerShell
in the parent folder of your existing checkout. Skip the first command if
already in that checkout's root. No clone, credential or activation command is
needed. These are instructions, **not commands executed on Windows here**.

```powershell
Set-Location -LiteralPath '.\Coindcx-trading-bot'
if (!(Test-Path -LiteralPath '.\config.py') -or !(Test-Path -LiteralPath '.\tests')) {
    throw "Run from the existing Coindcx-trading-bot repository root"
}
py -3.12 -c "import platform, sys; print(platform.platform(), sys.version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3, 12)"
if ($LASTEXITCODE -ne 0) { throw "Native Windows and Python 3.12 are required" }
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed" }
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency check failed" }
.\.venv\Scripts\python.exe -c "import sys, sqlite3; print(sys.platform, sys.version, sqlite3.sqlite_version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3, 12)"
if ($LASTEXITCODE -ne 0) { throw "Virtual environment is not native Windows Python 3.12" }

$phase8iPreviousPublic = [Environment]::GetEnvironmentVariable('COINDCX_RUN_PUBLIC_INTEGRATION', 'Process')
try {
    $env:COINDCX_RUN_PUBLIC_INTEGRATION = '0'
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Offline tests failed" }
} finally {
    [Environment]::SetEnvironmentVariable('COINDCX_RUN_PUBLIC_INTEGRATION', $phase8iPreviousPublic, 'Process')
}
```

There are no third-party dependencies. The default run intentionally skips its
one opt-in public integration test. Record actual native output; do not assume
Linux counts or outcomes. To additionally execute that read-only public test,
run full discovery again with public network access:

```powershell
$phase8iPreviousPublic = [Environment]::GetEnvironmentVariable('COINDCX_RUN_PUBLIC_INTEGRATION', 'Process')
try {
    $env:COINDCX_RUN_PUBLIC_INTEGRATION = '1'
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Public-enabled tests failed" }
} finally {
    [Environment]::SetEnvironmentVariable('COINDCX_RUN_PUBLIC_INTEGRATION', $phase8iPreviousPublic, 'Process')
}
```

Neither run enables live trading or requires private keys. Native Windows
verification remains outstanding until actual execution evidence is available.

## 2. Public sources and reproducible observations

Official [market details](https://docs.coindcx.com/#markets-details) and
[candles](https://docs.coindcx.com/#candles) were re-fetched from the canonical
HTTPS page, default TLS verification enabled, redirects disabled, HTTP 200 at
**2026-10-17T16:15:05.665588Z** (21:45:05.665588 IST), 1,118,960 bytes.
Page SHA-256:
`eacaadbfa6bbc3ba8c27d1285e08e7bee522859d6226d36040c918875f5f9049`.
The markets/details/candles sections are byte-identical to Phase 8H. Full page,
sections, raw public bodies and request manifests are in `reports/phase8i-public/`;
compact evidence is [examples/phase8i-evidence.json](examples/phase8i-evidence.json).

The only exchange network calls in the collector were six unsigned GETs, all
HTTP 200: active markets, market details, and one completed 15m candle per pair.
Their routes are `https://api.coindcx.com/exchange/v1/markets`,
`https://api.coindcx.com/exchange/v1/markets_details` and
`https://api.coindcx.com/market_data/candles`. No private operation was attempted.
Actual URLs/parameters/body hashes/HTTP dates are retained; no cache or model
data is relabeled as a new server response.

Phase 8H's existing public snapshot has a 15:45 UTC candle close and metadata
observed at 15:58:20.458087 UTC on 17 October. Its four serialized diagnostic
records reproduce exactly, including quantities, exposure, fees and stop risk.
The new snapshot below is separate; prior prices were not overwritten.

New metadata observed **2026-10-17T16:15:08.682299Z** (21:45:08.682299 IST).
New price references are closes of **16:00–16:15 UTC completed 15m candles**,
fetched after completion under the local opening+15m rule. They are neither
best bid/ask nor verified executable prices or final-revision guarantees.

Official field meanings:

- `min_quantity`: minimum target-asset quantity.
- `step`: "the minimum increment accepted for the target currency".
- `min_notional`: "the minimum amount of base currency". For these four pairs,
  CoinDCX base_currency_short_name is INR (quote in this repository), while
  target_currency_short_name is the cryptocurrency.
- Precision fields document accepted decimals, not a separately verified price
  tick or a complete set of server/order-type acceptance rules. Current missing
  market-order minimum fields are not invented or equated to limit constraints.

### Why INR 100 returns NO_TRADE

**Margin** is collateral reserved, **notional** is price×quantity, and
**leverage** is their ratio. At 1x they happen to be numerically equal. INR 2000
total simulated equity does not make all that capital available to each entry:
the requested margin cap is INR 100, further bounded by 25% of current equity,
cash affordability and planned stop risk. No cap was raised automatically.

The unchanged model uses entry `E=reference×1.001`, fixed stop `T=E×0.98`,
modeled stop exit `F=T×0.999`, and fee fraction `f=0.001` on each side.
Per-unit planned loss is `u=E−F+f×(E+F)`. Initial budget is
`R=min(2000×0.005,20)=10`, and the authoritative gate can reduce it further for
remaining daily/drawdown room. INR 20 is an absolute ceiling, not permission to
spend INR 20 initially; INR 10 is a maximum initial budget, not a minimum loss.

Before quantity rounding, the sizer takes the smallest of:

```text
M×L/E                         margin ceiling, M=min(100,equity×0.25)
R/u                           risk ceiling
equity/(E/L + E×f)             margin-plus-entry-fee cash affordability
```

It rounds this maximum DOWN to a whole number of quantity steps. It then rejects
quantity below min_quantity or notional below min_notional; it never rounds UP
to fit an exchange minimum. The margin ceiling binds in all eight reviewed
Phase 8H/new numerical cases. Their candidate risk is below INR 10, but that
cannot override the margin or instrument minimum.

| Pair | Observed INR close | Step / min asset quantity | Min INR notional | Down-rounded quantity | Modeled notional = margin at 1x, INR | Estimated entry fee INR | Planned stop risk INR |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| I-BTC_INR | 8211416.5 | 0.00001 / 0.00001 | 100 | 0.00001 | 82.196279165 | 0.082196279165 | 1.88714601727481830 |
| I-ETH_INR | 242721 | 0.0001 / 0.0000001 | 100 | 0.0004 | 97.1854884 | 0.0971854884 | 2.231283571885368 |
| I-SOL_INR | 10486.8 | 0.001 / 0.01 | 100 | 0.009 | 94.4755812 | 0.0944755812 | 2.169066758282424 |
| I-DOGE_INR | 7.9596 | 1 / 0.001 | 100 | 12 | 95.6107152 | 0.0956107152 | 2.195128322491104 |

All four resulting notionals are below INR 100; SOL also fails its 0.01 quantity
minimum. A min_quantity smaller than step does not permit a fractional step.
Pure diagnostic status is **NO_TRADE**, with risk_approved=false and zero orders.
`size_position` supplied the actual public minima also rejects each candidate.

Independent exact Fraction arithmetic reproduces the production quantity,
exposure, margin, entry fee and stop risk for all four old and four new cases.
It also computes the smallest step-aligned quantity meeting both minimums:

| Pair | Minimum stepped quantity at modeled entry | Required notional / 1x margin INR | Margin plus assumed entry fee INR |
| --- | ---: | ---: | ---: |
| BTC | 0.00002 | 164.39255833 | 164.55695088833 |
| ETH | 0.0005 | 121.4818605 | 121.6033423605 |
| SOL | 0.01 | 104.972868 | 105.077840868 |
| DOGE | 13 | 103.5782748 | 103.6818530748 |

Each smallest compliant modeled lot exceeds INR 100 margin. Thus no compliant
lot exists **at these prices under the unchanged model/settings**. These are
arithmetic lower bounds, not recommendations, approved positions or verified
exchange fills. No margin, leverage or risk limit changed. Feasibility at every
historical price or a different future configuration is not inferred.

Fees are illustrative 0.1% of filled notional per side and are paid separately
from collateral in the simulation. Planned stop risk includes both fees and
adverse exit slippage. Actual fee rate/currency, market impact, executable depth,
price tick, gaps, partial fills and full server acceptance remain UNVERIFIED.
The table is pure numerical evidence, not cash fees incurred or performance.
Current raw leverage fields are null; they do not authorize 3x borrowing.
The hard 3x ceiling is preserved, while reviewed real spot remains limited to
1x by existing code. No speculative leverage increase is used to force a trade.

## 3. Original ETH values and data quarantine

Original ZIP SHA-256 is still
`2ff6f63c3c03083592d53767c13ab06056189d7c1b52ec798e081cd64c2a3835`.
All 85 manifested original source files and their working copies were checked.
Existing Phase 8G/8H quarantine files and Phase 8H raw documentation/public inputs
were separately fingerprinted before this task; 37 retained input files remain
unchanged. No old sample or failed row was removed.

For I-ETH_INR opening **1791934200000 ms / 2026-10-13T23:30:00Z**
(14 October 05:00 IST), direct raw and normalized 15m volume remains
**0.086267 ETH**; the original 15 consecutive 1m values sum to **0.085028 ETH**,
difference **0.001239 ETH**. This was recomputed from original ZIP bodies with
exact arithmetic. Original CSV SHA-256 remains
`ef035c02465f4801abc26d5d260aac36922ac5ec9dd5aa17fcc291453bca2c3c`.

Official documentation establishes **target-asset volume units**. It does not
establish identical trade coverage, aggregation algorithm, cross-request revision
or definitive zero/no-trade semantics. These remain UNVERIFIED, and the numerical
difference alone does not prove a provider bug. ETH stays quarantined; original
CSV/raw values and false quality_reviewed/ingestion_eligible flags are intact.
No candle volume is interpreted as proof of executable quote liquidity.

Four new guarded `assess`/`load_eligible` checks retain all 11,520 records per
symbol and reject every dataset. BTC/SOL/DOGE retain SOURCE_INGESTION_REJECTED,
ZERO_VOLUME and LIQUIDITY_REVIEW_REQUIRED; ETH additionally retains
SOURCE_INTERVAL_MISMATCH. The loader rejects before strategy/simulation entry.
No source or liquidity rule is weakened. Fresh minimum-order metadata does not
retroactively establish historical constraints, executable depth or eligibility.

## 4. Tests, exact execution commands and changes

Only Linux was available. Standard-library-only environment; no new installation,
service, network permission or environment draft change was needed.

| Execution | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Linux baseline discovery | 633 | 0 | 0 | 1 | 634 | 31.815 |
| Linux focused sizing/risk/interval | 152 | 0 | 0 | 0 | 152 | 3.692 |
| Linux final public-enabled discovery | **634** | **0** | **0** | **0** | **634** | **40.410** |
| Native Windows | Not run | Not run | Not run | Not run | Not run | Not measured |

Actual commands from `/workspace/Coindcx-trading-bot`:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_minimum_diagnostics tests.test_risk tests.test_central_risk tests.test_candle_semantics tests.test_interval_trace -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=. .venv/bin/python reports/phase8i/collect.py --output reports/phase8i-public
```

The last command's output directory must be new; it already exists after this
audit. For a later collector reproduction use `--output reports/phase8i-local`.
The ignored collector and raw artifacts are retained locally, not bundled into
a normal Git clone. Unit tests do not require the genuine historical archive.

The baseline's only skip is the opt-in public discovery/candle test. It ran and
passed in final discovery; there are no final skipped tests. No tests failed.
The focused suite covers sizing minimums, cost assumptions, fixed limits,
gate bypass attempts, zero/malformed volume, timestamps, incomplete/duplicate
records and quarantine. Full discovery also covers prior persistence, paper
worker, strategies, backtests and exchange mocks. Synthetic fixtures remain
explicitly synthetic; neither passing tests nor public connectivity qualify a
real symbol or establish profitability.

No implementation defect was found or patched, and no existing test changed.
Eight guarded numerical functional checks (four Phase 8H, four new), plus four
guarded actual-data eligibility checks, are separate from unit-test counts.
Sockets, broker, credential loading, simulation and experiment calls were
forbidden during those pure checks; none occurred. Collector error branches
are not a comprehensive independently unit-tested framework.

Full test logs: `/tmp/phase8i-baseline.log`, `/tmp/phase8i-relevant.log`,
`/tmp/phase8i-full-public.log`. Exact sources, numbers, command/environment
evidence and test log hashes are in the JSON evidence linked above. Ignored
workspace artifacts/hashes are local audit evidence, not independently signed
provider history or automatically published records.

Phase-local Git-visible changes are only new `docs/PHASE8I_AUDIT.md` and
`docs/examples/phase8i-evidence.json`, and updated `README.md` / `VALIDATION.md`.
README now states the correct parent-directory convention and native Python
guard; both documents record current evidence. The ignored collector/public
responses/verification records are audit artifacts, not new trading interfaces.
Compared with the 140-file pre-task snapshot, 138 inherited files remain
byte-identical, two documents changed, two added, none deleted. All application,
tests, dependencies, config and 15 frozen source/rule fingerprints are unchanged.
Diff/whitespace, JSON, hashes and exclusions were checked. Nothing is staged,
committed or pushed. `.env.example` remains 20 blank BOT names; no tracked/staged
real .env/key/credential file or detected credential value in changed files.
Pattern checks do not certify all external Git history.

Remaining blockers: actual native Windows execution/output; authoritative ETH
aggregation/revision clarification or corroborating evidence; genuinely eligible
continuous history and historical instrument/cost review; executable liquidity;
and a valid proposed size within the existing requested margin and risk limits.
No account balance, fill, performance, Windows result or liquidity is invented.
**Live trading stays disabled. Wait for explicit approval before any subsequent
phase; do not proceed to Phase 9.**
