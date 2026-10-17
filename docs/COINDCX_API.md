# Public API contract and evidence

## Phase 8H current official-source review

The [Phase 8H audit](PHASE8H_AUDIT.md) re-fetched the canonical HTTPS site on
17 October 2026 at 15:56:54.734969 UTC, with default TLS verification enabled.
HTTP 200; 1,118,960 bytes; SHA-256
`7817d23c17301b45bc5f79d970e8ab85536af45fa529ca7460d8eb35b705f275`.
The `#markets`, `#markets-details` and `#candles` HTML sections are byte-identical
to the retained Phase 8E sections, despite the whole-page hash changing.

The current spot source confirms the three allowed public GET routes below,
required candle `pair`/`interval`, optional millisecond `startTime`/`endTime`,
limit default 500/max 1000, intervals `1m`, `15m`, `1h`, `1d`, descending unique
opening times and volume in target-asset units. The raw source calls `time`
"open time in ms"; the client uses Unix-millisecond UTC normalization consistent
with the archived samples. The source does **not** specify candle-boundary
timezone/origin, server bound inclusivity, cross-interval aggregation/revision
rules, identical underlying trade coverage, zero/no-trade conventions, historical
retention/completeness or a numeric candle-request quota. These remain UNVERIFIED;
local filtering, completion and alignment rules are not provider guarantees.

The archived ETH 15m value differs from the exact 1m sum. This verifies an
arithmetic difference under the selected same-pair opening-time convention,
not a documented-contract violation or proven provider bug. No source value was
replaced; ETH quarantine remains enforced. No quote turnover, executable depth
or historical instrument qualification can be inferred from target-asset volume.
Fresh public metadata and four completed-candle snapshots still give NO_TRADE
at unchanged INR 100 margin/1x; they do not qualify historical orders or liquidity.
See the audit and evidence for exact sources, parameters, times and limitations.
All older sections below describe their explicitly dated evidence.

## Phase 3 Gate 0 refresh

The canonical site was reached successfully during the Phase 3 gate check.
Its current [spot candles section](https://docs.coindcx.com/#candles) names
`https://api.coindcx.com/market_data/candles` and lists `1m`, `15m`, `1h`, `1d`.
The client now uses that documented URL and still fixes the interval to `15m`.
Bounded unsigned GETs for an active INR pair returned HTTP 200, with
`open,high,low,close,volume,time`; the enabled discovery/candles integration test
also passed. This supersedes the prior runtime-connectivity blocker below.
No private requests or orders were made. This does not establish whole-history
coverage, reliable quote turnover, eligibility for any real market, or profitability.

The older source snapshot below is historical evidence. Its candle host and
larger interval list differ from the current deployed documentation and are not
the current contract. Python's default urllib User-Agent received Cloudflare
1010/403 in a diagnostic request; the project's existing descriptive User-Agent
and default TLS/redirect settings succeeded. Private credentials were not used.

## Original Phase 2 evidence (historical)

Reviewed 2026-10-17. Phase 2 used the **official CoinDCX documentation
source**, not an inferred endpoint or a third-party SDK:

- Canonical documentation: <https://docs.coindcx.com/> (direct access was blocked
  by this cloud environment's egress proxy).
- Official repository: <https://github.com/coindcx-official/rest-api>.
- Exact reviewed revision: `dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e`, dated
  **2022-03-31**. Its `CNAME` is `docs.coindcx.com` and its README identifies that
  site as the documentation deployment.
- [Markets and market details source](https://github.com/coindcx-official/rest-api/blob/dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e/source/index.html.md#L288).
- [Candles source](https://github.com/coindcx-official/rest-api/blob/dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e/source/index.html.md#L517).
- [Error definitions](https://github.com/coindcx-official/rest-api/blob/dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e/source/includes/_errors.md).

**Original compatibility limit:** the official source snapshot is old. The live
site/API could not be checked during that audit. This was documented-contract
implementation with mocked tests, not a claim that today's server behavior was
successfully exercised. The Phase 3 refresh above supersedes this access blocker.
Endpoint/schema changes must fail explicitly.

## Allowed public requests

| Purpose | Method and URL | Documented response |
| --- | --- | --- |
| Active market names | `GET https://api.coindcx.com/exchange/v1/markets` | Array of active market strings |
| Market details | `GET https://api.coindcx.com/exchange/v1/markets_details` | Array including `pair`, `symbol`, `coindcx_name`, currency names and `status` |
| Candles | `GET https://api.coindcx.com/market_data/candles` | Descending array of candle objects |

The official examples send these GETs without keys, signatures, or authentication
headers. The client accepts no API key and has no account, balance, position,
order, authentication, or POST method. Its transport whitelists these three
HTTPS host/path combinations and blocks redirects. TLS certificate and hostname
verification remain enabled.

Use the **exact `pair` returned by market details**, for example the documented
`B-BTC_USDT`, rather than synthesizing a pair from a ticker. The native pair
combines exchange code, target asset, and quote currency. CoinDCX's
`target_currency_short_name` is the traded asset; its `base_currency_short_name`
is the quote currency. Discovery cross-checks active market names and detail
status, and fetch refuses a pair that is not confirmed active.

## Candle parameters, ordering, and history

| Parameter | Official source |
| --- | --- |
| `pair` | Required; returned by market details |
| `interval` | Required |
| `startTime` | Optional Unix timestamp in milliseconds |
| `endTime` | Optional Unix timestamp in milliseconds |
| `limit` | Optional; default 500, maximum 1,000 |

Currently documented spot intervals: `1m`, `15m`, `1h`, `1d`. The older source
also listed `5m`, `30m`, `2h`, `4h`, `6h`, `8h`, `3d`, `1w`, `1M`;
those are not claimed as currently supported. This project implements **15m only**.

Each candle has `open`, `high`, `low`, `close`, `volume`, and `time`. `time` is
the opening timestamp in milliseconds. `volume` is in the **target asset**, not
the quote currency. It is not safe to relabel that field as INR/USDT turnover.
The client does not invent an exact quote volume by multiplying close × volume.

The source specifies descending time order and unique candle times. The client
requests bounded pages, advances `endTime` to the oldest opening millisecond
minus one, checks progress, and retains the raw page bodies. It normalizes API
output into ascending UTC records. Unexpected source ordering is still recorded
and makes eligibility fail; duplicates are retained and reported, not hidden.
Out-of-bound rows are filtered with a warning and retained in raw evidence.

The local range convention is **[start, end)**. The documentation does not define
inclusive/exclusive server boundaries, so the client applies its own explicit
filter and requests `endTime = end_ms - 1`. Only candles closed by the evaluation
time can enter completed records. CSVs are not silently sorted, padded, resampled,
forward-filled, deduplicated, or assigned invented volume.

The official source gives **no guaranteed oldest date, retention period, maximum
date span, or promise of complete listing history**. Empty/truncated results are
not proof of a full requested history. Quality reporting checks the requested
window, missing bars, and minimum count. A local 100-page safety budget prevents
unbounded fetches; reaching it reports `PAGE_LIMIT_REACHED`, not success.
No currently listed meme coin or established coin's actual historical coverage
was verified in this environment. Listing age alone is not an exclusion rule;
short histories report `INSUFFICIENT_HISTORY`.

## Rate limits and failures

The source error table documents 400, 401, 404, 429, 500, and 503. It does not
establish a current numeric quota for public candle requests. An old aggregate
rate note is inside a commented-out section; it is **not** treated as a current
limit. The public client uses its own conservative 0.5-second spacing, not a
claim of a server allowance.

Default retry policy: up to three attempts for timeouts/network failures, HTTP
429, and transient 500/502/503/504. Backoff is 1 then 2 seconds when no usable
server delay is given. `Retry-After` seconds and HTTP dates are honored; a delay
above the local 60-second waiting budget aborts instead of retrying early.
Ordinary 400/401/403/404 and redirects fail without retries. A proxy CONNECT 403
is classified as access denial. TLS failures are never fixed by disabling
verification. Malformed JSON/error objects are not successful responses.

The documented error body is not assumed to have invented JSON field names;
failure reporting uses HTTP status and a local error code. Live 401/403 on these
public GETs should be diagnosed as a contract/access problem, never an automatic
request for private account keys.

## Cache and integration limits

Raw successful schema-checked responses are cached locally with URL-keyed
SHA-256, fetch time, and body digest. Market responses expire after five minutes;
candle responses expire after 30 seconds. Expired, future-dated, corrupt, or
invalid cache entries do not mask an API failure. A checksum detects corruption,
not provider authenticity or malicious local modification.

Final-audit cloud probe: `python -m cli data markets` returned structured
`API_FAILURE / ACCESS_DENIED / HTTP 403` from the proxy; no market dataset was
fabricated. The optional read-only integration test remains disabled by default.
The final audit re-read environment settings: no draft is pending, and the saved
restricted policy includes `docs.coindcx.com`, `api.coindcx.com`, and
`public.coindcx.com`. Nevertheless this attached runtime still returns CONNECT
403 for documentation, market details, and candles as well as discovery. The
separately enabled integration test ended with one access-denial error. Diagnose
the runtime/proxy policy before retrying; do not infer that CoinDCX rejected the
request or requires credentials. See [PHASE2_AUDIT.md](PHASE2_AUDIT.md) for exact
commands and requirement statuses. An allowlist entry is not connectivity proof.
