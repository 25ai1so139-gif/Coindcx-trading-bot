# Phase 5 Gate 0 — BLOCKED, implementation not started

Historical prerequisite record, before the user's explicit central-gate
remediation request. [The remediation report](PHASE5_REMEDIATION.md) records the
subsequent implementation and tests. Its code evidence supersedes the "not
implemented" finding below; real-market evidence remains unqualified and no
Phase 6 approval or readiness is inferred.

Verified 2026-10-17 on Linux 6.18.55 x86_64, Python 3.12.14, using the existing
/workspace/Coindcx-trading-bot/.venv. Existing branch: phase2-market-data.

The Phase 5 request requires: "If critical tests fail or required evidence is
missing, report BLOCKED and resolve the issue before proceeding."

**Gate 0 is BLOCKED by missing qualified real-market data and execution evidence.**
All available tests pass. Passing synthetic tests and environment publication
do not establish valid real-market history, realistic instrument execution or
real out-of-sample evidence. Phase 5 Tasks 1–6 are not implemented or claimed
complete; Task 7 is limited to this prerequisite verification.

## Evidence reviewed

- [Phase 1 safety audit](../PHASE1_AUDIT.md): original protection controls and
  documented limits, including gap overshoots and in-memory account state.
- [Phase 2 audit](PHASE2_AUDIT.md): data normalization/eligibility/cache tests;
  original network blocker subsequently superseded in Phase 3.
- [Phase 3 final strategy audit](PHASE3_AUDIT.md): strategy and safety results,
  current public endpoint evidence and still-unqualified real liquidity.
- [Phase 4 audit](PHASE4_AUDIT.md) and [design](PHASE4_BACKTESTING.md): tested
  software framework; explicitly BLOCKED real-market/out-of-sample evaluation.
- Actual config.py, risk/controls.py, risk/sizing.py, risk/entry.py,
  risk/stops.py, risk/context.py, backtesting/datasets.py, costs.py, splits.py
  and experiment.py; relevant existing risk, broker, verifier and evaluation
  test definitions and the complete test runner output.
- Actual dataset sidecars, checksums, row counts and both final Phase 4 JSON
  reports, rather than treating the audit narrative alone as proof.

## Exact test results

Commands actually executed from the existing repository root:

```bash
.venv/bin/python -m unittest discover -s tests -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```

| Run | Passed | Failed | Errors | Skipped | Total | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Default baseline discovery | 268 | 0 | 0 | 1 | 269 | 0 |
| Complete discovery, public integration enabled | 269 | 0 | 0 | 0 | 269 | 0 |

Default output: Ran 269 tests in 6.191s / OK (skipped=1).
Enabled output: Ran 269 tests in 7.796s / OK.

The default skip is exactly
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles.
It requires COINDCX_RUN_PUBLIC_INTEGRATION=1 and actually passed in the enabled
suite. No available existing test was skipped in the complete run. No Phase 5
tests were added or run because implementation has not passed Gate 0. No native
Windows tests were run; the older Phase 1 Windows CI result does not cover the
current code.

Complete discovery includes all Phase 1–4 regression modules. Existing coverage
includes margin/notional distinction, cost-inclusive risk sizing, 3x rejection,
protective stops and gaps, fees/slippage, daily-loss threshold and UTC rollover,
three-entry/fourth-entry behavior, one position, drawdown/emergency latches,
manual/verify zero orders, disabled shorts, invalid/stale input and chronological
evaluation. This does not certify the additional centralized approval, audit
logging, session persistence or full adversarial cases requested for Phase 5.

Logs: /tmp/coindcx-phase5-baseline.log and
/tmp/coindcx-phase5-gate0-complete.log. Underlying runner exit codes were preserved.

## Gate status and unresolved evidence

| Gate check | Status | Actual finding |
| --- | --- | --- |
| Inspect latest audits and current implementation | PASS | Phase 1–4 audits and actual data/cost/split paths reviewed |
| Existing software tests/regressions | PASS | Complete suite: 269 passed, no failures/errors/skips |
| Existing data-quality gates | PASS | Structural checks and real-data liquidity rejection tests pass; no bypass added |
| Qualified real historical dataset | BLOCKED | Every usable local dataset declares synthetic; no reviewed real INR history/liquidity evidence exists |
| Cost-accounting implementation | PASS | Fees/slippage and sensitivity calculations are tested and assumptions explicit |
| Realistic instrument/execution evidence | BLOCKED | Rates remain illustrative; no verified exchange precision/minimums, leveraged product model, historical spread/funding/fill evidence |
| Chronological train/validation/test implementation | PASS | Exact ranges, prior-only warmup and fixed-parameter behavior tested |
| Real-market out-of-sample validation | BLOCKED | Both final reports are COMPLETE_SYNTHETIC_ONLY, not real-market evidence |
| Current native Windows execution | BLOCKED | Linux host only; this is a platform limitation, not an additional invented market-data gate |
| Private/live/short execution stays disabled | PASS | Existing regression tests pass; no new trading implementation or private request |
| Phase 5 implementation | BLOCKED | Required prior-phase evidence remains missing; no permission to bypass Gate 0 inferred |

The local dataset inspection found:

| Dataset | Rows | Declared kind | Reviewed real quality / verified quote volume |
| --- | ---: | --- | --- |
| data/local/sample.csv | 3,072 | synthetic | false / not asserted |
| data/local/phase2-sample.csv | 3,072 | synthetic | false / false |
| data/local/phase2-normalized.csv | 3,072 | synthetic | false / false; ingestion_eligible=false |
| data/local/phase2-research.csv | 3,072 | synthetic | false / false; synthetic research eligibility only |
| data/local/phase4-synthetic.csv | 11,520 | synthetic | false / false |

Each listed CSV matches its sidecar SHA-256. That verifies local byte binding,
not authentic market provenance. The additional content-addressed CSV under
data/local/raw has no standalone dataset sidecar; it is ingestion evidence,
not an eligible independent backtest input.

Both reports under reports/phase4-sma-synthetic-final/results.json and
reports/phase4-momentum-synthetic-final/results.json were checked:

- Status COMPLETE_SYNTHETIC_ONLY; kind synthetic.
- Source digest matches current application source.
- Separate train, validation and test periods each have 2,880 evaluation bars
  and 2,880 preceding warmup bars.
- Configured fee_rate=0.001 and slippage_rate=0.001, per leg, with
  cost_assumptions.schedule_verified=false.
- Zero real orders; live_trading_enabled=false and short_entries_enabled=false.

The actual public integration succeeded without private credentials, but recent
public candles are not sufficient history/liquidity qualification. The documented
public candle volume is asset volume; converting close × asset volume would be
an estimate, not verified quote turnover. No such value was invented to clear
the eligibility requirement. Existing synthetic files or reports were not
relabelled as real.

## Deferred Phase 5 work and scope limits

Existing risk/entry.py is a shared sizing/position/account-limit helper. Its
signature does not centrally receive all signal identity, freshness, eligibility,
explicit stop and instrument evidence requested for Phase 5. Some checks remain
in caller paths. Existing broker RiskEvent telemetry records limit activations,
not every accepted/rejected signal with the full requested audit fields.

RiskControls latches daily losses within a UTC day and resets the daily halt
and entry count on a new observed UTC day; the day-start basis uses previously
observed equity to retain overnight gaps. Drawdown/emergency latches persist
for that in-memory account. This is not restart-safe persistent session storage.
Existing eight-decimal sizing precision is an abstract simulator rule, not
verified exchange metadata. Those limitations remain documented, not fixed or
represented as passing the new Phase 5 requirements.

No application logic, tests, limits, dependencies, credentials, data or reports
were changed. Only docs/PHASE5_GATE0.md was added to record the required stop.
Existing tracked and untracked work is preserved. No commit or push occurred.
The existing repository-hygiene tests passed; .gitignore and .env.example remain
unchanged. No private endpoints, API secrets, real orders, live enablement,
profitability claims or Phase 6 work.

## Evidence needed to resume

1. Obtain sufficient real INR 15-minute history with reviewed provenance,
   completed coherent gap-free candles, reliable quote-volume evidence and a
   justified liquidity threshold. Preserve raw evidence and run the strict
   existing Phase 2/4 eligibility path. Unqualified/newly listed markets remain
   excluded; synthetic opt-in cannot substitute for this evidence.
2. Document defensible cost assumptions and applicable instrument details for
   that historical study. Distinguish verified fee/precision/minimum rules from
   estimates, and unavailable spread/funding/fill evidence from supported models.
   Do not claim the current abstract leverage model is a verified CoinDCX product.
3. Freeze strategy/settings and chronological development/validation/holdout
   ranges, then produce reproducible net-of-cost Phase 4 reports on the qualified
   data. No profitable result is required or promised. Recheck Gate 0 before
   beginning the Phase 5 implementation.

These evidence gaps cannot be repaired by passing more synthetic tests,
weakening liquidity checks, adding an API secret, or publishing the environment.
No credentials are required for the existing offline/public verification workflow.

## Exact local Windows PowerShell commands

These instructions have not been executed on Windows in this session. From
the actual audited checkout, with Git and Python 3.12 installed:

```powershell
Set-Location C:\path\to\Coindcx-trading-bot
git --version
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }
```

For the complete suite including actual public read-only market-data requests:

```powershell
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Complete verification failed; inspect output." }
} finally {
    Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
}
```

Passing these commands verifies software on that host; it does not clear the
missing real-data and execution-evidence prerequisites by itself.
