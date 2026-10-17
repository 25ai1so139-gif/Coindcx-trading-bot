# Phase 8G — original ETH archive audit and backtest decision

17 October 2026. **Audit complete; historical backtest/OOS unblocking remains
BLOCKED. Permitted entry action: NO_TRADE.** The original public responses
contain a reproducible ETH interval-volume difference. No local field-mapping,
timestamp, resampling or storage defect was proven. The provider's aggregation/
revision mechanism remains UNVERIFIED; neither source value was replaced.

Final full suite: **634 passed, 0 failed, 0 errors, 0 skipped**, on Linux
6.18.55 x86_64/glibc 2.41, CPython 3.12.14, SQLite 3.53.1. Tests establish
software behavior, not profitability, qualified liquidity or live readiness.
Current native Windows execution remains UNVERIFIED.

## Requirement matrix

| Requirement | Status | Evidence / limit |
| --- | --- | --- |
| Preserve capital, leverage, strategy and risk rules | PASS | Existing config/trading/test files and frozen Phase 8F source fingerprints unchanged; INR 2000, maximum 3x, initial planned risk INR 10/hard ceiling INR 20, daily minimum of INR 40 or 2%, three entries/UTC day, one long, emergency/drawdown halts retained |
| No private endpoints, credentials, real orders or next phase | PASS | Archive audit is offline, guarded against network/strategy/simulation calls; final optional integration test uses public read-only endpoints only; live and short entries remain disabled |
| Reproduce original ETH discrepancy | PASS | Original ZIP/85 source-file hashes verified; independent exact arithmetic reproduces 0.086267 versus 0.085028 ETH at the opening below |
| Sample's cross-interval volume consistency | FAIL | Difference 0.001239 ETH remains in the archived original responses; OHLC agrees |
| Identify a specific local implementation defect | UNVERIFIED | None proven by raw-to-production-to-storage trace; no speculative production patch |
| Establish provider mechanism/trade completeness | UNVERIFIED | Documentation does not establish identical trade population, revisions or exact aggregation guarantees across the two endpoints' intervals |
| Preserve evidence and quarantine unresolved sample | PASS | Separate byte-identical CSV/raw copy, explicit mismatch warning, false review/eligibility flags; CLI validation and re-import reject it |
| Independently requalify BTC/ETH/SOL/DOGE | PASS | 46,080 raw/normalized matches and individual quality/size results; none approved |
| Historical dataset eligibility and executable liquidity | BLOCKED | All four fail unchanged zero-volume/liquidity requirements; ETH also fails source interval check |
| Default INR 100 margin snapshot feasibility | BLOCKED | All four quantity-rounded candidates are below INR 100 minimum notional; SOL also below minimum quantity; action NO_TRADE |
| Qualified historical/OOS backtest and performance | BLOCKED | No eligible dataset or entry; zero experiments executed, performance unavailable |
| Full available Linux regressions | PASS | 634/0/0/0 passed/failed/errors/skipped; focused group 203/0/0/0 |
| Current native Windows / actual exchange execution | UNVERIFIED | Not executed on Windows; no private exchange operation authorized or attempted |

## Original evidence and method

Inspected Phase 8F's audit, frozen rules, original archive, CSVs/sidecars and the
actual public client, schema, interval comparison, quality/storage/loader,
strategies, sizing, central gate and historical execution interfaces. No
existing application code or unit test changed in this phase.

Original archive: `reports/phase8f-replay-inputs.zip`, 3,342,701 bytes, SHA-256
`2ff6f63c3c03083592d53767c13ab06056189d7c1b52ec798e081cd64c2a3835`.
Its 85 source files plus manifest (86 ZIP entries) were checked against the
original sizes/hashes. It contains the original public history/trace responses,
request manifests, normalized records, sidecars and pre-test rules record.
The archive and its original working files were preserved. Checksums establish
local identity, not independently authenticated trade completeness.

[tools/phase8g_archive.py](../tools/phase8g_archive.py) reads raw bodies directly
from that ZIP in memory. Its arithmetic uses standard-library JSON Decimal
parsing and exact Fraction sums independently of `data/intervals.py`. It also
replays original HTTP bodies through the actual `PublicClient.history` and
`normalize` path with an injected offline transport. It does not rely on a
replayer resolving loose files outside the ZIP. Altering the ZIP is rejected
before an output directory is created.

Final evidence is [examples/phase8g-evidence.json](examples/phase8g-evidence.json).
Full local artifacts: `reports/phase8g-verified/eth-trace.json`, `evidence.json`,
`quarantine/` and `quarantine-verification.json`. The guarded audit ran at
21:00:33.710343 IST on 17 October 2026 (stored UTC 15:30:33.710343).
Sockets, both strategy calculations, broker, simulation and experiment calls
were patched to raise if called: no unexpected calls, network requests, orders
or backtests. This functional check is separate from unit-test counts.

### Documentation contract and limits

Official source: [CoinDCX API documentation](https://docs.coindcx.com/),
anchors `#markets`, `#markets-details`, `#candles`. The retained Phase 8E copy
was retrieved at 20:13:49.695743 IST on 17 October 2026, HTTP 200, 1,118,960
bytes, SHA-256 `4aa8e4e4a3f26cb626c847b651853734405dbcbe88a087963602964a0d7b2603`.
This phase inspected the retained documentation; it did not newly verify an
ETH server response or a provider explanation.

Public GETs in the original trace are:

- `https://api.coindcx.com/exchange/v1/markets`
- `https://api.coindcx.com/exchange/v1/markets_details`
- `https://api.coindcx.com/market_data/candles`

They require no private API credentials. The retained candle contract describes
`pair`, intervals `1m`, `15m`, `1h`, `1d`, `limit` (default 500/max 1000), optional
`startTime`/`endTime`, descending candle objects with opening epoch milliseconds,
OHLC prices and target-asset volume. It does not document an exact no-trade-zero
convention, historical revision policy or guarantee that separately retrieved
1m and 15m records represent an identical trade population. No stronger provider
claim is inferred from the observed mismatch.

## ETH failure: exact raw-to-storage trace

Instrument: active public `I-ETH_INR`, target asset ETH, quote INR. Opening
`1791934200000` ms = **14 October 2026 05:00 IST**
(`2026-10-13T23:30:00Z`); close 05:15 IST (`23:45:00Z`). Original body is
`reports/phase8e-trace/public-0003.json` inside the ZIP:

```json
[{"open":250244.2,"high":250244.2,"low":249701,"close":250218.5,"volume":0.086267,"time":1791934200000}]
```

| Stage | Observed behavior |
| --- | --- |
| Raw parsing in `data/coindcx.py` | Decimal JSON numeric parsing; exact `open/high/low/close/volume` keys retained, no price/volume substitution |
| Timestamp normalization in `data/schema.py` | Integer milliseconds to aware UTC; opening aligned to 15 minutes; no seconds/milliseconds or local-time reinterpretation |
| Timeframe path | Client requests `interval=15m` directly; no local 1m-to-15m aggregation creates the stored candle |
| Schema and storage | `normalize` / `CandleRecord` and `data/storage.py` retain volume `0.086267`; stored timestamp `2026-10-13T23:30:00+00:00`; quote_volume empty/unavailable |
| Independent comparison | Fifteen complete, unique 1m openings from 23:30 through 23:44 UTC sum to `0.085028` ETH; O/H/L/C = 250244.2/250244.2/249701/250218.5, all matching the direct 15m bar |

The six positive minute volumes are below; the other nine target minutes have
explicit numeric zero. The complete 15-row ledger, including epoch milliseconds,
is in the published evidence.

| Opening, 14 October IST | Opening, 13 October UTC | Raw ETH volume |
| --- | --- | ---: |
| 05:00 | 23:30 | 0.000439 |
| 05:04 | 23:34 | 0.001191 |
| 05:05 | 23:35 | 0.000800 |
| 05:10 | 23:40 | 0.001898 |
| 05:12 | 23:42 | 0.079929 |
| 05:13 | 23:43 | 0.000771 |
| Sum | Fifteen-minute window | **0.085028** |

Thus 86,267 versus 85,028 micro-ETH differs by **1,239 micro-ETH / 0.001239 ETH**.
This is not floating-point rounding. The direct limit=1 and limit=1000 original
responses agree, as do the exact-window 1m response and selected 45-minute context
records. Target/context timestamps are aligned, unique, complete and contiguous;
all target candles closed before capture. No malformed/missing volume exists in
this sample. No local unit scaling occurs.

All **31 complete sliding 15-minute windows** in the archived 45-minute context,
offset −15 through +15 minutes, were independently summed: **zero** match the
reported 0.086267 ETH. These available offsets do not explain it. This bounded
check cannot establish every possible provider timezone or aggregation policy.

If both intervals represent the same trade population and revision, additive
volume should agree. The archive cannot establish that prerequisite or reveal
the provider's backend. The verified finding is a **source-response volume
difference with matching OHLC**, with no demonstrated client conversion defect.
Provider revision, trade inclusion and aggregation semantics remain unresolved.
Do not infer the location of a missing trade or substitute either volume.

### Quarantine without data repair

Using existing `write_dataset`, the audit writes a separate
`reports/phase8g-verified/quarantine/I-ETH_INR.csv` and sidecar/raw evidence.
The affected original 15m record is retained unchanged; the whole dataset is
ineligible because it contains the unresolved sample. No original file was
overwritten and no row was removed or manufactured.

- CSV is byte-identical to original: SHA-256
  `ef035c02465f4801abc26d5d260aac36922ac5ec9dd5aa17fcc291453bca2c3c`.
- Original raw-page JSON archive bytes are retained: SHA-256
  `2897c3a40847570dbdab7ecfd4e34c8d0d7af831b466c74945fe4e981b77eafe`.
- Sidecar retains `quality_reviewed=false`, `ingestion_eligible=false`, and
  appends `CROSS_INTERVAL_VOLUME_MISMATCH` plus source-archive/time/reason links.
- Actual CLI validation and re-import both return expected **exit 2**, with
  `SOURCE_INGESTION_REJECTED`, `SOURCE_INTERVAL_MISMATCH`, `ZERO_VOLUME`,
  `LIQUIDITY_REVIEW_REQUIRED`. Re-import preserves CSV bytes and mismatch flags.
  Its new raw import artifact appropriately records the imported CSV bytes;
  the first quarantine copy retains the original raw JSON.
- Existing eligibility loader also rejects for missing explicit historical
  quality review. No strategy or broker is reached.

These are expected safety rejections, not failed unit tests. Synthetic interval
fixtures remain explicitly synthetic; they are not part of this public archive.

## Independent historical requalification

Each pair is checked against its own original raw-page bodies, request bounds,
CSV/sidecar hashes, source schema and unchanged `DataPolicy`. Shared range:
**[19 June 2026 20:00 IST, 17 October 2026 20:00 IST)**, equivalently
`[2026-06-19T14:30:00Z, 2026-10-17T14:30:00Z)`. Last opening is 17 October
19:45 IST, closing at the exclusive end. This is archived coverage, not a fresh
price observation or retention/listing guarantee.

| Pair | Raw/CSV matches, completed 15m | Invalid OHLC/time/volume | Gaps / duplicates / incomplete | Explicit flat zero bars | Positive-volume shape only | Eligible strategy observations |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| I-BTC_INR | 11,520 | 0 | 0 / 0 / 0 | 6 | 11,514 | 0 |
| I-ETH_INR | 11,520 | 0 | 0 / 0 / 0 | 46 | 11,474 | 0 |
| I-SOL_INR | 11,520 | 0 | 0 / 0 / 0 | 23 | 11,497 | 0 |
| I-DOGE_INR | 11,520 | 0 | 0 / 0 / 0 | 195 | 11,325 | 0 |

Raw pages are strictly descending; normalized candles ascending, aware UTC and
15m aligned. All **46,080** OHLCV mappings match original responses. All 270 zero
bars are flat and explicit, not missing data defaulted to zero. Such records
are structurally valid for analysis; legitimate inactivity is possible but not
proven here. Existing strategy candles require positive volume and the default
policy permits no zero-volume fraction. These rules were not relaxed and zeros
were not dropped or replaced to join discontinuous history.

Each dataset independently retains `SOURCE_INGESTION_REJECTED`, `ZERO_VOLUME`
and `LIQUIDITY_REVIEW_REQUIRED`; ETH additionally `SOURCE_INTERVAL_MISMATCH`.
The ETH defect is not assumed to affect the other pairs. Wider cross-interval
consistency for those pairs remains UNVERIFIED; their own recorded failures
already prevent approval. Positive-volume shape counts are not qualified samples.

**Quote-volume observations: zero for every symbol (unavailable, not zero
liquidity).** Target-asset candle volume, including close×volume, cannot prove
executable INR liquidity. No historical verified quote-volume threshold,
spread/depth/impact evidence or authoritative trade completeness is available.
Current public instrument identity does not prove historical listings,
survivorship, constraints or costs. Review/eligibility flags cannot safely be
enabled on this evidence alone.

## Order feasibility, frozen rules and backtest decision

The [exact existing rules](PHASE8F_RULES.md) and
[pre-test source manifest](examples/phase8f-rules.json) remain unchanged.
SMA fast=5/slow=20 crossover and momentum lookback=12/threshold=0.01 are not
tuned. Historical entries require the next open after a closed-bar signal,
fresh central approval, a fixed modeled-entry 2% stop, adverse gap handling,
one long and all existing capital controls. SHORT can only exit a long.
Fees/slippage remain assumed 0.1% per side; funding/borrow/derivative execution
is unsupported, not fabricated. Fill/queue/partial-execution and intrabar path
are unverified limitations of the OHLC simulation.

The fixed chronology remains 2,880 bars each: warmup 19 June→19 July, train
19 July→18 August, validation 18 August→17 September, planned final test
17 September→17 October, each boundary 20:00 IST. No window was shortened,
optimized, or treated as a completed/untouched performance evaluation.

Unapproved sizing diagnostics reuse original prices at the 17 October
20:00 IST candle close and public metadata observed 20:08–20:09 IST. Default
requested margin remains INR 100 and leverage 1x. Genuine spot support stays 1x;
the maximum 3x ceiling does not grant permission for a leveraged spot product.

| Pair | INR reference | Quantity step / minimum quantity | Rounded quantity | Modeled notional = margin at 1x, INR | Estimated entry fee, INR | Result |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| BTC | 8221532.7 | 0.00001 / 0.00001 | 0.00001 | 82.297542327 | 0.082297542327 | NO_TRADE |
| ETH | 244000 | 0.0001 / 0.0000001 | 0.0004 | 97.6976000 | 0.0976976000 | NO_TRADE |
| SOL | 10477.2 | 0.001 / 0.01 | 0.009 | 94.3890948 | 0.0943890948 | NO_TRADE |
| DOGE | 8.0731 | 1 / 0.001 | 12 | 96.9740772 | 0.0969740772 | NO_TRADE |

Public minimum notional is INR 100 for all four, which every rounded candidate
fails; SOL also fails its quantity minimum. Values include assumed adverse
0.1% entry slippage and estimated entry fees are separate from margin. They are
not risk approvals, actual exchange costs or historical fills. Minimum-order
constraints were not bypassed by increasing margin/leverage. Snapshot arithmetic
cannot establish infeasibility at every historical price/contract.

**Backtests executed: 0; OOS evaluations executed: 0.** Net/gross P&L, win rate,
expectancy, profit factor, drawdown, exposure, benchmark and cost-sensitivity
results remain **unavailable/null**. This is not a zero-trade performance result.
Insufficient qualified data and executable-liquidity evidence alone block the
experiment; the default sizing snapshot adds a separate NO_TRADE condition.

## Tests and exact commands executed

All commands below ran from the repository root on the Linux environment above,
using the existing standard-library-only virtual environment.

| Run | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline full discovery | 633 | 0 | 0 | 1 | 634 | 16.137 |
| Focused data/interval/gate/sizing | 203 | 0 | 0 | 0 | 203 | 1.042 |
| Final public-enabled full discovery | **634** | **0** | **0** | **0** | **634** | **19.694** |

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_interval_trace tests.test_candle_semantics tests.test_data_pipeline tests.test_public_market_data tests.test_market_quality tests.test_central_risk tests.test_minimum_diagnostics -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m tools.phase8g_archive --output reports/phase8g-original
.venv/bin/python -m cli data validate --input reports/phase8g-verified/quarantine/I-ETH_INR.csv --as-of 2026-10-17T14:30:00+00:00
.venv/bin/python -m cli data import --input reports/phase8g-verified/quarantine/I-ETH_INR.csv --as-of 2026-10-17T14:30:00+00:00 --output reports/phase8g-verified/quarantine/I-ETH_INR.reimport.csv
```

The separate guarded Python invocation of the same archive `run` function wrote
`reports/phase8g-verified`; its forbidden calls and results are in the evidence.
Each helper output directory must be new. Expected CLI exits above are both 2.
An altered temporary ZIP was rejected with `ORIGINAL_ZIP_HASH_CHANGED`, before
output creation; no source or original archive changed.

The baseline skip was the opt-in public integration test; it ran and passed in
final discovery. No final-suite tests were skipped. That read-only public smoke
test verifies discovery/recent response parsing, not qualification of the ETH
archive or all source semantics. No private endpoint was called. All Phase 1–7
risk, persistence, worker, adapter and adversarial regressions are included.
No production defect was proven, so no existing code/test assertions were
changed. Existing 18 interval regressions (synthetic, from Phase 8E) remain in
the passing suite. New audit-tool normal/guarded, changed-archive and quarantine
paths were functionally checked against actual archived inputs; not every new
helper error branch has a dedicated unit test.

Local full-suite logs: `/tmp/phase8g-baseline.log`, `/tmp/phase8g-relevant.log`,
`/tmp/phase8g-full-public.log`. Logs/artifacts are workspace evidence and are not
automatically durable or published elsewhere.

### Native Windows commands (instructions, not executed here)

From the repository root in PowerShell with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
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

The second run needs public network access; default discovery intentionally
skips its one opt-in test. Archive reproduction additionally needs the original
ignored ZIP and prior Phase 8F rules/evidence JSON; it is not downloaded by the
unit tests. With those retained, use a new output directory:

```powershell
.\.venv\Scripts\python.exe -m tools.phase8g_archive --archive reports/phase8f-replay-inputs.zip --output reports/phase8g-local
```

Linux success does not certify native Windows, a personal installation or actual
exchange behavior. Earlier Phase 1 Windows evidence is not current-suite proof.

## Final diff, remaining prerequisites and phase boundary

Phase-local comparison uses the 135-file nonignored snapshot taken before this
task, including inherited untracked work; comparing HEAD alone would mix older
phases into this audit. Phase 8G adds only:

- `tools/phase8g_archive.py`: independent offline provenance/consistency audit
  and unchanged-value quarantine generation; no entry path or rule change.
- `docs/PHASE8G_AUDIT.md`: this report.
- `docs/examples/phase8g-evidence.json`: compact source, quarantine and test evidence.

Only inherited `README.md` and `VALIDATION.md` are updated. Other 133 inherited
files remain byte-identical, none deleted. Existing application/test/config/risk/
exchange code, original source archive/data and frozen rule fingerprints are
preserved. `git diff --check` and new-file whitespace/JSON/Python parsing checks
pass. Nothing was staged, committed or pushed. Existing Git exclusions retain
reports, local accounts/SQLite, `.env`/variants, credential/key paths; the tracked
`.env.example` contains only 20 blank BOT variable names. No tracked/staged real
`.env`, key or credential file was found, and changed files contain no detected
credential values. Pattern checks are not a guarantee about all external history.

Remaining work before any qualified backtest:

1. Obtain authoritative interval/revision/trade-population semantics or independent
   corroborating trade evidence for the affected ETH interval. Preserve original
   responses; keep the sample quarantined until justified requalification.
2. Supply history meeting the unchanged strategy's positive-volume/continuous
   warmup requirements and reliable source/listing/instrument identity. Do not
   manufacture replacement bars or relax zero-volume rules to force a pass.
3. Establish historically relevant executable-liquidity, constraints and cost
   evidence, then verify an entry fits the unchanged margin and risk rules.
4. Only after eligibility passes, run frozen chronological evaluation with
   explicit simulated-fill limits. Native Windows remains independently unverified.

Live/short entries stay disabled; no private integration, orders, credentials,
strategy tuning, paper worker startup or Phase 9. **Wait for explicit approval
before any subsequent phase.**
