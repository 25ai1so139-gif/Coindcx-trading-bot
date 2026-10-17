# Complete project synchronization review

17 October 2026. Reviewed contents for `codex/full-project-sync` in the existing
repository <https://github.com/25ai1so139-gif/Coindcx-trading-bot>. This is a
synchronization task, not a new trading phase. Git push status and the resulting
commit ID must be verified separately; this pre-commit record is not proof of a
successful upload.

## History and preservation

Origin was already `https://github.com/25ai1so139-gif/Coindcx-trading-bot.git`;
it was not changed. Read-only remote inspection and fetch showed:

- `main`: `9f42d5da8eb0ca4bddb049b05157e84bb980b48e`, the initial commit.
- `phase1-windows-verification`: `acde254c37b8f2f0fc84da00bd0a0012e2595cca`.
- Current local foundation: the same `acde254` commit, four commits ahead of
  main, with main as an ancestor and no unrelated remote commits to merge.
- `codex/full-project-sync` did not exist during inspection. It is a new branch;
  main and the Windows branch are not updated, deleted or force-pushed.

The complete existing application, tests, configuration templates, Windows
workflow, all phase documentation and compact audit evidence are retained.
All **142 pre-task nonignored project files remain byte-identical**, including
the existing README and validation history. No working code was replaced,
recreated or converted to placeholders. The synchronization adds only this
review, the evidence archive, its manifest and the actual test log: **146 direct
repository files** in total.

## Entire-directory inventory and evidence packaging

Inventoried **773 files** outside Git internals, the virtual environment, Python
bytecode and development tool cache directories. Each file is classified with
its original path, size and SHA-256 in
[the synchronization manifest](archive/full-project-sync-manifest.json).

| Disposition | Files | Treatment |
| --- | ---: | --- |
| Existing source/tests/docs/templates/configuration | 142 | Ordinary Git files, unchanged |
| Reviewed public or explicitly synthetic audit artifacts | 448 | Original bytes and paths in the ZIP below |
| Regenerable response caches | 153 | Remain local and ignored |
| Raw worker/account/runtime exports | 20 | Remain local and ignored |
| SQLite paper-account databases | 3 | Remain local and ignored; never uploaded |
| Full third-party API pages/private-operation example sections | 7 | Remain local; relevant public-only sections, references and source hashes retained |

[full-project-audit-evidence.zip](archive/full-project-audit-evidence.zip)
contains **448 files**, 231,210,364 uncompressed bytes / 26,611,331 ZIP bytes.
SHA-256:
`4aa59059bc2df1dbf7213e4bed89037bdac9c83e357bd71869c5599b66104916`.
All entries were checked against original file hashes and ZIP CRCs; original
relative paths are preserved. No original working-directory artifact was deleted
or modified. The archive avoids adding hundreds of generated files directly to
Git while preserving reviewed audit evidence.

Included evidence covers the original public API histories/response bodies,
normalized/quarantined CSVs and metadata, diagnostics, sizing reports, public
documentation sections, Phase 8F's original replay ZIP, later audit verification
records, and the explicit synthetic inputs/reports from early phases. Phase 4
simulation reports/equity/trades are generated mathematical fixtures labeled
`COMPLETE_SYNTHETIC_ONLY`, not real account records or market performance.
Existing published audit summaries remain ordinary documentation. Raw worker
status/account exports and account databases are excluded even when simulated.

The seven omitted provider-page files are full third-party documentation captures
or private-operation examples, not application source or phase audit reports.
Their source URLs/hashes and relevant public sections are retained. The complete
per-file disposition list makes these omissions explicit. None is silently
replaced with fabricated evidence.

### Reading the archived evidence

The archive is data only; no extraction or worker startup happens automatically.
Use a new destination to preserve existing local files. From the repository root,
with Python 3.12 (replace `python` by the virtual environment's Python as needed):

```text
python -m zipfile -t docs/archive/full-project-audit-evidence.zip
python -c "from pathlib import Path; Path('reports/sync-evidence-restored').mkdir(parents=True, exist_ok=False)"
python -m zipfile -e docs/archive/full-project-audit-evidence.zip reports/sync-evidence-restored
python -m tools.phase8g_archive --archive reports/sync-evidence-restored/reports/phase8f-replay-inputs.zip --output reports/sync-archive-review
```

The last output directory must also be new. The original ETH volume values,
quarantine flags and historical eligibility failures are preserved. Restoring
public history does not qualify it, create fills, authorize orders or establish
profitability. The existing Phase 8I audit documents outstanding data, liquidity,
order-feasibility and native Windows limitations.

## Secret, account-data and safety review

Reviewed both tracked/untracked project files and local artifact provenance.
Credential/token/private-key pattern checks found no credential values. The
credential module contains offline interfaces and environment-variable names;
tests contain explicit synthetic fixtures, not real keys. No credential loader
or private exchange operation was used for synchronization.

`.env` and variants, credential/private-key paths, local SQLite databases,
reports/runtime state and virtual environments remain Git-ignored. The only
environment template is `.env.example`, with **20 blank BOT variable names**.
No real `.env`, account database, private key or raw account/worker export is
included in the direct files or evidence ZIP. Recursive archive checks and an
explicit staged-file review are required before committing. Pattern checks are
not a proof against every possible secret; file type and provenance review were
also used.

All 15 frozen Phase 8F source/rule fingerprints still match. Simulated capital
remains INR 2000, maximum leverage 3x, requested margin INR 100/default 1x, 15m,
initial planned risk INR 10/hard cap INR 20, daily lower of INR 40 or 2%, three
entries per UTC day, one open long and all existing emergency/drawdown controls.
Live trading and short entries stay disabled. No private request, real order,
new paper account, parameter change or Phase 9 work is part of this sync.

## Actual test evidence

Command run from `/workspace/Coindcx-trading-bot`:

```bash
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```

**634 passed, 0 failed, 0 errors, 0 skipped**, 33.554 seconds.
Actual environment: Linux 6.18.55 x86_64/glibc 2.41, CPython 3.12.14,
SQLite 3.53.1, standard library only. The opt-in public read-only integration
test ran and passed; no private endpoints or credentials were used.

The [complete actual log](archive/full-project-sync-tests.txt) is preserved,
SHA-256 `d52aaff302f57b5c81f2121e1e000984d933df296acf0050e0a15778180525d9`.
Current native Windows execution remains **UNVERIFIED**. Earlier Phase 1 Windows
results and Linux success are not claimed as current native Windows evidence.
Passing tests are not profitability or live-readiness evidence.

New archive/manifest/log/review files do not change application behavior. Original
phase audit findings and limitations remain in force. Remote upload must be
confirmed against the exact branch commit before synchronization is reported as
successful.
