# Phase 8D — historical readiness and order feasibility

17 October 2026, Asia/Kolkata (IST). This audit continues the existing checkout;
no project recreation, Phase 9 work, strategy tuning, private request, credential,
real order, or live/short enablement. **Linux regressions PASS. Genuine historical
backtesting and order feasibility BLOCKED: all four configurations are NO_TRADE.**
Passing tests do not establish profitability or live readiness.

Actual environment: Linux 6.18.55 x86_64/glibc 2.41, CPython 3.12.14,
SQLite 3.53.1, existing .venv, standard library only. Current native Windows
execution is **UNVERIFIED**; no Windows runner was available or used. Earlier
Phase 1 Windows evidence does not cover this revision.

## Gate 0 and scope

Reviewed [Phase 8B](PHASE8B_AUDIT.md), [Phase 8C](PHASE8C_AUDIT.md), their retained
public evidence, and actual config, data client/schema/quality/CSV loader,
instrument and sizing diagnostics, central gate, broker, persistence/worker,
CLI, chronological splits/evaluation and related tests. The previous 30-day
sample was insufficient for default warmup plus three evaluation periods; the
zero-trade paper run was rejection evidence only.

No inherited application code, tests or risk settings changed in Phase 8D.
No new production defect was confirmed; the existing source-quality and
minimum-size blockers were reproduced rather than bypassed.
The new diagnostic tool explicitly uses Settings() defaults, not BOT_* overrides:
₹2,000 initial simulated equity, ₹100 requested margin, 1x configured leverage,
3x hard ceiling, 15m, ₹10 initial planned-risk budget, ₹20 absolute ceiling,
daily loss halt at min(₹40, 2% of applicable daily starting equity), three entries
per UTC day, one open position, emergency halt and short entries disabled.
The central gate remains authoritative; a pure sizing result is never approval.

## Genuine historical coverage

Executed the bounded command:

~~~bash
.venv/bin/python -m tools.phase8d_readiness --output reports/phase8d-readiness
~~~

The four BTC/ETH/SOL/DOGE INR assets and 120-day/split plan were fixed and written
before this fetch. Capture ran **19:51:58.799593–19:52:38.588535 IST**,
39.788943 seconds: **54 unsigned public API GETs, all HTTP 200**, including 12
candle pages per asset and public discovery/instrument metadata. No synthetic
candles, interpolation, source repair, gap filling or return-based asset selection.
This is a fixed four-asset sample, not an exhaustive exchange/history survey.

For every pair, the exact requested range is **19 June 2026 19:45 IST through
17 October 2026 19:45 IST, end exclusive**. First opening is 19 June 19:45 IST;
last opening is 17 October 19:30 IST, closed at 19:45 IST. Machine evidence uses
explicit UTC: [2026-06-19T14:15:00+00:00, 2026-10-17T14:15:00+00:00).

| Native pair | Genuine rows / completed | Invalid OHLC/time/volume | Missing / duplicate / incomplete | Zero-volume bars | Longest consecutive positive-volume run | Trading eligibility |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| I-BTC_INR | 11,520 / 11,520 | 0 | 0 / 0 / 0 | 6 | 6,060 | BLOCKED |
| I-ETH_INR | 11,520 / 11,520 | 0 | 0 / 0 / 0 | 46 | 1,910 | BLOCKED |
| I-SOL_INR | 11,520 / 11,520 | 0 | 0 / 0 / 0 | 23 | 4,503 | BLOCKED |
| I-DOGE_INR | 11,520 / 11,520 | 0 | 0 / 0 / 0 | 195 | 959 | BLOCKED |

All source pages were descending as documented; normalization is ascending,
UTC/aligned, and gaps/duplicates remain visible. **All 46,080 raw records match
their CSV OHLCV numerically exactly.** Every overlapping Phase 8B record also
matches: 2,882 per pair, 11,528 total, no observed revisions in that overlap.
The 270 zeros are all structurally valid flat bars, classified ZERO_VOLUME_FLAT.
They are retained as source observations and quarantined for trading. Positive
asset volume alone is not independently qualified quote liquidity. The longest
runs above are coverage diagnostics, not selected strategy/performance samples;
none can supply the unchanged full 11,520-bar evaluation requirement.

Every primary assessment rejects ZERO_VOLUME and LIQUIDITY_REVIEW_REQUIRED.
quote_volume is unavailable; quote_volume_verified and quality_reviewed remain
false. Asset volume is not relabeled INR volume or multiplied by closing price
to invent exact turnover. Dropping zero rows would introduce gaps. The source's
genuine-inactivity versus upstream no-data convention remains UNVERIFIED; no new
exception to strict strategy/execution policy was introduced.

The known ETH inconsistency was independently re-fetched through public GETs:
the 15m bar opening **14 October 2026 05:00 IST** (2026-10-13T23:30:00Z) still
reports **0.086267 ETH**, while its 15 unique complete 1m volumes sum to
**0.085028 ETH**, difference **0.001239 ETH**. These two additional requests
returned HTTP 200. The same 15m value is present in the new 120-day dataset.
The derived review adds CROSS_INTERVAL_VOLUME_MISMATCH, yielding
SOURCE_INTERVAL_MISMATCH. Original raw bodies, CSV and sidecar are unchanged.
This is same-provider diagnostic evidence, not independent trade corroboration;
the upstream aggregation/revision cause remains unknown. ETH remains quarantined.

### Provenance and official contracts

Official [CoinDCX documentation](https://docs.coindcx.com/) was retrieved with
verified TLS: HTTP 200, 1,118,960 bytes, SHA-256
9171ab097c2b6b495b2d59fe353448aa4ab5b2ddb42b53f3b8ee560a94baf7fc.
Snapshot/extracted sections: reports/phase8d-official-docs.

| Source | Verified contract / actual use |
| --- | --- |
| [Markets](https://docs.coindcx.com/#markets), GET https://api.coindcx.com/exchange/v1/markets | Active name array; unsigned successful discovery, no account/key |
| [Market details](https://docs.coindcx.com/#markets-details), GET https://api.coindcx.com/exchange/v1/markets_details | Exact pair, active symbol/asset/quote identity, quantity constraints and limit-order support; fresh public snapshots retained |
| [Candles](https://docs.coindcx.com/#candles), GET https://api.coindcx.com/market_data/candles | open/high/low/close/volume/time; opening epoch ms, volume in target asset; descending unique times; intervals 1m/15m/1h/1d; optional startTime/endTime, limit default 500/max 1000 |
| [Spot order-update documentation](https://docs.coindcx.com/#get-order-update), documentation only | fee_amount is charged in base/quote currency; no private stream contacted, fee tier/rounding/actual settlement not established |

Each dataset is genuine CoinDCX public-response provenance, bound by the exact
native pair query plus current active discovery. Responses contain no per-row
symbol identity. Historical listing/rebranding/delisting identity, venue trade
completeness and listing-time universe/survivorship remain UNVERIFIED. No exchange
retention guarantee is inferred from a successful 120-day request.

Raw responses, exact query URLs, UTC fetch times, SHA-256, normalized CSVs,
original-rejection schema-2 sidecars/reports and the pre-fetch plan are retained
under ignored reports/phase8d-readiness. Per-dataset CSV SHA-256:

| Pair | SHA-256 |
| --- | --- |
| BTC | 6740a986f5e4d6bba3ccb6008c6dccf25086089b421cd63a6ef7c94864efef21 |
| ETH | de70ac1a75d70c757e185983bc2a0ba0ebda848de0abca7b7829b2baa08400a5 |
| SOL | fb6a8521d0452026d73f64bd94bc7a6cff26e61d2a1a4e1b32d435c27cd39145 |
| DOGE | 1446c430670e05cf66fde0d1127174b7f28297d3c718d3bbc93a48b785c7429c |

Hashes establish byte identity, not authenticated market activity. The compact
[evidence](examples/phase8d-evidence.json) contains full page
hashes, request manifests, constraints, observations and exact cost arithmetic;
no Git commit/push was made. Retain the ignored source archive for exact replay.

## ₹100 margin feasibility

Observation prices are completed candle closes, **not executable quotes**. All
four are the bar opened **17 October 2026 19:30 IST**, closed **19:45 IST**;
capture began 6 minutes 58.799593 seconds after close. Fresh instrument snapshots
were observed at BTC 19:52:09.701750, ETH 19:52:19.219988, SOL 19:52:29.652849,
DOGE 19:52:38.584522 IST. They are historical audit observations, not current
permission to reuse stale metadata for an entry.

The configured leverage is **1x**. Genuine spot is supported at 1x only in the
existing gate/adapter; a 3x absolute ceiling does not supply a verified leveraged
product. No leverage/margin setting was increased. Quantity step/min/max are
target-asset units; min_notional is API base currency, INR for these pairs.

| Pair | Reference price, INR | Step | Minimum quantity | Maximum quantity | Min notional, INR | Asset / quote decimals |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTC | 8,179,818 | 0.00001 | 0.00001 | 2 | 100 | 5 / 1 |
| ETH | 242,675 | 0.0001 | 0.0000001 | 20 | 100 | 4 / 1 |
| SOL | 10,414.8 | 0.001 | 0.01 | 10000000 | 100 | 3 / 1 |
| DOGE | 8.0094 | 1 | 0.001 | 200000 | 100 | 0 / 4 |

The documented decimal fields do not independently establish a server price
tick. Estimated slipped fills below are not validated limit-order prices.
The minimum quantity need not be a step multiple; both constraints must hold.

The unchanged model assumes **0.1% adverse slippage and 0.1% fee on each side**.
Estimated entry = reference × 1.001; stop trigger = estimated entry × 0.98;
no-gap stop fill = stop trigger × 0.999. Quantity is rounded DOWN using the
existing size_position, accounting for collateral/cash and risk. No minimum is
satisfied by increasing quantity above the configured budget.

| Pair | Estimated entry, INR | Rounded candidate quantity | Candidate notional / margin at 1x, INR | Smallest stepped minimum quantity | Arithmetic minimum margin at 1x, INR | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTC | 8187997.818 | 0.00001 | 81.87997818 / 81.87997818 | 0.00002 | 163.75995636 | NO_TRADE |
| ETH | 242917.675 | 0.0004 | 97.1670700 / 97.1670700 | 0.0005 | 121.4588375 | NO_TRADE |
| SOL | 10425.2148 | 0.009 | 93.8269332 / 93.8269332 | 0.01 | 104.252148 | NO_TRADE |
| DOGE | 8.0174094 | 12 | 96.2089128 / 96.2089128 | 13 | 104.2263222 | NO_TRADE |

Notional = quantity × modeled entry; required margin = notional / leverage.
At 1x they coincide, but they remain distinct concepts. A ₹100 margin ceiling
does not imply spending exactly ₹100. Each rounded candidate is below ₹100
minimum notional; SOL additionally fails minimum quantity. The next permitted
lot exceeds the ₹100 margin ceiling. The arithmetic minimum column excludes
fees/cash and other approval checks and is **not a recommendation or new setting**.
No compliant order exists for these observed prices under the current setup.

| Pair | Entry fee | Stop exit fee | Round-trip fees at stop | Entry / stop slippage cost | Margin + entry fee | Modeled planned stop risk |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| BTC | 0.08187997818 | 0.0801621362377836 | 0.1620421144177836 | 0.08179818 / 0.0802423786164 | 81.96185815818 | 1.8798840566341836 |
| ETH | 0.0971670700 | 0.095128504871400 | 0.192295574871400 | 0.0970700 / 0.095223728600 | 97.2642370700 | 2.230860703471400 |
| SOL | 0.0938269332 | 0.091858444141464 | 0.185685377341464 | 0.0937332 / 0.091950394536 | 93.9207601332 | 2.154174435877464 |
| DOGE | 0.0962089128 | 0.094190449809456 | 0.190399362609456 | 0.0961128 / 0.094284734544 | 96.3051217128 | 2.208862353153456 |

All amounts in this table are INR, hypothetical estimates, **not charged fees,
fills or returns**. Exact rational reconciliation independently checked the
cost/notional/margin identities against the captured candidates. The modeled
stop risks are below ₹10/₹20 but do not constitute compliance/approval: minimums
and market eligibility fail, and this calculation has no actual account/day/
position/halt state. Gap losses can exceed planned risk. No risk approval requested.

Actual fee schedule/taxes/fee rounding, executable bid/ask spread, impact,
partial fills and historical instrument constraints remain unqualified. Funding
is not modeled; this is spot, with no verified derivatives/borrow product or
funding history. An example stream fee percentage is not a universal fee tier.
These limits would need resolution before calling a backtest execution-realistic.

## Backtest decision and chronological plan

**BLOCKED. Genuine backtests executed: 0. OOS evaluations executed: 0.** Real
trade count, net P&L, drawdown, expectancy, profit factor and benchmark comparison
are **unavailable**, not fabricated zeros. No synthetic fixture/report was
relabeled real. No paper session or account mutation was used for this audit.

The requested history now has sufficient nominal duration for the unchanged plan:

| Segment, end exclusive | IST boundaries | Bars |
| --- | --- | ---: |
| Prior warmup | 19 June 19:45 → 19 July 19:45 | 2,880 |
| Train | 19 July 19:45 → 18 August 19:45 | 2,880 |
| Validation | 18 August 19:45 → 17 September 19:45 | 2,880 |
| Test | 17 September 19:45 → 17 October 19:45 | 2,880 |

All dates are 2026. The plan is prospective for an evaluation that has not run;
it is not proof of a previously blinded/OOS experiment. Data-quality inspection
is not parameter selection. No strategy parameters, split minima or risk limits
were tuned, and no performance-based selection was performed. Every dataset
still fails strict strategy data requirements and lacks reviewed liquidity/
instrument context; every current configured order size fails exchange minima.
The actual backtest loader rejects all four, first at the missing explicit
historical quality-review requirement. No review flag was set just to continue.

## Tests and rejection verification

| Actual Linux run | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full default baseline | 615 | 0 | 0 | 1 | 616 | 30.489 |
| Central risk/recovery/worker/exchange adversarial group | 335 | 0 | 0 | 0 | 335 | 21.070 |
| **Final full public-enabled discovery** | **616** | **0** | **0** | **0** | **616** | **40.848** |
| Native Windows | N/A | N/A | N/A | Not executed | N/A | N/A |

Exact test commands, from repository root:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_exchange_adapter tests.test_order_reconciliation tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
git diff --check
~~~

The sole baseline skip is test_discovery_and_recent_candles, optional unsigned
public access. It actually passed in final discovery. No available Linux test
remained unrun/skipped; no test failed. Current native Windows, private/server
execution, physical power-loss and real-market performance were not tested.
Existing deterministic synthetic tests exercise accounting/control logic only.
No new test or existing assertion was altered in Phase 8D. The new diagnostic's
normal successful-public-response path and costs were functionally checked on
actual captured responses. Four additional offline functional checks passed:
existing evidence refuses overwrite without a hash change; future and misaligned
cutoffs reject before directory creation; missing candidates produce no cost
estimate. They made zero network requests and are not added to unittest counts.
Not every new tool error branch was separately unit-tested; inherited client
retry/error controls remain covered by the suite.

Logs: /tmp/phase8d-baseline.log, /tmp/phase8d-safety.log,
/tmp/phase8d-full-public.log. Python exit statuses were preserved, e.g.:

~~~bash
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v > /tmp/phase8d-full-public.log 2>&1
result=$?; tail -n 6 /tmp/phase8d-full-public.log; exit "$result"
~~~

All four actual CSV re-imports returned **exit 2, eligible=false**, retaining
SOURCE_INGESTION_REJECTED, ZERO_VOLUME and LIQUIDITY_REVIEW_REQUIRED. These are
expected safety rejections, not failed unit tests. Equivalent exact commands:

~~~bash
.venv/bin/python -m cli data validate --input reports/phase8d-readiness/I-BTC_INR.csv --as-of '2026-10-17 14:15:00+00:00'
.venv/bin/python -m cli data validate --input reports/phase8d-readiness/I-ETH_INR.csv --as-of '2026-10-17 14:15:00+00:00'
.venv/bin/python -m cli data validate --input reports/phase8d-readiness/I-SOL_INR.csv --as-of '2026-10-17 14:15:00+00:00'
.venv/bin/python -m cli data validate --input reports/phase8d-readiness/I-DOGE_INR.csv --as-of '2026-10-17 14:15:00+00:00'
~~~

Exact child argv/results, raw-normalized verification and rational cost checks
are in reports/phase8d-readiness/verification.json. The additional ETH review
and direct/minute raw responses are retained in the same archive. A future API
refetch with --end 2026-10-17T14:15:00+00:00 fixes the window but cannot guarantee
the provider never revises history; keep the original hashed bytes for identity.

## Safety matrix and remaining prerequisites

| Requirement | Status | Implementation / evidence and remaining scope |
| --- | --- | --- |
| Gate 0 actual Phase 8B/8C/code review | PASS | Previous limits and blocked evidence inspected; complete current Linux baseline/final runs |
| Genuine 15m acquisition, provenance and nominal 120-day coverage | PASS | Four active INR pairs, 46,080 raw/normalized matches, exact ranges/page/CSV hashes |
| Timestamp/OHLC/gap/duplicate/incomplete checks | PASS | All four sampled windows have no structural errors; existing adversarial pipeline tests pass |
| Zero-volume semantics independently prove genuine no-trade intervals | UNVERIFIED | Explicit source zeros retained; no independent historical trades/source guarantee |
| Eligible data for existing SMA/momentum and chronological backtest | BLOCKED | Zero exclusions, missing verified quote liquidity/review, ETH interval inconsistency |
| Public quantity/minimum/currency constraint diagnosis | PASS | Fresh official public details, source-defined asset steps and INR minima; no automatic enlargement |
| ₹100 configured margin order feasibility | BLOCKED | All four NO_TRADE: down-rounded notional < ₹100, SOL also below min quantity |
| Realistic actual exchange costs/server price ticks/historical instrument constraints | UNVERIFIED | Explicit configured estimates only; no private request or invented market evidence |
| Backtest and untouched OOS performance/benchmark evidence | BLOCKED | No eligible data/configuration; metrics unavailable, no experiment executed |
| ₹2,000 starting equity / ₹10 initial planned risk / ₹20 cap | PASS | config.py, risk/entry.py and risk/sizing.py unchanged; boundary/adversarial tests pass |
| 3x ceiling, margin vs notional, real spot limited to 1x | PASS | Settings validation, gate leverage checks and exchange diagnostics/tests; no 3x real-product inference |
| Daily min(₹40,2%) halt and maximum 3 UTC-day entries | PASS | risk/controls.py and gate; persisted/restart/daily-threshold tests pass |
| One open position, stop validation, emergency halt, shorts disabled | PASS | Sole broker entry calls fresh gate; repeated/direct/bare-buy/short attempts and emergency tests pass |
| Persistent halt/restart/duplicate protections and failure-closed entries | PASS for tested offline APIs | SQLite and managed-session regression/process-death tests; physical crash/storage/long-hosting evidence not asserted |
| manual/verify zero orders and private/live execution disabled | PASS | Existing CLI/gate/adapter tests; diagnostic never creates broker/account/order transport |
| Full available Linux regression suite | PASS | 616 passed; 0 failures/errors/skips, optional public test included |
| Current native Windows | UNVERIFIED | No native execution; commands below are instructions only |
| Secret exclusion / preserved source and Git changes | PASS within checked scope | No staged files or tracked .env/known secret paths; .env.example remains 20 blank BOT_* names; no comprehensive unknown-secret/history guarantee |
| Phase 9 / private operations | BLOCKED | Outside authorization; remain disabled |

Remaining prerequisites: independent clarification/corroboration of source
activity and ETH aggregation, reliable reviewed quote-liquidity/listing history,
eligible contiguous history, documented execution costs/precision and a feasible
requested configuration approved without weakening current limits. No margin or
leverage increase is proposed/applied. Current native Windows and any sustained
paper stability require separate actual evidence. Unit passes are not market
qualification or profitability. Phase 8D is complete as an audit; readiness is
BLOCKED, and further phases require explicit approval.

## Changed files and final review

- tools/phase8d_readiness.py (new): bounded public capture/pre-fetch split plan,
  production quality/CSV/sizing reuse and labeled two-sided estimated costs;
  no authorization, orders, account changes or backtest calls. Exit 0 means
  evidence capture completed, not data qualification.
- docs/PHASE8D_AUDIT.md and docs/examples/phase8d-evidence.json (new): report,
  actual observations/constraints/hashes, verification and tests.
- README.md / VALIDATION.md: latest evidence pointer and explicit blockers;
  older phase records preserved.

Phase-local comparison uses /tmp/phase8d-before.zip, including inherited untracked
work, rather than only HEAD. Final comparison: two inherited documentation files
modified, three new files, **120 inherited files byte-identical**, none deleted.
All existing production code, tests, dependency files, .gitignore, .env.example
and fingerprint-bound trading/persistence sources remain unchanged. No existing
paper balance/halt was reset. No files staged, committed or pushed. Public
captures/databases remain ignored; no indefinite process was started.

## Native Windows PowerShell instructions — not executed here

From a native Windows checkout with Python 3.12/Git, without copying Linux .venv:

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
# Optional bounded public capture: choose a NEW output directory every time.
.\.venv\Scripts\python.exe -m tools.phase8d_readiness --output reports/phase8d-local --end 2026-10-17T14:15:00+00:00
if ($LASTEXITCODE -ne 0) { throw 'capture failed; inspect error, do not reset accounts' }
~~~

The capture command makes no orders and its zero exit does not imply eligibility.
Inspect each quality report/NO_TRADE result. No real-market backtest is executed
by these verification commands.
