# Historical dataset contract

Put private/local datasets under `data/local/` (Git-ignored). A market CSV needs
a JSON sidecar with the same stem: `btc_inr.csv` and `btc_inr.json`. Each pair
contains one market and a single currency. Phase 2 adds a public-only downloader;
its verified documentation contract and current access limits are described in
[../docs/COINDCX_API.md](../docs/COINDCX_API.md).

CSV columns must be exactly:

```csv
timestamp,open,high,low,close,volume
2024-01-01T00:00:00+00:00,100,102,99,101,1500
2024-01-01T00:15:00+00:00,101,103,100,102,1700
```

These two rows show the format only and are insufficient history. Timestamps
represent **opening times of completed candles**, must include a timezone, and
are normalized to UTC. Bars must align to 15-minute boundaries and be sorted,
unique, and gap-free. All prices and volume must be finite and positive;
`low <= open/close <= high` is enforced. Future or still-open bars are rejected.
Do not interpolate missing prices or invent volume to make a market eligible.

Historical sidecar template (replace the source and digest, and complete review
before setting `quality_reviewed` to true):

```json
{
  "symbol": "BTC-INR",
  "quote_currency": "INR",
  "timeframe": "15m",
  "kind": "historical",
  "source": "https://public.coindcx.com/REPLACE_WITH_ACTUAL_PUBLIC_SOURCE",
  "quality_reviewed": false,
  "sha256": "REPLACE_WITH_SHA256_OF_EXACT_CSV_BYTES"
}
```

Calculate the digest in PowerShell after finalizing the CSV:

```powershell
(Get-FileHash data/local/btc_inr.csv -Algorithm SHA256).Hash.ToLower()
```

Review the original provider, exact market/instrument, currency, trading history,
timestamps, candle construction, and any anomalies before approving the file.
`source` must be a public HTTPS provenance URL with no credentials. The checksum
binds that review to the local bytes; it does not prove the provider's authenticity
or liquidity. The bot does not independently validate a provider or a listing.

Established cryptocurrencies and newly listed meme coins use the same rules;
neither market name nor token category bypasses the gate. Default eligibility
requires 2,880 consecutive candles (30 days), and replay waits until that many
bars have actually been observed before generating signals. A newer market with
too little history is excluded. At least one additional bar is needed to execute
the first eligible signal. Positive volume alone is not a liquidity guarantee;
the manual quality review remains required.

Only **INR-valued** datasets are supported. Raw USDT quotes must not be relabeled
as INR. Correct timestamp-aligned FX conversion with documented provenance is a
separate preparation step; USDT input is rejected here. Price validation uses
Decimal, so low-priced meme coins do not need to be rounded to whole rupees.

The demo generator produces `kind: synthetic` metadata, and simulation/verification
accepts it only with `--allow-synthetic`. Data inspection/import can inspect it
without that flag, and always labels its report as synthetic; those commands
never instantiate a broker. Never relabel synthetic data as historical
or use it as evidence of trading performance.

## Phase 2 normalized schema

The six-column format above remains supported with its sidecar. The normalized
export has the eight required fields and an optional ninth quote-volume field:

```csv
timestamp,open,high,low,close,volume,symbol,timeframe,quote_volume
2024-01-01T00:00:00+00:00,100,102,99,101,10,I-SYNTHETIC_INR,15m,1000
```

This row is **synthetic format illustration only**, not an actual CoinDCX market.
The `symbol` and `timeframe` columns must agree with the sidecar. The analysis
schema retains zero volume so it can report the issue; the default policy and
the simulation loader reject such bars. Negative/nonfinite values, malformed
columns, nonpositive prices, mixed symbols/timeframes, and impossible OHLC are
invalid. Incomplete/future candles are excluded from completed records and listed
in the report. API records are explicitly normalized from documented descending
order; unexpected source ordering remains a rejection reason even after sorting.
CSV order is preserved so mistakes cannot be hidden by sorting.

Sidecars for quality assessment additionally use:

```json
{
  "market_status": "active",
  "quote_volume_verified": false
}
```

These are additional fields, not a complete replacement for the sidecar template.
For an offline real market, active status is an operator attestation, not a new
network lookup. The synthetic generator's active status describes its simulated
fixture only. Public fetch obtains status from both documented discovery routes.

Leave `quote_volume_verified` false unless source documentation and review establish
that the supplied per-bar `quote_volume` values are reliable **quote-currency
turnover**. CoinDCX's documented candle `volume` is in the asset; this pipeline
does not infer exact quote volume from OHLC. Positive base volume does not prove
liquidity. The strict policy has no invented default quote threshold and reports
`LIQUIDITY_REVIEW_REQUIRED` until a defensible threshold and reliable measurements
exist. The explicit research policy retains a liquidity warning and never claims
market suitability.

An import/export creates:

- The normalized `.csv`, containing parseable completed records only.
- A version-2 `.json` sidecar, SHA-256, selected policy, `ingestion_eligible`, and
  **`quality_reviewed: false`**, even if the source was previously reviewed.
- A `.report.json` with all original row counts, exclusions, duplicates, missing
  intervals, warnings, completeness, and eligibility reasons.
- `raw/<sha256>.csv` or `.json`, containing the exact input CSV bytes or an API
  page container whose UTF-8 strings reproduce each original response body.

Inspect the report before using an output that omitted invalid/incomplete rows.
An output with `ingestion_eligible: false` remains blocked by the version-2
simulation loader even if its remaining normalized rows look valid. Repair the
original source and re-import it. Validation/re-import of a rejected version-2
export reports `SOURCE_INGESTION_REJECTED`, including under a relaxed research
policy; the normalized subset cannot erase an earlier rejection. To reassess a
different policy, use the original input and its sidecar rather than the rejected
export. Do not flip the flag to hide exclusions. Existing filenames
are never overwritten. Raw files and API cache entries remain under Git-ignored
`data/local/` when using the documented commands.

Quality reports can relax completeness/zero-volume rules for research, but the
simulation loader still requires continuous positive-volume data. Historical
version-2 data also needs explicit provenance review and passes a quality recheck;
synthetic simulation still requires `--allow-synthetic`. Legacy six-column files
retain the original Phase 1 gate rather than silently acquiring unverified market
or liquidity attestations. Re-import legacy files to adopt the new policy.

## Freshness, coverage, and reproducibility

`data validate` / `data import` use the current UTC time unless `--as-of` is given.
Historical analyses must state their reference time explicitly; a historical
endpoint is not evidence of current freshness. Fetch evaluates at the earlier of
the requested end and now, excludes bars not yet closed then, and preserves the
requested window in metadata. Completeness uses that window when available;
otherwise it is measured between observed edges with `COVERAGE_EDGES_NOT_SPECIFIED`.
Without external window boundaries, a CSV cannot reveal missing data before its
first or after its last row. The freshness allowance is a configurable local
policy, not a guarantee about exchange availability.

No candle filling or fabrication occurs. Original source data is retained;
exports are byte-reproducible for identical input, metadata, policy, and evaluation
time. Checksums bind local bytes and detect corruption; they cannot establish
authenticity, volume truthfulness, historic listing status, or future liquidity.
Current active-market discovery can introduce survivorship bias in a historical
universe; it is not a complete archive of delisted markets.
