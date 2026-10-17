# Phase 8H — official market-data semantics and eligibility

17 October 2026. **Historical eligibility remains BLOCKED; entry action
NO_TRADE for BTC, ETH, SOL and DOGE.** The current official public documentation
confirms the repository's routes, fields, target-asset volume and opening times
in milliseconds. It does not settle cross-interval aggregation, revision or
underlying trade coverage. The ETH difference is reproducible arithmetic; it
does not prove a documented-contract violation or a provider bug. Quarantine
remains enforced without replacing, removing or relabeling failed samples.

Final suite: **634 passed, 0 failed, 0 errors, 0 skipped** on Linux 6.18.55
x86_64/glibc 2.41, CPython 3.12.14, SQLite 3.53.1. No current native Windows
test was executed. Unit tests are not evidence of historical profitability,
executable liquidity or live readiness.

## Gate 0 and requirement matrix

Inspected the Phase 8G audit, its original ZIP/CSV/raw/sidecar evidence, frozen
Phase 8F rules, public client, schema, interval diagnostics, quality/eligibility
loaders, strategies, public instrument diagnostics, sizing and central entry gate.
The existing Python environment has no third-party requirements or service
startup prerequisite; no environment configuration change was needed.

| Requirement | Status | Evidence / practical limit |
| --- | --- | --- |
| Preserve safety and fixed configuration | PASS | Config/application/tests unchanged; original INR 2000, maximum 3x, initial planned risk INR 10/hard cap INR 20, daily lower of INR 40 or 2%, three entries/UTC day, one long, emergency/drawdown limits retained |
| Inspect current official source | PASS | Canonical HTTPS page HTTP 200, exact hashes/excerpts below; relevant public sections unchanged from retained Phase 8E source |
| Endpoint/parameter/field representation | PASS | Official source agrees with implemented public GET paths, 15m and target-asset volume mapping; actual public discovery/metadata/candle responses retained |
| Provider boundary, aggregation and revision guarantees | UNVERIFIED | Not specified in the reviewed public candle contract; local conventions are not provider promises |
| Reproduce original ETH numbers | PASS | Verified original ZIP and independent Decimal/Fraction arithmetic; 0.086267 versus 0.085028 ETH |
| Establish semantic equivalence or exact provider cause | UNVERIFIED | Same pair/requested openings/units verified; same underlying trades/revision not established |
| ETH reconciliation and requalification | BLOCKED | Source uncertainty remains; unchanged-value quarantine rejects validation, re-import and eligibility loading |
| Independent four-symbol eligibility audit | PASS | All 46,080 original OHLCV mappings rechecked; separate completeness, semantics, liquidity and sizing decisions below |
| Historical backtest eligibility | BLOCKED | All four fail unchanged zero-volume/liquidity requirements; ETH additionally quarantined for the arithmetic discrepancy |
| Default current size feasibility | BLOCKED | Four public snapshots return NO_TRADE at INR 100 margin/1x; no risk approval or fill |
| Full available Linux suite | PASS | 634/0/0/0 passed/failed/errors/skipped; focused group 203/0/0/0 |
| Native Windows / actual exchange execution | UNVERIFIED | Neither was performed; public reads and mocks do not verify private execution |
| No private requests, credentials, orders or Phase 9 | PASS | Documentation/public GETs only; no worker startup, account mutation, trading-rule tuning or live/short enablement |

## 1. Current official documentation and source evidence

Canonical source: <https://docs.coindcx.com/>, retrieved
**2026-10-17T15:56:54.734969Z** (21:26:54.734969 IST), HTTP 200,
1,118,960 bytes, default HTTPS certificate/hostname verification enabled,
redirects disabled. SHA-256:
`7817d23c17301b45bc5f79d970e8ab85536af45fa529ca7460d8eb35b705f275`.
The response reports Last-Modified `Wed, 19 Aug 2026 11:59:58 GMT`; that header
is not a guarantee that the described exchange behavior has been tested.

Full raw page and bounded section HTML/text are retained under
`reports/phase8h-docs/`; provenance/section hashes and source excerpts are in
[examples/phase8h-evidence.json](examples/phase8h-evidence.json). The whole-page
hash differs from Phase 8E, but the three relevant HTML sections are
**byte-identical**. No undocumented interval/alternate endpoint was substituted.

| Official source | Actual public endpoint | Documented fields / purpose |
| --- | --- | --- |
| [Markets](https://docs.coindcx.com/#markets), captured HTML lines 1092–1121 | `GET https://api.coindcx.com/exchange/v1/markets` | Array of currently active market names |
| [Markets details](https://docs.coindcx.com/#markets-details), lines 1122–1252 | `GET https://api.coindcx.com/exchange/v1/markets_details` | Pair/symbol, status, currency identity, precision, step, quantity/notional/price constraints, supported order types and leverage fields |
| [Candles](https://docs.coindcx.com/#candles), lines 1388–1475 | `GET https://api.coindcx.com/market_data/candles` | Descending candle array: `open,high,low,close,volume,time`; time uniquely identifies a candle |

The examples send unsigned public GETs without API keys/signatures. The actual
client accepts no credential and restricts HTTP transport to those three HTTPS
host/path combinations. No account/order/private endpoint was contacted.

### Candle semantics: documented versus unverified

| Item | Official evidence / assessment |
| --- | --- |
| `pair` | Required, from Market Details; do not synthesize a ticker. `I-ETH_INR` maps to asset ETH and quote INR in actual archived/current metadata |
| `interval` | Required; current valid list `1m`, `15m`, `1h`, `1d`. Trading code remains 15m only; archived 1m data is diagnostic |
| `startTime`, `endTime` | Optional, described as timestamps in milliseconds. Server inclusive/exclusive boundaries are UNVERIFIED |
| `limit` | Optional, default 500, maximum 1000 |
| `time` | Exact source comment: **"open time in ms"**. Client interprets Unix milliseconds as aware UTC, consistent with archived observed openings; server boundary timezone/origin is not explicitly documented |
| `volume` | Exact source: **"total volume in terms of target currency (in BTC for B-BTC_USDT)"**. ETH/INR volume is ETH, not INR turnover or executable depth |
| Ordering | Exact source: **"This API provides with a sorted list (in descending order according to time key) of candlestick bars for given pair. Candles are uniquely identified by their time."** |
| OHLC | Source describes open/highest/lowest/close prices. Finite positive prices and coherent OHLC are existing local validation requirements; price history authenticity is not established by shape |
| Aggregation | No algorithm or promise that 15m volume equals separately retrieved 1m sums; underlying trade population, revision, atomic snapshot and cross-interval consistency semantics UNVERIFIED |
| Zeros | No verified no-trade/carry-forward/missing-volume convention. Explicit numeric zero is preserved for analysis; malformed/missing volume is not defaulted to zero |
| Retention/completeness | No guaranteed oldest date, full listing history, complete underlying trade feed or maximum recoverable history period in this contract |
| Quotas | No verified numeric public candle quota; local spacing/retries/page caps are client policy |
| Completion | No closed/final revision flag. Closing at opening+15m and rejecting future/incomplete data are local rules, not proof a provider will never revise a closed candle |

The local range convention remains `[start,end)`, request `endTime=end_ms−1`,
explicit returned-row filtering, ascending UTC storage, aligned completed bars,
no padding/deduplication/resampling. Those are defensive implementation choices,
not a newly asserted official timezone or server pagination guarantee. HTTP
success alone does not settle any UNVERIFIED semantics.

## 2. Original ETH comparison: arithmetic and semantic validity

Original archive `reports/phase8f-replay-inputs.zip` remains 3,342,701 bytes,
SHA-256 `2ff6f63c3c03083592d53767c13ab06056189d7c1b52ec798e081cd64c2a3835`.
All 85 manifested source files/86 ZIP entries were verified again using the
unchanged `tools/phase8g_archive.py`, with network, strategies, broker and
experiments forbidden. New output is `reports/phase8h-original/`; no original
archive, raw file, CSV, metadata or previous report was overwritten.

Same public pair **I-ETH_INR**, opening **1791934200000 ms /
2026-10-13T23:30:00Z** (14 October 05:00 IST), modeled closing
23:45 UTC / 05:15 IST. Both requests use `startTime=1791934200000` and
`endTime=1791935099999`, with interval respectively `15m` and `1m`.
Archived direct limit=1 and limit=1000 responses agree. The exact 1m request
has 15 unique consecutive openings 23:30–23:44 UTC; the 45-minute context agrees.

Raw original direct body (`reports/phase8e-trace/public-0003.json` inside ZIP;
SHA-256 `db95541fdb21ea971ae0cc076a9d77ee2e9edaafb794b726c301c087f64dff2a`):

```json
[{"open":250244.2,"high":250244.2,"low":249701,"close":250218.5,"volume":0.086267,"time":1791934200000}]
```

Production normalization/storage preserves it as:

```csv
timestamp,open,high,low,close,volume,symbol,timeframe,quote_volume
2026-10-13T23:30:00+00:00,250244.2,250244.2,249701,250218.5,0.086267,I-ETH_INR,15m,
```

No volume conversion, quote-volume inference or local 1m aggregation occurs in
the storage path. Empty quote_volume means unavailable. Independent exact sums
from original minute JSON give:

| 1m opening UTC, 13 October | Raw ETH volume |
| --- | ---: |
| 23:30 | 0.000439 |
| 23:34 | 0.001191 |
| 23:35 | 0.000800 |
| 23:40 | 0.001898 |
| 23:42 | 0.079929 |
| 23:43 | 0.000771 |
| Other nine target minutes | Explicit numeric 0 each |
| Fifteen-minute sum | **0.085028** |

Direct volume **0.086267** minus minute sum **0.085028** is **0.001239 ETH**.
The minute-derived O/H/L/C equals the direct 15m O/H/L/C exactly. There are no
missing/duplicate/misaligned/incomplete target minutes. All 31 complete sliding
15-minute windows in the recorded 45-minute context (offsets −15…+15 minutes)
also fail to match 0.086267. This rules out those recorded shifts only.

The 15m body was observed at 2026-10-17T14:43:16.554601Z, repeated at
14:43:17.190439Z and 14:43:17.790351Z; exact 1m at 14:43:18.630672Z, context
at 14:43:19.136873Z. The requests are **not an atomic provider snapshot**.
HTTP dates/hashes and agreement across limits do not establish common revision
or complete, identical underlying trade coverage.

**Assessment:** arithmetic comparison PASS for the recorded values under the
observed opening-time/units convention. A semantic expectation of equality is
conditional on identical boundaries, trade coverage, aggregation and revisions.
The documentation and archive cannot establish every prerequisite. Exact
provider cause and a documented-contract violation remain UNVERIFIED. Phase 8G's
"consistency FAIL" describes this numerical inequality; it must not be read as
proof of a provider bug or that a particular amount of trading is missing.

No local implementation defect was proven. ETH reconciliation remains BLOCKED.
The existing `CROSS_INTERVAL_VOLUME_MISMATCH` / `SOURCE_INTERVAL_MISMATCH`
quarantine is retained as a conservative unresolved-evidence flag. No arithmetic
match would independently prove liquidity or market eligibility either.

### Quarantine verification

New quarantine copy retains original ETH CSV bytes (SHA-256
`ef035c02465f4801abc26d5d260aac36922ac5ec9dd5aa17fcc291453bca2c3c`) and original
raw-page archive bytes (SHA-256
`2897c3a40847570dbdab7ecfd4e34c8d0d7af831b466c74945fe4e981b77eafe`). All 11,520
rows remain; quality_reviewed and ingestion_eligible stay false. Actual CLI
validation and re-import both return expected exit 2 with SOURCE_INGESTION_REJECTED,
SOURCE_INTERVAL_MISMATCH, ZERO_VOLUME and LIQUIDITY_REVIEW_REQUIRED. Re-import
preserves CSV bytes and the mismatch flag. The eligible-dataset loader rejects
before any strategy/simulation call. These are successful safety rejections,
not failed unit tests or fabricated strategy signals.

## 3. Symbol-by-symbol eligibility

Historical source is the original public candle capture from the endpoint above,
not synthetic fixtures. Each window is **[2026-06-19T14:30:00Z,
2026-10-17T14:30:00Z)**, 120 days of 15m records. Last opening 14:15 UTC,
closing 14:30 UTC on 17 October. Raw pages are descending; normalized records
ascending/aligned UTC. All 46,080 raw OHLCV mappings match stored values.

| Pair | Completed bars | Gaps / duplicates / incomplete | Invalid OHLCV/time shape | Flat zero bars | Positive-volume shape only | Eligible strategy observations |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| I-BTC_INR | 11,520 | 0 / 0 / 0 | 0 | 6 | 11,514 | 0 |
| I-ETH_INR | 11,520 | 0 / 0 / 0 | 0 | 46 | 11,474 | 0 |
| I-SOL_INR | 11,520 | 0 / 0 / 0 | 0 | 23 | 11,497 | 0 |
| I-DOGE_INR | 11,520 | 0 / 0 / 0 | 0 | 195 | 11,325 | 0 |

All 270 zeros are explicit flat source records. Zero is not inherently malformed
OHLCV or automatically a provider failure. Genuine no-trade semantics remain
UNVERIFIED. `CandleRecord` retains these rows for analysis, while both existing
trading strategies' Candle/history contracts require positive volume and the
strict policy permits a zero-volume fraction of zero. No rule was relaxed and
no failed sample was silently dropped, padded or replaced to join history.

| Pair | Historical candle completeness | OHLCV representation / source accuracy | Quote turnover and executable depth | Current metadata / default size | Historical backtest |
| --- | --- | --- | --- | --- | --- |
| BTC | PASS for archived openings | PASS field/shape mapping; underlying trade completeness UNVERIFIED; 6 policy exclusions | UNVERIFIED; no verified quote volume/depth | PASS public metadata capture; NO_TRADE size | BLOCKED: zeros, source review and liquidity |
| ETH | PASS for archived openings | PASS field/shape mapping; interval semantic reconciliation UNVERIFIED; 46 policy exclusions | UNVERIFIED; no verified quote volume/depth | PASS public metadata capture; NO_TRADE size | BLOCKED: quarantine, zeros, source review and liquidity |
| SOL | PASS for archived openings | PASS field/shape mapping; underlying trade completeness UNVERIFIED; 23 policy exclusions | UNVERIFIED; no verified quote volume/depth | PASS public metadata capture; NO_TRADE size | BLOCKED: zeros, source review and liquidity |
| DOGE | PASS for archived openings | PASS field/shape mapping; underlying trade completeness UNVERIFIED; 195 policy exclusions | UNVERIFIED; no verified quote volume/depth | PASS public metadata capture; NO_TRADE size | BLOCKED: zeros, source review and liquidity |

Each pair independently retains SOURCE_INGESTION_REJECTED, ZERO_VOLUME and
LIQUIDITY_REVIEW_REQUIRED. ETH additionally retains SOURCE_INTERVAL_MISMATCH.
The ETH discrepancy is not assumed to affect the other pairs. Four actual
guarded loader checks reject for absent explicit historical quality review;
separate quality checks establish why that flag cannot simply be enabled.

No stored quote-volume observations exist for any pair: unavailable is not zero
liquidity. Target-asset volume or close×volume cannot prove INR turnover, depth,
spread, market impact or a full executable fill. Current active identity does
not establish historical listing/survivorship, contract changes, fees or trade
completeness. Zero gaps/duplicates cannot establish those either.

Requirements remain 2,880 consecutive eligible completed 15m warmup bars,
strict ordered OHLCV, no stale/incomplete data, reviewed source/market/liquidity,
reliable instrument/cost evidence and fresh central approval. SMA 5/20 and
momentum 12/0.01, fixed 2% stop, next-bar fills and all frozen exit/sizing rules
remain unchanged; see [PHASE8F_RULES.md](PHASE8F_RULES.md). No favorable subwindow
was selected or treated as an untouched OOS experiment.

## 4. Current public constraints, distinct from historical eligibility

Six actual unsigned public GETs, all HTTP 200: active markets, market details,
and one completed 15m candle per pair. Raw bodies/URLs/parameters/times/hashes
are under `reports/phase8h-public/` and included in compact form in the evidence.
Metadata observed **2026-10-17T15:58:20.458087Z** (21:28:20.458087 IST).
Price references are the **15:30–15:45 UTC completed candle close**, fetched
after completion, not executable quotes. Each candle used
`startTime=1792251000000`, `endTime=1792251899999`, `interval=15m`, `limit=1`.

Official market details define `min_quantity` as target-asset quantity,
`min_notional` as **"the minimum amount of base currency"**, and `step` as
**"the minimum increment accepted for the target currency"**. CoinDCX's
base_currency_short_name is INR for these four pairs (quote currency in this
repository); target is the crypto asset. Precision is documented decimals,
not independently verified server price-tick behavior.

| Pair | Current step / min target quantity | Min INR notional | INR close reference | Rounded candidate quantity | Modeled notional / 1x margin INR | Estimated entry fee INR |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BTC | 0.00001 / 0.00001 | 100 | 8175901 | 0.00001 | 81.84076901 | 0.08184076901 |
| ETH | 0.0001 / 0.0000001 | 100 | 243615.8 | 0.0004 | 97.54376632 | 0.09754376632 |
| SOL | 0.001 / 0.01 | 100 | 10420.4 | 0.009 | 93.8773836 | 0.0938773836 |
| DOGE | 1 / 0.001 | 100 | 8.03 | 12 | 96.45636 | 0.09645636 |

Every candidate fails INR 100 minimum notional; SOL also fails min quantity.
Existing pure diagnostics return **NO_TRADE**, not entry approval. Margin stays
INR 100 maximum requested; leverage stays 1x. Margin/notional coincide numerically
at 1x but have different meanings. Current raw max_leverage/max_leverage_short
are null, not authority to borrow or trade at 3x. Short entries remain disabled.
Both quantity precision and step are respected; a minimum quantity below step
does not permit a fractional step.

The table uses unchanged **assumed** adverse entry slippage 0.1% and fee 0.1%;
fees are separate from margin. Modeled planned stop losses are below the initial
INR 10 budget, but that cannot override failed instrument/market requirements.
Actual fee/slippage calibration, price tick, exchange validation and full fills
remain UNVERIFIED. Minimum stepped quantities would require more than INR 100
margin under these assumptions; none was selected or proposed as a new setting.
Fresh constraints do not retrospectively validate orders throughout 120 days.
Four positive-volume recent candles also do not repair old exclusions or supply
2,880 qualified bars or executable liquidity.

**Backtests/OOS evaluations executed: 0. Performance unavailable/null**, including
trade sample, P&L, win rate, expectancy, profit factor, drawdown and benchmark.
There were no historical simulated fills or fabricated performance metrics.

## 5. Tests, changes and remaining blockers

| Run | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline full discovery | 633 | 0 | 0 | 1 | 634 | 18.409 |
| Focused interval/data/gate/sizing | 203 | 0 | 0 | 0 | 203 | 1.090 |
| Final public-enabled full discovery | **634** | **0** | **0** | **0** | **634** | **19.497** |

Exact test commands, from the repository root:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_interval_trace tests.test_candle_semantics tests.test_data_pipeline tests.test_public_market_data tests.test_market_quality tests.test_central_risk tests.test_minimum_diagnostics -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```

The baseline skip is the opt-in public integration test; it ran and passed in
final discovery. No final tests were skipped. No local root cause was proven,
so no production patch or new regression assertion was appropriate. Existing
synthetic tests cover timestamp units/UTC alignment, boundaries, missing and
duplicate intervals, incomplete candles, malformed/zero volume, arithmetic
differences and quarantine retention, plus risk, persistence, worker and adapter
regressions. They remain synthetic, separate from actual archived/public data.
Public integration success checks response handling, not source truth or trading
eligibility. Windows and private execution were not tested.

The existing archive tool's `run` function was called in a guarded Python
invocation with sockets, both strategy calculations, PaperBroker, simulate and
run_experiment forbidden; zero unexpected calls. Reproduction without those
extra guards, using a new output directory and the retained original ZIP:

```bash
.venv/bin/python -m tools.phase8g_archive --archive reports/phase8f-replay-inputs.zip --output reports/phase8h-local
```

Actual quarantine CLI commands (both expected exit 2) were:

```bash
.venv/bin/python -m cli data validate --input reports/phase8h-original/quarantine/I-ETH_INR.csv --as-of 2026-10-17T14:30:00+00:00
.venv/bin/python -m cli data import --input reports/phase8h-original/quarantine/I-ETH_INR.csv --as-of 2026-10-17T14:30:00+00:00 --output reports/phase8h-original/quarantine/I-ETH_INR.reimport.csv
```

Full logs are `/tmp/phase8h-baseline.log`, `/tmp/phase8h-relevant.log`,
`/tmp/phase8h-full-public.log`. Reports/raw bodies/logs in ignored workspace
paths are local evidence, not automatically published or independently signed.

### Windows PowerShell instructions — not executed on Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Offline tests failed" }
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Public-enabled tests failed" }
} finally {
    Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
}
```

The public-enabled run needs network access. Default discovery intentionally
skips one optional test. Earlier Phase 1 Windows CI does not verify this source.

### Phase-local diff and next evidence needed

Only documentation/evidence changes:

- New `docs/PHASE8H_AUDIT.md` and `docs/examples/phase8h-evidence.json`.
- Updated `docs/COINDCX_API.md` with current sources and explicit semantic limits.
- Updated `README.md` and `VALIDATION.md` with current outcomes.

Compared with the 138-file phase-start snapshot (including inherited untracked
work), 135 inherited files remain byte-identical; three documents changed, two
documents added, none deleted. No application, tests, dependencies, config,
strategy, limits, original archived data or quarantine flags changed. All 15
frozen Phase 8F rule/source fingerprints still match. Full diff/whitespace,
JSON, source hashes and Git exclusions were checked; index remains empty,
with no tracked/staged real .env/key/credential file found. The existing
.env.example remains 20 blank BOT variable names. Pattern checks of changed
files found no credential values; they cannot certify all external Git history.
Nothing was staged, committed, pushed or sent to another party.

Remaining prerequisites are authoritative interval/revision/trade-population
clarification or independently corroborating evidence for ETH; strategy-eligible
continuous history without silently removing failures; historically relevant
instrument/listing/cost review; and justified executable-liquidity evidence.
Only then can unchanged chronological evaluation be considered. Native Windows
verification remains independent work. No safeguard is weakened to obtain trades.

**Live trading stays disabled. No private requests, credentials, real orders,
paper worker startup or Phase 9. Wait for explicit approval before any subsequent
phase.**
