# Validation record

Initially validated on 2026-10-17, Linux, Python 3.12.14. All commands run from
the repository root. Native Windows CI verification subsequently passed on
Windows Server 2022, Python 3.12.10; see the final section below. The Windows
launcher/venv installation instructions were not executed on a personal computer.

- `python3 -m venv .venv`: created an isolated Python 3.12 environment.
- `.venv/bin/python -m pip install --no-index -r requirements.txt`: passed;
  no third-party dependencies or package downloads needed.
- `.venv/bin/python -m unittest discover -s tests -v`: the original foundation
  and Phase 1 baseline each passed **54 tests**. The final Phase 1 suite passed
  **81 tests**, with 0 failures, 0 errors, and 0 skipped tests. See
  [PHASE1_AUDIT.md](PHASE1_AUDIT.md) for the added safety checks and changes.
- `.venv/bin/python -m tools.generate_sample_data`: generated 3,072 labeled
  synthetic candles and matching checksum metadata under ignored `data/local/`.
- `.venv/bin/python -m cli strategies`: listed `momentum` and `sma_cross`.
- `backtest --strategy sma_cross --margin-amount 100 --leverage 1` and
  `paper --strategy momentum --margin-amount 100 --leverage 3`, each via
  `.venv/bin/python -m cli` with `--data data/local/sample.csv --allow-synthetic`:
  passed, produced valid JSON, and executed simulated trades. Repeating each
  command produced identical output from a fresh simulated account.
- `verify --strategy sma_cross` and `manual --strategy momentum`, each via
  `.venv/bin/python -m cli` with `--data data/local/sample.csv --allow-synthetic`:
  passed, produced valid JSON, and reported **zero orders submitted**.
- `paper --leverage 4` with the sample dataset/opt-in: rejected with exit code 2.
- `paper` with the synthetic sample and without `--allow-synthetic`: rejected
  with exit code 2. Both rejection checks produced no simulation result.
- `git diff --check`: passed.

The automated tests use deterministic fixtures and generated synthetic data.
They verify safety rules, accounting, dataset rejection, and command behavior;
they do not establish real-market returns or reliability. No real historical
backtest, exchange integration, or live order was executed. Real-money trading
remains disabled.

Phase 1 additionally verified three entries maximum per UTC day in both command
smoke checks, repeated deterministic simulation output, credential-free commands
with sockets blocked in tests, common secret-file Git exclusions, cost-inclusive
account stops, absolute INR ceilings, and best-effort emergency cleanup/exit 130.
The smoke checks used isolated generated data and did not access CoinDCX.

## Phase 1 final verification

Repeated the full available suite on Linux, Python 3.12.14:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Result: **81 passed, 0 failures, 0 errors, 0 skipped**. All discovered tests ran.
No application-code changes or fixes were needed in this verification pass.
The existing tests cover planned INR risk caps, margin sizing, stop enforcement,
3x leverage, daily loss and entry-count halts, one open position, drawdown,
emergency cleanup, and order-free manual/verify commands with sockets blocked.

Git index inspection found zero staged paths and only `.gitignore` and `README.md`
tracked. No sensitive filenames or credential-pattern findings were present in
the index blobs or their current working copies. `.env` variants, common secret
files, and private keys are ignored; `.env.example` remains blank placeholders.
This is a current-index/content check, not a full Git-history secret scan or an
online credential-validity check. Most application files remain untracked from
the prior foundation work and were reviewed directly.

Windows execution was not run because this environment is Linux. Exchange/live
integration tests were not run: this foundation has no exchange transport and
CoinDCX access is outside the authorized offline verification scope. No such tests
were skipped by the runner. No network connection to CoinDCX, live order, or
live-trading enablement occurred. Phase 2 has not started.

Previously documented limitations remain: realized gap losses can exceed planned
thresholds; counters/halts are in-memory; emergency cleanup is best-effort.

Native Windows CI preparation: added `.github/workflows/windows-phase1.yml` for
Windows Server 2022 and Python 3.12, with a native-platform assertion and a complete
suite discovery guard. This workflow has not been executed on Windows. No project
changes were committed or pushed while preparing it. The cloud host is Linux and
provides no Windows shell/runner. The read-only GitHub Actions workflow API request
returned `Forbidden`; this does not establish a missing credential. Native Windows
execution remains **BLOCKED** until a Windows runner executes the published code
and its results can be inspected. Phase 2 has not started.

The workflow YAML and its native-Windows/Python assertions, full-suite discovery
guard, pinned action references, read-only permissions, and failure propagation
were checked locally with an isolated YAML parser outside the project environment.
Those static checks passed; they do not constitute a Windows test run. No new
application dependency was added.

## Completed native Windows verification — PASS

The earlier BLOCKED entries record the state before the CI branch was published;
this verified Windows run supersedes that status.

- Branch: `phase1-windows-verification`.
- Verified source commit: `6f96dfc76a9e5d80c1f9b55601577a798df2df16`.
- Platform: native Windows, GitHub-hosted `windows-2022`, Python **3.12.10**.
- [Run 39011498680](https://github.com/25ai1so139-gif/Coindcx-trading-bot/actions/runs/39011498680).
- [Job 117334801440](https://github.com/25ai1so139-gif/Coindcx-trading-bot/actions/runs/39011498680/job/117334801440).
- Actual command: `python -m unittest discover -s tests -v`.
- Actual runner totals: **81 passed, 0 failures, 0 errors, 0 skipped**; exit 0.

The native-platform assertion, Python-version check, at-least-81-tests discovery
guard, full test command, and whitespace check all completed successfully. The
public job page exposed this exact result step, generated from the real unittest
output rather than fixture data:

```text
Test result: Windows / Python 3.12.10 / Ran 81 tests in 0.574s / OK / exit 0
```

The initial branch publication (`78e6762`) and summary-reporting update (`3774f58`)
also completed successful Windows workflows. The counts above are verified from
the public result step for `6f96dfc`, not inferred from those earlier green runs.

No application logic or risk rules changed during CI setup. All published files
were checked for sensitive filenames/credential patterns before the initial
commit, and all 81 tests also passed locally with the complete source staged.
No CoinDCX connection, live order, or live-trading enablement occurred. Phase 2
has not started.

GitHub's Actions API remained blocked by the cloud proxy, but public GitHub pages
provided the run, step statuses, commit identity, and exact test totals. The
temporary `api.github.com` draft addition was removed, restoring the previous
custom allowlist and preserving preset domains. Environment drafts are separate
from runtime configuration: review/save and publish environment settings to apply
any pending configuration; no environment publication was performed here.
