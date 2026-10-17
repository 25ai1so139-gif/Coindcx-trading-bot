# Phase 6B implementation and verification audit

2026-10-17 UTC. This report covers the current working tree, not a published commit.
Environment: Linux 6.18.55 x86_64/glibc 2.41, CPython 3.12.14, SQLite 3.53.1.
Native Windows is UNVERIFIED. No credentials, private API calls, real orders,
live/short enablement, strategy optimization or Phase 6C work were performed.

**Implementation and deterministic safety verification: PASS on Linux for the
supported interfaces. Real-market entry qualification: BLOCKED. Continuous
production readiness/24-hour availability: UNVERIFIED. No overall operational PASS.**

## Gate 0 and exact test evidence

Inspected actual risk/entry.py, risk/proposal.py, risk/audit.py, risk/sizing.py,
risk/controls.py, paper_trading/broker.py, persistence.py, state.py, the Phase 5
remediation and Phase 6A audits, data pipeline, existing CLI and strategy/replay
interfaces before editing. Gate 0 tests passed before implementation:

| Command from repository root | Passed | Failed | Errors | Skipped | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| .venv/bin/python -m unittest discover -s tests -v (baseline) | 411 | 0 | 0 | 1 | 412 |
| .venv/bin/python -m unittest tests.test_persistence tests.test_central_risk tests.test_risk -v (Gate 0) | 161 | 0 | 0 | 0 | 161 |
| .venv/bin/python -m unittest tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v | 232 | 0 | 0 | 0 | 232 |
| .venv/bin/python -m unittest discover -s tests -v (final, 20.262s) | 482 | 0 | 0 | 1 | 483 |
| COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v (final, 21.845s) | 483 | 0 | 0 | 0 | 483 |
| COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest tests.integration.test_coindcx_public -v | 1 | 0 | 0 | 0 | 1 |

The default skip is exactly the opt-in public discovery/candles integration test,
which was separately enabled and also passed in final public-enabled discovery.
No available test was left unrun. Windows execution, multi-day hosting, physical
power-loss and independent market qualification were not tested and are not
inferred from these results. All 71 new tests are deterministic synthetic cases.
The final discovery contains all 411 pre-existing offline tests unchanged plus
71 new offline tests and the one optional network integration test.

Final module counts: central-risk 86, persistence 57, sizing/controls 18,
continuous-paper 71; the remaining Phase 1–4 offline tests account for 250 passes.
The focused run took 9.468s. After the final equity-mark timestamp correction,
both complete suites were rerun and include its new assertion.

Commands were captured with underlying exit status preserved, for example:

~~~bash
.venv/bin/python -m unittest discover -s tests -v > /tmp/phase6b-full-offline-final.log 2>&1
code=$?; tail -n 6 /tmp/phase6b-full-offline-final.log; exit "$code"
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v > /tmp/phase6b-full-public-final.log 2>&1
code=$?; tail -n 6 /tmp/phase6b-full-public-final.log; exit "$code"
git diff --check
git diff --cached --name-only
~~~

These /tmp logs are local execution artifacts, not durable hosting or Windows
evidence. Test output reported OK and both final shell commands returned zero.

## Changed files and preserved behavior

| File | Result and reason |
| --- | --- |
| paper_trading/continuous.py (new) | PublicFeed, completed-candle PaperLoop, strict Phase 2 assessment, stale/gap/retry handling, prior-history strategy input, startup/catch-up HOLD, status/daily P&L and graceful shutdown |
| paper_trading/session.py (new) | Transactional schema-3 extension, configuration fingerprint, owner lease/fencing, heartbeat, atomic bar and stop operations |
| paper_trading/commands.py (new) | Durable start/status/stop, explicit create, saved-settings resume, interruptible backoff and scoped JSON logging |
| paper_trading/persistence.py | Validate schema 3/runtime digest, expose detached runtime snapshot, forbid raw bar/finish on managed accounts, atomically integrate existing emergency API |
| cli.py | Dispatch the three paper session verbs while preserving paper --data and all prior commands; clarify help |
| tests/test_continuous_paper.py (new) | 71 deterministic synthetic cases, including real child-process death/recovery and separate SQLite connections |
| README.md | Exact PowerShell setup/start/status/stop/resume/verification instructions and qualification caveats |
| VALIDATION.md | Append current results; historical evidence retained |
| docs/PHASE6A_PERSISTENCE.md | Historical-scope pointer to the schema-3 guide |
| docs/PHASE6B_PAPER.md (new) | Timing, schema, ownership, failure/recovery, Windows instructions, monitoring and hosting requirements |
| docs/PHASE6B_AUDIT.md (new) | This implementation/evidence/status report |
| docs/examples/phase6b-public-smoke.json (new) | Actual public-read-only CLI smoke summary, explicitly not market qualification or performance evidence |

Compared against a pre-edit archive of tracked and nonignored untracked files,
five inherited files were modified, seven files were added, 84 inherited files
remained byte-identical and no inherited file was deleted. Phase 5 gate/limits, broker mathematics, state codec,
data pipeline, SMA/momentum implementation and all pre-existing tests remained
byte-identical. No risk rule was loosened and no strategy parameter was tuned.
The old CSV paper command is still an independent stateless historical replay.
The Git HEAD predates earlier phases, so its larger cumulative diff also includes
inherited Phase 2–6A work; that work must not be misattributed to this phase.

Final diff review checked the phase-local persistence and CLI changes separately
from that cumulative diff. git diff --check passed. Nothing is staged/committed/
pushed by this task. .gitignore still excludes .env variants, secrets/private-key
paths, paper_trading/local and SQLite files/sidecars. The tracked/staged path scan
found no .env, private keys, credentials or paper DBs; .env.example still has only
20 blank BOT_* placeholders. Source review found no real API credentials and no
new authentication/order transport. Repository hygiene regression tests pass.

## Entry-path proof and preserved limits

The continuous route is PaperLoop.poll -> session.process -> its BEGIN IMMEDIATE
transaction -> recovered PaperBroker.process_bar -> PaperBroker._open -> existing
risk.entry.approve_entry -> validated plan. Only then does the original broker
reserve margin and set its private position. Session process commits that financial
checkpoint, processed candle ID and runtime state atomically, revalidating the full
candidate before acknowledgement. There is no alternative fill constructor in the
loop. SELL exits an existing long or receives the central unsupported-short
rejection; it never opens a short.

Raw PersistentPaperBroker.process_bar/finish are explicitly rejected once runtime
exists, including an independently opened handle. session.process requires a
current owner token, an unexpired lease, no stop flag, a completed consecutive
candle and (for an entry) the latest bar after ownership acquisition. BUY must
include strictly prior completed history; previously processed history cannot be
silently revised. The original gate still independently checks market/strategy/
instrument/cost/equity/stop/risk state. Reusing a processed bar is a no-op before
another gate review; changed data at that ID is rejected. All mutations are local
paper bookkeeping; the public transport has only unsigned whitelisted GET routes.
Supported interfaces, not arbitrary Python memory or malicious direct SQL edits,
are the boundary of this proof.

| Safety requirement | Status | Evidence |
| --- | --- | --- |
| ₹2,000 initial simulated equity; margin distinct from notional | PASS | Unchanged Settings/gate/account binding; sizing/account reconciliation regressions and start-command test |
| Leverage <=3x; no short entries | PASS | Existing adversarial ceilings/instrument tests; managed short rejection and leveraged drawdown recovery |
| Initial ₹10 planned budget and hard ₹20 cap, including costs | PASS | Existing gate boundary/independent-plan tests; continuous approval assertion <=₹10 at initial equity |
| Daily halt min(₹40, 2% daily starting equity) | PASS | Unchanged controls; managed daily-loss/takeover test plus 6A overnight-basis/UTC reset regressions |
| Maximum three UTC entries; one open position | PASS | Managed fourth-entry rejection/recovery and repeated LONG rejection; original UTC rollover regressions |
| Central gate mandatory, including direct-path attempts | PASS | Managed raw bar/finish blocked; missing-stop/short/revised-history cases; all central-risk bypass regressions |
| Complete candles, no lookahead, duplicate handling | PASS | Prior-signal/next-open capture, incomplete exclusion, startup HOLD, duplicate/no-gate call, correction rejection |
| Stale/missing/invalid/insufficient data fail closed | PASS | Dedicated deterministic quality, missing edge, zero-volume, wrong-market and gap tests |
| Timeouts/429/backoff/recovery bounded | PASS | Existing client tests plus timeout/Retry-After/exhaustion/recovery tests in the loop |
| Atomic restart-safe balances, open positions and limits | PASS on Linux/local SQLite | v2 migration preserves financial chain; subprocess recovery; deaths during extension and before/after bar commit; rollback/lost-entry prevention |
| Owner contention, expired worker and external stop fencing | PASS | Two-connection ownership, takeover, stop/entry race and stop-during-I/O tests |
| Persistence faults stop new entries | PASS | Commit-failure rollback/poisoned handle test; existing lock, corruption and ambiguous-commit regressions |
| Emergency stop and graceful shutdown | PASS on Linux | Ctrl+C/handler restoration, external-stop normal exit, idempotent flatten, no environment-variable dependence and actual public CLI process smoke |
| Fill fees/slippage/stop/equity reconciliation | PASS for deterministic model | Original broker math reused, managed stop trade/cash reconciliation, full persistence/gate regressions |
| Structured logs, health, safe-data timestamp and daily P&L | PASS for tested snapshots | Whitelisted JSON events, daily summary/status/freshness and close-time assertion; no raw provider exception content |
| manual/verify submit zero orders; live disabled | PASS | Existing no-broker/no-network command tests; transport whitelist and no live mode unchanged |
| Secrets and state excluded from Git | PASS | Unchanged ignore rules, placeholder/path scan, repository hygiene regressions, empty index |
| Public API connectivity/response handling | PASS for smoke only | Enabled public test and real CLI start/status/stop described below |
| Real-market entry/liquidity/instrument qualification | BLOCKED | Feed cannot supply required independent evidence; real-data proposals remain rejected |
| Native Windows | UNVERIFIED | No current-source native Windows execution was performed |
| Continuous hosted availability/long-run capacity | UNVERIFIED | Short functional/synthetic tests only; no host service, soak or physical-power-loss proof |

## Official contract and actual public smoke

Official https://docs.coindcx.com/ returned HTTP 200 with TLS verification; reviewed
sections: [markets](https://docs.coindcx.com/#markets),
[market details](https://docs.coindcx.com/#markets-details),
[candles](https://docs.coindcx.com/#candles). Exact three GET URLs and unsigned
schema are in PHASE6B_PAPER.md and COINDCX_API.md. Documented intervals remain
1m/15m/1h/1d; volume is target-asset volume, not reliable quote turnover.
The captured HTML digest is recorded in the smoke evidence. Documentation does
not guarantee history retention, complete coverage or a numeric public quota.

The opt-in discovery/recent-candle integration passed (1/1). A separate actual
subprocess harness ran start, local status and local stop against I-BTC_INR using
public history; all three exit codes were 0. At 2026-10-17T11:10:07 UTC its observed
health was DATA_BLOCKED/ZERO_VOLUME, with zero processed bars/entries, ₹2,000 equity,
then STOPPED and a durable emergency halt. The account was temporary and is not a
production deployment. The commands executed by that harness were:

~~~bash
.venv/bin/python -m cli paper start --create --db "$temporary_db" --symbol I-BTC_INR --poll-seconds 1
.venv/bin/python -m cli paper status --db "$temporary_db"
.venv/bin/python -m cli paper stop --db "$temporary_db"
~~~

The foreground start ran in a child while the other commands inspected/stopped
it; temporary_db denotes its generated temporary path. The exact harness was
executed as PYTHONPATH=. .venv/bin/python /tmp/phase6b-cli-smoke.py. Durable summary:
[docs/examples/phase6b-public-smoke.json](examples/phase6b-public-smoke.json).

An additional single-poll probe of I-IMX_INR returned 2,882 completed rows with no
missing intervals, but 1,876 zero-volume bars and LIQUIDITY_REVIEW_REQUIRED. It also
processed zero candles/entries and retained ₹2,000. These observations describe
those requests only; neither pair is qualified and no returns/win rates are claimed.

## Defects resolved during implementation and remaining work

Closed direct managed-account bypass paths, fenced stops/lease loss after fetch,
made a durable external stop a normal worker exit, and bounded poll periods below
the ownership lease. Invalid start environment remains rejected, while local
emergency stop now uses validated stored settings so an invalid environment cannot
block it. Corrected equity_marked_at to the actual completed-candle close boundary.
All are covered by deterministic assertions and the final complete suites pass.
No pre-existing Phase 5/6A critical failure was found at Gate 0. Early new-test
fixture errors (skipping required inter-bar heartbeats, revising known synthetic
prices, inspecting a SELL audit after a rejected fourth BUY) were corrected to
represent the existing contracts, without weakening prior tests or safety checks.

Remaining work, explicitly not completed:

1. Run the exact native Windows verification commands in README.md or
   PHASE6B_PAPER.md on Windows/Python 3.12 and record platform/revision/counts.
2. Independently establish trustworthy real-market history, liquidity, instrument
   and cost evidence and review its integration. The current public-only adapter
   intentionally cannot qualify entries; no override/relaxed policy was added.
3. Before sustained hosting, review durable storage, validated backup/recovery,
   clock synchronization, supervision, log rotation and external health alerts.
   Benchmark inherited full-history checkpoint growth/recovery costs. No automatic
   compaction, failover, remote monitoring or always-on service is installed.
4. Do not treat estimated candle fills/stops or last-known-close shutdown as
   executable live prices. Price gaps, intrabar ordering, outage exits, provider
   changes, funding/liquidation/order-book effects remain outside this simulator.
   Valid-file rollback requires trusted latest evidence; hashes are not signatures.
5. Review this Phase 6B result and obtain approval before any Phase 6C work. No
   active paper worker was left running by these tests.
