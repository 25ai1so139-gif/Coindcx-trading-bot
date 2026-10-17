# Phase 8C — historical candle semantics and qualification

2026-10-17, Asia/Kolkata (IST). Existing branch phase2-market-data and inherited
working changes preserved; HEAD acde254c37b8f2f0fc84da00bd0a0012e2595cca.
Execution: **Linux 6.18.55 x86_64/glibc 2.41, CPython 3.12.14, SQLite 3.53.1**.
Current native Windows remains UNVERIFIED. No private endpoint/stream, credential,
real order, live/short enablement, parameter optimization or Phase 9 work occurred.

**Diagnosis and Linux safety/regressions: PASS within the evidence below.
Genuine no-trade causation: UNVERIFIED. Historical execution qualification:
BLOCKED; configured-size result: NO_TRADE for all four sampled markets.**
No genuine backtest or performance metric was generated.

## Gate 0 and confirmed rejection mechanism

Inspected Phase 8B's report/captures, actual public client, schema, normalization,
quality/CSV/cache, both strategy input requirements, sizing, gate, worker, state
interfaces, tests and official public documentation. Archived all 115 inherited
nonignored files before editing. Baseline discovery: 585 passed, 0 failed,
0 errors, 1 optional public skip (586 total).

The confirmed mechanism is **explicit source-reported zero volume entering an
unchanged strict positive-volume trading policy**. It is not a missing-value
default, symbol conversion, unit conversion or demonstrated pagination defect.
All **11,528 raw/normalized candles** across the four archived 2,882-row windows
match numerically. All **38 zero-volume rows** contain a literal numeric zero,
have flat O=H=L=C, and equal the preceding candle's close. The client did not
invent those flat prices or carry them forward itself.

That pattern is consistent with no reported trades and provider-supplied carried
prices. **It does not independently prove genuine inactivity**: both candle
intervals come from the same provider, and the official candle section does not
define a zero-volume/no-trade/outage convention. A same-provider response cannot
rule out upstream collection/aggregation failure. Do not call every zero corrupt,
and do not promote it to executable liquidity merely because it is well-formed.

## Actual public comparisons and raw evidence

Commands actually executed, each refusing to overwrite its output directory:

~~~bash
.venv/bin/python -m tools.phase8c_diagnose --source reports/phase8b-history --output reports/phase8c-diagnosis
.venv/bin/python -m tools.phase8c_diagnose --source reports/phase8b-history --output reports/phase8c-diagnosis-final
~~~

The first probe took 10.234s; the final probe took **11.780s**, captured through
**19:35:46.811677 IST** on 17 October. Each made 18 recorded public GETs (discovery,
four native-pair/instrument checks, direct candle and minute comparisons), all
HTTP 200. A separate two-request ETH recheck is described below. Optional public
unit integration/documentation requests are outside these probe manifests.

| Native pair | Archived zeros | Flat / equal prior close | Selected zero, IST | Exact direct/neighbor reproduction | Minute coverage / sum in selected zero |
| --- | ---: | --- | --- | --- | --- |
| I-BTC_INR | 1 | 1 / 1 | 11 Oct 05:30 | Both match archived source | 15 unique 1m bars / 0 BTC |
| I-ETH_INR | 4 | 4 / 4 | 14 Oct 04:45 | Both match archived source | 15 unique 1m bars / 0 ETH |
| I-SOL_INR | 4 | 4 / 4 | 16 Oct 03:00 | Both match archived source | 15 unique 1m bars / 0 SOL |
| I-DOGE_INR | 29 | 29 / 29 | 17 Oct 04:45 | Both match archived source | 15 unique 1m bars / 0 DOGE |

One most-recent zero per symbol was selected before comparing intervals. The
single request uses interval=15m, startTime=t, endTime=t+900000-1, limit=1.
The neighboring request uses t-900000 through t+1800000-1, limit=1000. The 1m
request uses that same 45-minute range. Each returned 45 unique diagnostic
minute records; neighboring intervals contained positive volume. Thus zero is
reproduced independently of the original 1,000-row page and cursor position,
and changing the documented interval yields the expected minute timestamps.
**1m is diagnostic only; configured strategies/timeframe remain 15m.**

Example actual BTC source object (not a synthetic fixture):

~~~json
{"open":"8240491.7","high":"8240491.7","low":"8240491.7","close":"8240491.7","volume":0,"time":1791676800000}
~~~

Its normalized record retains prices and volume exactly:

~~~json
{"timestamp":"2026-10-11T00:00:00+00:00","open":"8240491.7","high":"8240491.7","low":"8240491.7","close":"8240491.7","volume":"0","symbol":"I-BTC_INR","timeframe":"15m","quote_volume":""}
~~~

The timestamp is an opening time at 05:30 IST, not a closing time. An empty
quote_volume field means unavailable quote-turnover evidence; it is not replaced
with zero or close×volume. Source volume zero, missing volume and missing quote
volume have separate meanings.

## Separate source inconsistency: ETH positive-volume bar

For the following positive neighbor of the selected ETH zero, opening **14 Oct
05:00 IST** (2026-10-13T23:30:00+00:00), the 15m source volume is **0.086267 ETH**;
the 15 unique 1m volumes sum to **0.085028 ETH**, difference **0.001239 ETH**.
A separate fresh 15m request and a 1m request extending one minute on both edges
reproduced the difference. The edge minutes do not explain it. No duplicate,
missing or misaligned minute timestamp was involved. Across the final four
three-bar comparisons, 11 volume checks matched and this one differed.

This is an observed upstream cross-interval inconsistency, **not a diagnosed
internal normalization bug or an explanation for the zero bars**. The provider's
aggregation/revision mechanism remains UNVERIFIED; no undocumented rounding or
"repair" was assumed. Original values are retained. The derived ETH review adds
CROSS_INTERVAL_VOLUME_MISMATCH to a copy of ingestion annotations, producing
SOURCE_INTERVAL_MISMATCH. Original archived CSV/metadata/raw bytes are unchanged.

The independent recheck bytes/URLs/hashes remain under
reports/phase8c-diagnosis/eth-recheck. Its exact documented queries, also recorded
in the evidence, use I-ETH_INR and start=1791934200000: 15m through start+899999,
and 1m from start-60000 through start+959999, limit=1000. There was no private
endpoint or historical-trade reconstruction.

## Official source and candle contract

Official https://docs.coindcx.com/ returned HTTP 200 over verified TLS, 1,118,960
bytes, SHA-256
119d4d27b6acd365b1dbafbb0258df4464fd8c6e8bd0d47515c39c4b9dfb4c89.

| Public endpoint/source | Verified contract and evidence |
| --- | --- |
| GET https://api.coindcx.com/exchange/v1/markets ([markets](https://docs.coindcx.com/#markets)) | Current active symbol array; discovery agrees with details for all four native INR pairs; not historical listing-age proof |
| GET https://api.coindcx.com/exchange/v1/markets_details ([details](https://docs.coindcx.com/#markets-details)) | pair identifies ecode/target/base; target is traded asset, base is quote; quantity step/precision/min/max are asset units; min_notional is base/quote currency; active status and limit support checked |
| GET https://api.coindcx.com/market_data/candles ([candles](https://docs.coindcx.com/#candles)) | open/high/low/close/volume/time array; volume in target asset units; opening epoch milliseconds; descending order and unique time; intervals 1m/15m/1h/1d; limit default 500/max 1000, optional startTime/endTime |
| GET https://api.coindcx.com/market_data/trade_history ([trades](https://docs.coindcx.com/#trades), documentation only) | Most recent trades, limit default 30/max 500, no documented historical time-range parameters. Cannot certify those older intervals using invented time parameters; no request to this route was made |

All requests made by the tool use the original three-route unsigned GET client;
no credential inputs or authentication headers. The zero/no-trade convention,
server price-tick semantics, historical listing identity and independent trade
completeness are not established by these docs or by two same-source intervals.
Base-currency price precision is a conservative local check, not a verified tick.

The archived 15m windows have aligned UTC openings, coherent finite positive
OHLC, no missing intervals/duplicates/out-of-order times and only closed candles.
The end is exclusive; backward pagination uses oldest opening minus one ms and
keeps raw pages and duplicates visible. Tests cover missing keys/null values,
timestamp overflow/units, malformed OHLC, incomplete/future bars and page edges.
Historical symbol rebrands, delistings and survivorship remain UNVERIFIED.

## Explicit eligibility: three distinct layers

1. **Observation/schema:** CandleRecord accepts finite nonnegative volume,
   including a well-formed flat zero bar, retaining every observed value and
   timestamp. Missing/blank/null/malformed/nonfinite/negative volume is rejected,
   never coerced to zero. Malformed OHLC remains invalid even when volume is zero.
2. **Data-policy screen:** assess retains original reasons/counts and now adds
   volume_diagnostics with source activity UNVERIFIED. Flat zeros get
   ZERO_VOLUME_FLAT, nonflat zeros ZERO_VOLUME_PRICE_RANGE; both are
   QUARANTINED_FOR_TRADING. Invalid volumes get VOLUME_MISSING,
   VOLUME_MALFORMED, VOLUME_NONFINITE or VOLUME_NEGATIVE and invalid-record
   rejection. A known CROSS_INTERVAL_VOLUME_MISMATCH annotation now blocks
   eligibility with SOURCE_INTERVAL_MISMATCH. The report explicitly labels its
   scope DATA_POLICY_SCREEN_NOT_ENTRY_APPROVAL.
3. **Trading/backtesting:** Both existing SMA/momentum routes continue to need
   strict positive-volume, complete, unique/gap-free 15m trading candles,
   sufficient history (default 2,880), freshness capped at 30 minutes against
   the explicit evaluation clock, active INR identity, reliable reviewed metadata,
   independently justified quote liquidity, instrument/cost evidence and the
   unchanged central risk gate. DataPolicy research overrides cannot authorize
   an execution candle, bypass the CLI's strict policy or approve an order.

Existing explicitly opted-in research retention can describe zeros analytically;
it does not manufacture trades, positive liquidity, fills or missing prices.
No new automatic no-trade-bar exception was enabled for trading: genuine activity
semantics remain unverified, and the current fill/strategy model requires positive
volume. Removing zero rows would create gaps; inventing prices/volume or dropping
timestamps is not a repair. A future zero-bar execution model would need verified
semantics and separate tests/approval, not a policy relaxation to obtain trades.

| Pair | Data decision after diagnosis | Configured-size result |
| --- | --- | --- |
| BTC | BLOCKED: original ingestion rejection, ZERO_VOLUME, LIQUIDITY_REVIEW_REQUIRED | NO_TRADE |
| ETH | BLOCKED: same, plus SOURCE_INTERVAL_MISMATCH | NO_TRADE |
| SOL | BLOCKED: original ingestion rejection, ZERO_VOLUME, LIQUIDITY_REVIEW_REQUIRED | NO_TRADE |
| DOGE | BLOCKED: original ingestion rejection, ZERO_VOLUME, LIQUIDITY_REVIEW_REQUIRED | NO_TRADE |

Quote-liquidity evidence was not invented from asset volume. No symbol is
approved for a genuine backtest. The 30-day warmup-sized source window also does
not provide the existing three chronological evaluation periods plus warmup.
Real backtests/OOS runs, simulated trades and profitability results in this phase:
**none**. No claim is made about every other symbol/window on the exchange.

## Minimum-order diagnosis

Fresh public instrument metadata for all four markets agrees with active INR
identity/limit support. Source snapshots and hashes are in the evidence; actual
server acceptance/price tick/fee schedule remain UNVERIFIED.

| Pair | Quantity step | Minimum asset quantity | Minimum notional | Maximum asset quantity |
| --- | ---: | ---: | ---: | ---: |
| BTCINR | 0.00001 BTC | 0.00001 BTC | ₹100 | 2 BTC |
| ETHINR | 0.0001 ETH | 0.0000001 ETH | ₹100 | 20 ETH |
| SOLINR | 0.001 SOL | 0.01 SOL | ₹100 | 10000000 SOL |
| DOGEINR | 1 DOGE | 0.001 DOGE | ₹100 | 200000 DOGE |

Margin is reserved collateral; notional exposure is quantity×modeled entry and
margin is notional/leverage. At the configured 1x, ₹100 margin permits at most
₹100 exposure before down-rounding. Quantity is floored to the actual step;
it need not spend exactly ₹100. Thus a nominal ₹100 budget can fail a ₹100
minimum notional. SOL also has a 0.01-asset minimum above the rounded candidate.
Minimum quantity and step must both hold; the minimum need not itself be a step
multiple. This implementation supports reviewed real spot at 1x only; the 3x
absolute ceiling is not permission to infer a leveraged spot product.

Using the archived last closes (BTC 8215555.4, ETH 244280, SOL 10479.5, DOGE
8.0181 INR) and **unverified configured 0.1% adverse-entry slippage**:

| Pair | Existing down-rounded quantity | Candidate notional, INR | Theoretical stepped minimum quantity | Arithmetic minimum margin at 1x, INR |
| --- | ---: | ---: | ---: | ---: |
| BTC | 0.00001 | 82.237709554 | 0.00002 | 164.475419108 |
| ETH | 0.0004 | 97.8097120 | 0.0005 | 122.26214 |
| SOL | 0.009 | 94.4098155 | 0.01 | 104.899795 |
| DOGE | 12 | 96.3134172 | 13 | 104.3395353 |

These are **read-only hypothetical size explanations**, not recommended settings,
current tradable prices, approved limit prices or orders. Arithmetic minimum
margin excludes margin-plus-fee cash and other risk/market/precision checks.
exchange.diagnostics calls the existing size_position to explain the candidate
and actual minimum rejection. Exact rational ceiling arithmetic describes a
minimum step without rounding it down, but never changes configured size or
returns approval. Inadequate/unrepresentable sizes, weaker risk profiles and
unsupported real-spot leverage produce NO_TRADE; any available size is labeled
SIZE_ONLY_NOT_APPROVED with risk_approved=false. Quantity cannot be increased
to meet a minimum. All four actual diagnostics return NO_TRADE at unchanged
₹100 margin/1x. No margin, leverage, ₹10 budget or ₹20 ceiling was increased.

## Tests, failures encountered and final verification

| Run on Linux | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline default discovery | 585 | 0 | 0 | 1 | 586 | 18.490 |
| Initial 26 new methods | 25 | 0 | 1 | 0 | 26 | 0.047 |
| Corrected new methods + existing data group | 95 | 0 | 0 | 0 | 95 | 0.211 |
| Intermediate full public-enabled discovery | 612 | 0 | 0 | 0 | 612 | 19.968 |
| Final data/diagnostic group, with interval guards | 99 | 0 | 0 | 0 | 99 | 0.223 |
| **Final full public-enabled discovery** | **616** | **0** | **0** | **0** | **616** | **19.598** |

One new test initially used a one-unit lot where even one unit exceeded its
₹10 risk budget, then incorrectly indexed an unavailable candidate. The fixture
was corrected to a 0.01 lot to test a nonzero risk-capped candidate. No production
rule/assertion was weakened. Four subsequent tests cover the discovered interval
discrepancy, exact zero agreement, bad minute coverage and quarantine propagation.
All 30 new methods and every inherited test pass in final discovery.

Exact test commands (rerun after the relevant changes):

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_candle_semantics tests.test_minimum_diagnostics -v
.venv/bin/python -m unittest tests.test_candle_semantics tests.test_minimum_diagnostics tests.test_market_quality tests.test_data_pipeline tests.test_public_market_data -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
git diff --check
~~~

The optional public test was the only default skip and actually passed in final
enabled discovery; no available Linux test remained unrun/skipped. Existing risk,
stop, fee/slippage, leverage, per-trade/daily/entry-count limits, duplicate/open
position, durable recovery/halting, unknown-order and zero-order manual/verify
tests all remain in the full suite. New fixtures are explicitly SYNTHETIC and
never treated as market evidence. No native Windows or private/live test ran.

Logs are /tmp/phase8c-baseline.log, phase8c-new-tests.log,
phase8c-data-final.log, phase8c-full-public.log, phase8c-data-final2.log and
phase8c-full-public-final.log. Wrappers preserved the actual Python exit code.
The prior Phase 8B paper account was reopened: ₹2,000, zero processed candles,
emergency halt true and identical file SHA-256 before/after. No reset occurred.

## Changed files, preservation and final status

| Path | Phase 8C change |
| --- | --- |
| data/diagnostics.py (new) | Static malformed/zero classifications and exact same-source interval-volume comparison; no repair/authorization |
| data/quality.py | Per-record volume diagnostics, explicit scope and a stricter known-source-mismatch quarantine; original zero/stale/history/liquidity checks preserved |
| exchange/diagnostics.py (new) | Pure minimum-size explanation using original sizing; exact stepped minima, no approval or configuration mutation |
| tools/phase8c_diagnose.py (new) | Bounded archived/raw/normalized/direct/minute/instrument evidence capture over whitelisted public GETs |
| tests/test_candle_semantics.py (new) | 21 deterministic synthetic semantics/pagination/interval/quarantine methods |
| tests/test_minimum_diagnostics.py (new) | 9 deterministic synthetic sizing/boundary/risk/precision/zero-order methods |
| docs/examples/phase8c-evidence.json (new) | Actual source examples, hashes, comparisons, qualification/sizing decisions and preserved-account evidence |
| docs/PHASE8C_AUDIT.md (new) | This report and rules |
| README.md / VALIDATION.md | Latest results and limitations; earlier records retained |

Phase-local diff is against /tmp/phase8c-before.zip, including inherited
untracked files, not just HEAD. Three inherited files modified, seven added,
**112 inherited files byte-identical**, none deleted. All old test assertions,
config/risk/sizing/gate/broker/state/persistence/session/strategy/transport/schema
sources are unchanged; persisted trading fingerprints remain compatible.
No dependencies, credentials, .env.example or permissions changed. No source
was staged/committed/pushed. Raw/public captures and databases remain ignored;
20 BOT_* placeholders stay blank. Current filename/pattern/index checks are not
a comprehensive Git-history or unknown-secret-format audit.

| Requirement | Status | Evidence / remaining limit |
| --- | --- | --- |
| Preserve fixed simulation/risk/live-disabled configuration | PASS | Core source/fingerprints unchanged; all old regressions and prior-account reopen pass |
| Identify source of zero values / exclude mapping/defaulting/pagination defects in sampled records | PASS | All 11,528 exact normalized matches, 38 explicit flat zeros, four direct/neighbor/minute checks |
| Independently prove genuine no-trade versus upstream outage/aggregation behavior | UNVERIFIED | No official zero convention or historical trade-level corroboration; same-provider intervals are not independent proof |
| Timestamp/OHLC/volume/missing/duplicate/completed semantics | PASS for tested samples/implementation | Raw evidence and synthetic adversarial tests; no source or timestamp repair |
| Source interval consistency | BLOCKED | ETH positive volume discrepancy persists; precise upstream cause unknown, affected source quarantined |
| Explicit strategy-specific eligibility/quarantine | PASS | Structural retention distinguished from strict SMA/momentum trading; no zero/stale/minimum relaxation |
| Minimum-order explanation without automatic enlargement | PASS | Verified public fields, existing arithmetic and tests; all four configuration outcomes NO_TRADE |
| Full Linux regression/adversarial verification | PASS | 616 passed, 0 failed/errors/skipped |
| Native Windows current source | UNVERIFIED | Linux only; commands below, no Windows pass inferred |
| Genuine historical backtest/OOS now possible on these sources | BLOCKED | Zero trading exclusions, unqualified quote liquidity/metadata, ETH inconsistency, inadequate evaluation periods and configured-size minima remain |
| Private/real orders/Phase 9 | PASS for disabled scope | No credentials/private network/real orders or subsequent phase enabled |

Compact evidence: [phase8c-evidence.json](examples/phase8c-evidence.json).
Full raw bodies/manifests remain under reports/phase8c-diagnosis-final; the original
Phase 8B source must also be retained for exact archived comparison. Hashes prove
content identity, not authenticated market-trade completeness. Do not erase bars,
fill gaps, substitute 1m-derived values, or invent quote liquidity to pass a gate.

Remaining work is independent source clarification/corroboration, qualification
of quote liquidity/instrument/cost assumptions and listing history, sufficient
predeclared chronological history, feasible requested sizes under existing
limits, and actual Windows evidence. No profitability or live readiness follows
from software tests, observed no-volume patterns or theoretical minimum sizing.

## Windows PowerShell verification instructions only

Run from a native Windows checkout with Python 3.12 and Git. These commands have
not been executed on Windows here; do not copy the Linux .venv or reset accounts.

~~~powershell
$env:PYTHONUTF8 = '1'
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
.\.venv\Scripts\python.exe -m pip install --no-index --no-cache-dir -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency check failed' }
.\.venv\Scripts\python.exe -c "import sys,platform,sqlite3; print(platform.platform()); print(sys.version); print(sqlite3.sqlite_version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3,12)"
if ($LASTEXITCODE -ne 0) { throw 'native Windows/Python 3.12 required' }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'offline tests failed' }
$env:COINDCX_RUN_PUBLIC_INTEGRATION = '1'
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'public-enabled tests failed' }
} finally {
    Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
}
~~~

This completes Phase 8C only. Await explicit approval for further work; Phase 9
and private/live operations remain disabled.
