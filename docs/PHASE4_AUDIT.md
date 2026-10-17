# Phase 4 audit — realistic backtesting and out-of-sample validation

Date: 2026-10-17. Existing repository: 25ai1so139-gif/Coindcx-trading-bot,
branch phase2-market-data, starting HEAD acde254c37b8f2f0fc84da00bd0a0012e2595cca.
Environment: Linux 6.18.55, x86_64, Python 3.12.14 in the existing .venv.
No native Windows Phase 4 test was run. No commit, push or Phase 5 work.

**Framework and safety verification: PASS. Real-market performance and
out-of-sample evidence: BLOCKED because no eligible real dataset exists.**
Synthetic workflows below exercise the software only. No fabricated market
performance, profitability, private endpoint access or real order is claimed.

## Gate 0 and requirement statuses

Inspected PHASE1_AUDIT.md, docs/PHASE2_AUDIT.md and docs/PHASE3_AUDIT.md, plus
their validation/data documentation. Phase 2's earlier CONNECT-403 limitation
was superseded by Phase 3's documented canonical-endpoint correction and actual
public test. The Phase 3 final record contains 206 passing enabled tests. This
was not accepted solely from publishing: the current baseline was rerun first.

| Requirement | Status | Evidence / limits |
| --- | --- | --- |
| Gate 0: prior audits, baseline safety/data/strategies | PASS | Baseline 205 passed, 0 failed/errors, 1 opt-in skip; original groups subsequently pass independently; public smoke passes. No critical offline failure remained before implementation. |
| 1: engine sequencing/accounting/risk audit | PASS | Existing engine/broker extended incrementally; next-open, completed prefix, stops/gaps, risk ceilings, one long, UTC daily limits, emergency and cash reconciliation tested. Intrabar timing/latency limitations remain explicit. |
| 2: configurable costs and honest assumptions | PASS | Shared fee/slippage formulas, both fill references and cost ledger, explicit unverified assumptions, higher-cost replay; spread/funding/partial-fill execution is unavailable without supporting history and is not invented. |
| 3: eligibility before simulation | PASS | Strict Phase 2 assessment now also covers legacy CLI backtest/paper files; corrupt, incomplete, duplicate, insufficient and unqualified liquidity data blocks. No missing prices are fabricated. |
| 3: actually eligible real historical data | BLOCKED | All inspected local datasets are synthetic. Public candles supply asset volume, not independently verified quote turnover. No real coin is declared qualified. |
| 4: chronological splitting and leakage prevention | PASS | Explicit half-open UTC ranges, no shuffle, prior-only warmup, independent flat accounts, end liquidation with costs, exact coverage/minimum samples; tests cover boundary and future-price behavior. Baseline parameters fixed; sensitivity never evaluates test. |
| 4: meaningful untouched real-market test | BLOCKED | No eligible real data. Untouched-test discipline across operator reruns is procedural, not authenticated/enforced history. No actual market out-of-sample result is claimed. |
| 5: numerical performance metrics | PASS | Independent synthetic ledger expectations, drawdown, accounting, costs, zero trades, no losses, streaks, exposure and activation tests pass. Undefined values remain null; annualized/risk-adjusted metrics are NOT_ESTIMATED. |
| 6: benchmark/robustness implementation | PASS | Same-period observed-price 1x buy/hold and cash references, cost stress, predefined development-only parameter alternatives; different benchmark risk exposure is explicit. No parameter selection occurs. |
| 6: real-market benchmark/regime/concentration conclusions | BLOCKED | No qualified real sample or multi-symbol/regime evidence. Synthetic comparisons do not establish robustness, superiority or future profitability. |
| 7: reproducible JSON/CSV/Markdown reports | PASS | Full settings/parameters, source and quality, hashes, ranges/warmup, costs, activations, limitations, synthetic labels, deterministic run ID; identical-input byte comparisons tested; no overwrite. |
| 8: full tests and regressions | PASS | 269 passed, 0 failures, 0 errors, 0 skipped with public integration enabled. Phase 1/2/3 groups separately passed 82/69/54. |
| 8: native Windows execution of current code | BLOCKED | Linux host only. Exact PowerShell commands below; earlier Phase 1 Windows CI is not evidence for this code. |
| No live/private/short execution; unchanged protection ceilings | PASS | Both manual aliases remain zero-order and broker-free in tests; SHORT only exits an existing long in replay. Settings reject live and >3x; existing limit/stop/emergency tests pass. |
| Final diff, secret exclusions and preservation | PASS | Pre-edit archive comparison includes untracked files; no preexisting files deleted, zero staged paths, whitespace/hygiene tests pass; current-file pattern scan found no common secrets. |

The absence of real liquidity evidence blocks the affected market evaluations,
not the labelled deterministic framework work explicitly requested for Phase 4.

## Confirmed finding, changes and reasons

The legacy loader checks provenance review and structure but does not require
verified quote turnover for legacy historical metadata. Before Phase 4, the
backtest/paper CLI called only that loader, while manual verification also
performed strict Phase 2 assessment. That inconsistency could portray
unqualified legacy data as an eligible simulation input. It was identified by
inspection and existing loader behavior. The new backtesting/datasets.py gate
composes the existing loader with read_csv/assess, enforces the stricter
history/completeness/volume/liquidity rules and binds the assessed snapshot to
its canonical data digest. Both old simulation commands now reject the fixture
case before constructing a broker, including a requested liquidity bypass.
The original loader API is preserved.

Before editing, the proposed extension and stricter CLI gate were explained.
No numeric risk ceilings, strategy algorithms or default periods/thresholds
were changed. Existing config.py, RiskControls, stops, entry_plan and verifier
remain authoritative. Default requested margin is ₹100, separate from notional;
effective leverage defaults to 1x with maximum 3x. Initial planned-risk budget
remains ₹10 at ₹2,000; the hard ceiling is ₹20, daily cap ₹40, at most three
entries per UTC day, one open long, default drawdown halt 5%, emergency latched.
Actual losses can exceed triggers on gaps and are not clipped.

New evaluate explicitly requires ₹2,000 initial capital as requested; the
legacy independent-simulation ability to configure another positive capital
remains supported. Existing starting-capital/risk settings were not rewritten.

| Changed paths relative to the start of Phase 4 | Purpose |
| --- | --- |
| backtesting/engine.py | Optional trade_start with past-only warmup; existing next-open execution/emergency behavior; returned telemetry/cost assumptions; isolated Decimal context |
| paper_trading/broker.py | Entry/exit reference and slippage ledger; realized/unrealized equity samples, exposure and risk events; reuse cost model; existing risk/fill policy preserved |
| risk/sizing.py | Reuse cost-model entry/stop-fill formulas; no changed sizing/risk limits |
| cli.py | New evaluate command; explicit cost/policy/cutoff/plan/sensitivity options; strict eligibility for simulation; extra summary metrics/config/data |
| backtesting/costs.py | Shared user-assumption costs and deterministic Decimal context |
| backtesting/datasets.py | Phase 2 assessment, provenance classification, historical freshness and digest-bound eligibility |
| backtesting/splits.py | Validated chronological ranges, evidence floor and earlier warmup |
| backtesting/experiment.py | Fixed baseline, independent periods, cost stress and development-only alternatives; content-based run ID/source digest |
| backtesting/metrics.py | Independently tested Decimal metrics and explicit undefined/sample handling |
| backtesting/benchmarks.py | Same-period 1x full-affordable-capital buy/hold and cash references |
| backtesting/reporting.py | JSON, Markdown and four CSV exports; labels, no overwrite, handled-failure cleanup |
| tests/test_backtesting.py; tests/test_chronological_evaluation.py | 63 deterministic new tests; all price/ledger fixtures synthetic |
| docs/examples/phase4-splits.synthetic.json; docs/examples/phase4-sma-sensitivity.synthetic.json | Predefined example ranges and development alternatives; not optimized against final-test results |
| README.md; VALIDATION.md; docs/PHASE4_BACKTESTING.md; docs/PHASE4_AUDIT.md | Setup/run contract, metrics/assumptions, actual evidence and blockers |

There are 19 changed/new paths in this phase. The checkout already contained
uncommitted Phase 2/3 work: git diff against HEAD includes those earlier phases,
so this list is based on the pre-Phase-4 archive, not an assumed clean tree.
No existing project was recreated or source reset.

## Exact test commands and results

From /workspace/Coindcx-trading-bot:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_backtesting tests.test_chronological_evaluation -v
.venv/bin/python -m unittest tests.test_config tests.test_risk tests.test_broker tests.test_data tests.test_engine_cli tests.test_repository_safety tests.test_strategies -v
.venv/bin/python -m unittest tests.test_data_pipeline tests.test_market_quality tests.test_public_market_data -v
.venv/bin/python -m unittest tests.test_strategy_engine tests.test_signal_verification -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest tests.integration.test_coindcx_public -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
git diff --check
~~~

| Run | Passed | Failed | Errors | Skipped | Discovered | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gate 0 baseline default discovery | 205 | 0 | 0 | 1 | 206 | 0 |
| Final new Phase 4 tests | 63 | 0 | 0 | 0 | 63 | 0 |
| Phase 1 regression group (81 original + existing precision regression) | 82 | 0 | 0 | 0 | 82 | 0 |
| Phase 2 unit group | 69 | 0 | 0 | 0 | 69 | 0 |
| Phase 3 strategy/verifier group | 54 | 0 | 0 | 0 | 54 | 0 |
| Separately enabled actual public integration | 1 | 0 | 0 | 0 | 1 | 0 |
| Final default full discovery | 268 | 0 | 0 | 1 | 269 | 0 |
| Final complete enabled discovery | 269 | 0 | 0 | 0 | 269 | 0 |

Complete runner output: Ran 269 tests in 8.548s / OK. Default output:
Ran 269 tests in 5.665s / OK (skipped=1). No available test was omitted from
the enabled complete run. The default skip is exactly
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles,
which requires COINDCX_RUN_PUBLIC_INTEGRATION=1. It actually ran successfully
both separately and in the complete suite. No Windows results are inferred.

During development, the first old-suite regression run found two stdout-contract
failures after blocked JSON was added too broadly. The existing backtest/paper
invalid-configuration output contract was restored, without weakening its tests;
69 targeted tests then passed. Two subsequent fixture corrections fixed malformed
test headers/expectations, not accepted-data policy. All final results above
are clean; no unresolved failure or error is hidden.

New tests independently cover fee/slippage/cash reconciliation, margin/notional,
leverage rejection, entry-bar/adverse-gap stops, realized/unrealized accounting,
daily and trade-limit event tracking, emergency lockout, warmup-only history,
next-open fills, future-price independence, invalid/incomplete/duplicate/gapped
data, exact chronological coverage, insufficient samples, larger warmup, independent
accounts, metric edge cases, benchmark prices/costs, eligibility bypass/reuse,
zero-order offline CLI, both baselines, sensitivity isolation, stress validation,
interruption refusal, fixed Decimal context and byte-identical export behavior.

Evidence logs under /tmp: coindcx-phase4-baseline.log, targeted.log, phase1.log,
phase2.log, phase3.log, public.log, offline.log and complete.log (all filenames
have the coindcx-phase4- prefix). Pre-edit archive:
/tmp/coindcx-phase4-before.zip. Final phase-only diff:
/tmp/coindcx-phase4-final.diff. These are local evidence, not published artifacts.

## Actual workflow commands and synthetic reports

The following Bash commands were actually executed on Linux. The generator
created 11,520 labelled synthetic waveform candles from 2024-01-01 through
2024-04-30, exclusive. Creation and export refuse existing destinations.

~~~bash
.venv/bin/python - <<'PY'
from pathlib import Path
from tools.generate_sample_data import generate
generate(Path('data/local/phase4-synthetic.csv'), 11520)
PY
.venv/bin/python -m cli evaluate --data data/local/phase4-synthetic.csv --strategy sma_cross --fast 5 --slow 20 --margin-amount 100 --leverage 1 --fee-rate 0.001 --slippage-rate 0.001 --plan docs/examples/phase4-splits.synthetic.json --sensitivity docs/examples/phase4-sma-sensitivity.synthetic.json --output reports/phase4-sma-synthetic-final --allow-synthetic
.venv/bin/python -m cli evaluate --data data/local/phase4-synthetic.csv --strategy momentum --lookback 12 --threshold 0.01 --margin-amount 100 --leverage 1 --fee-rate 0.001 --slippage-rate 0.001 --plan docs/examples/phase4-splits.synthetic.json --output reports/phase4-momentum-synthetic-final --allow-synthetic
~~~

Each period has 2,880 evaluation bars, with 2,880 preceding warmup bars:

| Period | Start inclusive UTC | End exclusive UTC |
| --- | --- | --- |
| Train | 2024-01-31 00:00 | 2024-03-01 00:00 |
| Validation | 2024-03-01 00:00 | 2024-03-31 00:00 |
| Test | 2024-03-31 00:00 | 2024-04-30 00:00 |

Both commands returned COMPLETE_SYNTHETIC_ONLY, zero submitted real orders and
live_trading_enabled=false. Source digests in both exports were independently
checked against the final source. SHA-256 run IDs:

- SMA: 2bd0879cb1d4fe2e66f118f0cc1073e0cf6507638693596167224b3fcd21a41a.
- Momentum: f4a67faa871df804796e47281273b9ef81aaec87abedf093925a46a1b12f6922.

Each directory has results.json, report.md, metrics.csv, trades.csv, equity.csv
and risk_events.csv. They contain actual calculated **synthetic-only** values;
none is presented here as market evidence. The SMA alternatives {fast:3,slow:10}
and {fast:8,slow:30} were predeclared for development-period plumbing/sensitivity;
neither is selected or evaluated on test. The reported baseline stays {5,20}.
Momentum keeps {lookback:12,threshold:0.01}. No parameters were optimized.

Stress uses assumed fee/slippage of 0.002 on each leg versus baseline 0.001;
these are not verified CoinDCX rates. The workflows demonstrate report generation
and accounting under changed assumptions, not execution realism or robustness
of a profitable strategy. Reproducibility and edge behavior are independently
tested, not inferred from plausible-looking outputs.

## Data eligibility, API limits and unavailable evidence

All existing local datasets and the new generated fixture were inspected as
synthetic; none is eligible real history. No real-market net-of-cost, benchmark,
out-of-sample, regime, win-rate or profitability result is reported.

Actual public smoke passed using only unsigned GET discovery/details and recent
candles. The existing Phase 3 official-documentation record names:

- https://api.coindcx.com/exchange/v1/markets
- https://api.coindcx.com/exchange/v1/markets_details
- https://api.coindcx.com/market_data/candles
- Official contract source: https://docs.coindcx.com/#candles; current recorded
  intervals 1m, 15m, 1h, 1d. Project remains 15m. OHLCV/time schema uses
  opening Unix milliseconds and asset-unit volume, not reliable quote volume.

See docs/COINDCX_API.md for the current-versus-historical official sources,
limit/pagination/retry/cache behavior and contract limitations. This phase's
recent public smoke does not verify full history completeness, point-in-time
market eligibility, quote liquidity, historical spreads, funding or fill quality.
The canonical website was not re-audited as a new endpoint contract in Phase 4.
No private API credentials are accepted or required by these public/CSV paths.

## Final diff, exclusions and remaining risks

Tracked plus untracked paths were compared with the pre-edit archive and read
directly. No preexisting file was deleted. git diff --check passed. Nothing is
staged; no commit/push occurred. .gitignore still excludes .env variants,
credentials/secrets, private-key paths, data/local artifacts and reports. The
only tracked sensitive-filename candidate is .env.example, whose values are all
blank. Repository safety tests passed and current tracked/nonignored working-file
scans found no common API-key/private-key patterns. This is not an exhaustive
history scan or proof against every secret encoding. Requirements remain standard
library only; no credentials or dependency changes were introduced.

Unresolved limits:

1. **Real evaluation BLOCKED:** independently reviewed sufficient INR history and
   reliable quote turnover/threshold evidence are missing. Public asset volume
   is not promoted into fabricated quote-volume evidence. Newly listed coins
   without sufficient history remain excluded.
2. **Execution precision unavailable:** next-open full fills, constant symmetric
   cost rates and no extra latency are assumptions. No book/queue, spread,
   funding, borrow, liquidation, taxes or exchange lot/minimum rules are verified.
   Leveraged returns cannot represent a verified CoinDCX instrument model.
3. **Bar uncertainty:** drawdown omits unknown high/low ordering and tick peaks;
   exposure is bars touched, not elapsed time. Intrabar stop timestamps identify
   the candle, not exact fill time. Final liquidation can be attributed to the
   new UTC day at an exclusive endpoint. Trigger overshoots on gaps are real
   simulated losses, not failures to clamp a cap.
4. **Study discipline:** no authenticated untouched-test history, multi-symbol
   universe or market-regime sample exists. Active-status/provenance attestations
   are not point-in-time eligibility and may introduce survivorship/selection
   bias. Repeated operator reruns can compromise a holdout; freeze parameters and
   reserve a genuinely unseen interval before making market conclusions.
5. **Account/process limits:** risk state remains in-memory per simulation;
   period resets are independent comparisons, not shared durable trading limits.
   Manual account snapshots remain operator attestations. Emergency cleanup is
   best-effort; forced process death/durable recovery is not established.
6. **Operational limits:** large histories produce large in-memory reports; no
   streaming/memory-pressure or forced-crash recovery guarantee. Export cleanup
   is tested for handled failure, not hard termination.
7. **Native Windows BLOCKED here:** all current tests ran on Linux. Do not infer
   Phase 4 compatibility from the older Phase 1 Windows CI result.

Next steps: run native Windows verification below using these actual local
changes; obtain independently reviewed INR/quote-liquidity evidence and a justified
policy; document actual instrument/cost evidence before interpreting leveraged
results; reserve chronological development and untouched test ranges, freeze the
configuration, and run Phase 4 evaluation with synthetic opt-in absent. Keep
real results BLOCKED until eligibility passes. Review this phase; Phase 5 needs
separate user approval and has not started.

## Exact Windows PowerShell verification

From the audited working tree, with Git and Python 3.12 installed:

~~~powershell
Set-Location C:\path\to\Coindcx-trading-bot
git --version
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }
.\.venv\Scripts\python.exe -m unittest tests.test_backtesting tests.test_chronological_evaluation -v
if ($LASTEXITCODE -ne 0) { throw "Phase 4 tests failed." }
~~~

Optional complete discovery with actual public read-only requests:

~~~powershell
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Complete verification failed; inspect output." }
} finally {
    Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
}
~~~

The README includes full PowerShell synthetic workflow commands equivalent to
the Linux commands actually run. These Windows instructions are unexecuted in
this Linux environment, not a Windows PASS claim.
