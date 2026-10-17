# Historical dataset contract

Put private/local datasets under `data/local/` (Git-ignored). A market CSV needs
a JSON sidecar with the same stem: `btc_inr.csv` and `btc_inr.json`. Each pair
contains one market and a single currency. No downloader or API client is included.

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
accepts it only with `--allow-synthetic`. Never relabel synthetic data as historical
or use it as evidence of trading performance.
