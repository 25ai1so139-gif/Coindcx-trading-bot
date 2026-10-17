# Phase 7: public metadata and offline order readiness

This phase implements **offline request validation and synthetic reconciliation**.
It does not enable authenticated networking, submit/cancel/modify orders, establish
real-market eligibility or certify live readiness. All existing backtesting and
paper execution paths remain independent of exchange execution. No Phase 8 work
is included. See [the audit](PHASE7_AUDIT.md) for counts and requirement statuses.

## Gate 0 and scope

Phase 5 gate, Phase 6A state recovery and Phase 6B worker/CLI were inspected and
their complete regressions passed before implementation. Public discovery/candle
integration was enabled separately and passed. The real worker was also exercised
in a temporary account using public data: it rejected zero-volume history and
stopped durably with no entries. A qualified real-data paper fill remains
UNVERIFIED. Gate 0 item 6 permits documenting this limitation; implementation here
therefore proceeds only as offline/mock readiness. Real-market and authenticated
execution readiness remain BLOCKED, regardless of unit tests or publication.

Settings stay unchanged: ₹2,000 starting capital, margin distinct from notional,
15m, max 3x, initial 0.5% planned risk (₹10 at ₹2,000) with ₹20 ceiling, daily loss
min(₹40, 2% daily starting equity), three entries per UTC day, one position,
drawdown/emergency halts and short entries disabled. The spot request builder
supports **1x only**, preserving the existing real-spot restriction. It does not
infer 3x capability from spot candles or a max_leverage field.

## Official contract reviewed

Source: https://docs.coindcx.com/ (reviewed 2026-10-17 with verified TLS). The captured
HTML SHA-256 and observed public results are in
[phase7-public-evidence.json](examples/phase7-public-evidence.json). This is a
deployed-document snapshot, not a versioned exchange implementation guarantee.

| Purpose | Method / URL | Source |
| --- | --- | --- |
| Active symbols | GET https://api.coindcx.com/exchange/v1/markets | https://docs.coindcx.com/#markets |
| Native pair and constraints | GET https://api.coindcx.com/exchange/v1/markets_details | https://docs.coindcx.com/#markets-details |
| OHLCV | GET https://api.coindcx.com/market_data/candles | https://docs.coindcx.com/#candles |
| Authentication format, offline signing only | JSON POST, HMAC-SHA256 over exact UTF-8 body, headers X-AUTH-APIKEY / X-AUTH-SIGNATURE | https://docs.coindcx.com/#authentication |
| Spot order shape, never transmitted | POST https://api.coindcx.com/exchange/v1/orders/create | https://docs.coindcx.com/#new-order |
| Spot status shape, mocked only | POST https://api.coindcx.com/exchange/v1/orders/status | https://docs.coindcx.com/#order-status |
| Active-order shape, no retrieval | POST https://api.coindcx.com/exchange/v1/orders/active_orders | https://docs.coindcx.com/#active-orders |
| Balance shape, no retrieval | POST https://api.coindcx.com/exchange/v1/users/balances | https://docs.coindcx.com/#get-balances |

Public GET examples require no credentials. Candles expose open/high/low/close/
volume/time, with opening time in milliseconds and target-asset volume. Current
documented intervals are 1m/15m/1h/1d; only 15m is implemented. The existing client
still enforces unsigned whitelisted GETs, TLS, redirect blocking, response bounds,
bounded retries, Retry-After and local spacing. History coverage/liquidity checks
are unchanged. The docs do not establish a public-candle request quota or guaranteed
retention. The 0.5-second spacing is local policy, not proof of a server quota.

Current spot docs name statuses init, open, partially_filled, filled, cancelled,
rejected and partially_cancelled. New order responses use an object containing an
orders array; status returns one order object. Spot order IDs are now positive
numeric strings, and status queries require numeric IDs or client_order_id.
Older UUID examples remain in other sections; they are not accepted by this spot
normalizer. The heading create-order describes futures; the spot source is
**new-order**. Futures/margin routes and capabilities are not implemented.

client_order_id must be unique per user/order and reuse is rejected. This does
**not** document replay-safe idempotent submission. The local model therefore
never resends an unresolved request. Current documented spot quotas include
create/status 2,000 per 60 seconds and active orders 300 per 60 seconds; no private
poller/sender is installed or claimed compliant with these quotas. No official
sandbox was independently verified or used; all private behavior uses mocks.

## Public instrument inspection

exchange/instruments.py reuses PublicClient discovery, parsing, retries and
transport. Native candle pair and spot order market identifier remain distinct.
Discovery must confirm the pair active and its order market mapping unambiguous.
A fresh market-details request must agree with that identity and explicitly list
limit_order support. Missing constraints/types or inconsistent discovery fail
closed. The existing data markets output format is unchanged.

Instrument records carry quantity step/precision, min/max quantity, min notional,
min/max price, base-currency price precision, lookup time and provenance. Decimal
validation rejects nonfinite/invalid bounds. It never rounds a risk-approved plan
to satisfy a minimum. Base-currency precision is used as a **conservative local
price-decimal check**; the exact exchange price-tick rule has not been independently
validated. It is marked UNVERIFIED, and actual order execution remains unavailable.
Metadata inspection never upgrades quality_reviewed/liquidity_verified, fills in
invented quote turnover or changes Phase 6B eligibility.

PowerShell from the checkout after Python 3.12 setup:

~~~powershell
$markets = .\.venv\Scripts\python.exe -m cli data markets | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Public discovery failed." }
$pair = ($markets.markets | Where-Object { $_.active_confirmed -and $_.quote_currency -eq "INR" -and $_.asset_currency -eq "BTC" } | Select-Object -First 1).pair
if (-not $pair) { throw "No confirmed active BTC/INR pair. Do not invent one." }
.\.venv\Scripts\python.exe -m cli exchange instrument --pair $pair
if ($LASTEXITCODE -ne 0) { throw "Instrument constraints unavailable." }
~~~

Success means PUBLIC_METADATA_ONLY, with market_qualified=false and
price_tick_exchange_validated=false. It is not approval to trade this symbol.
Established and newly listed meme coins follow the same history/quality rules;
no listing age shortcut, ticker allowlist or fake history is introduced.

## Authentication preparation and limitations

exchange/auth.py has a disabled-by-default ReadOnlyPolicy. Future approved names
are COINDCX_API_KEY, COINDCX_API_SECRET and COINDCX_ENABLE_READ_ONLY (strict 0/1).
No public test needs these variables. The existing core-only .env.example stays
unchanged; no credentials were read from the real environment in this task.
Do not supply keys in chat, logs or committed files.

Credentials validate only a bounded printable local string envelope; the docs do
not establish a fixed key format. Their repr is redacted and they expose no normal
dataclass/dictionary serialization. This does **not** prove the key is genuine,
has read-only permissions or lacks withdrawal permission. Those properties are
UNVERIFIED without a separately approved permission review/read-only test.

prepare_read_only can construct and sign bodies **locally** for balances, a
client-ID status query or the first bounded active-orders page. Both enabled=True
and separately_approved=True are required even for that offline operation. The
environment flag alone cannot enable it. There is no private network transport,
no full account pagination/normalization and no automatic credential lookup on
public paths. Signed envelopes and returned headers are sensitive memory; their
repr hides contents, but an explicit accessor for offline tests exposes headers.
Never log or persist those headers. Python-level inspection can access memory;
this is not a secret vault or automatic memory erasure mechanism.

There is no signing helper for creation, cancellation, modification, transfers or
withdrawals. DisabledExecution methods always raise, even if passed enabled=True
or credentials. Server permissions are not inferred from a local boolean. Never
enable withdrawals; future account testing must use only verified minimal read
permissions, under separate approval. No authenticated endpoint was contacted.

## Dry-run request construction

preview_entry in exchange/orders.py accepts Settings, VerificationAccount,
EntryProposal, Instrument, timestamp/client ID and a mandatory RiskAudit. It
rechecks the account freshness and calls risk.entry.approve_entry every time.
It accepts no caller-supplied plan or cached approval. Missing stop, stale/invalid
history, incomplete/duplicate candles, SHORT, daily/drawdown/emergency halt,
entry count, position, leverage and sizing rejections remain the central gate's
decision. An uncertain execution context is also refused by that gate.

After risk approval it requires matching fresh (<=5 minute) instrument evidence,
consistent risk/order constraints, explicit limit support, 1x spot sizing and
exact step/decimal/minimum/maximum compliance. No quantity or price rounding is
performed. The unsigned spot BUY/limit body contains only documented fields:
side, order_type, market, price_per_unit, total_quantity, timestamp and
client_order_id. Decimal values are serialized as exact JSON numbers without
binary floating-point conversion. Local client IDs use a deliberately narrow
ASCII/100-character policy; that length is not an asserted exchange limit.

The result says DRY_RUN_ONLY, orders_submitted=0 and live_trading_enabled=false.
It contains no authentication headers and sends nothing. A preview, approved
RiskRecord or plan is not a fill or permission to execute. No exchange-hosted
protective stop, OCO/bracket order, liquidation model or exit-order adapter is
implemented. The risk plan's stop is still a simulation reference.

## Durable mocked reconciliation

exchange/reconciliation.py provides an explicitly opted-in MockOrderJournal.
Its database label is SYNTHETIC_MOCK_ONLY. It is a different SQLite application
and schema from Phase 6A paper accounts and must never open/modify their files.
Creation binds settings, symbol, an account UUID and implementation fingerprint.
It requires a paper profile and a synthetic ₹2,000 baseline; unexplained source
equity gains, deposits, other account kinds or weaker limits cannot authorize a
request. The original PaperBroker, its equity/positions/counts and CLI are not
mutated by mock order observations. Mock quote/asset projections are explicitly
separate from paper or exchange balances and from performance reporting.

The schema has append-only canonical events (revision, payload, SHA-256 digest,
hash chain) plus a head anchor. Reads replay all events and validate schema,
constraints, timestamps, identity, request/plan/cost consistency and monotonic
statuses. Writes use BEGIN IMMEDIATE, DELETE journaling and synchronous=FULL;
request reservation and its approval evidence commit before acknowledgement.
No implicit file creation on resume, overwrite, automatic reset or corruption
fallback exists. Unknown versions/settings/implementation changes fail closed.
Any storage/ambiguous-commit error poisons the handle; reopen explicitly to inspect
what committed. The returned snapshot is detached. No credentials, signatures,
free-form provider errors or arbitrary response extras enter the journal.

Transitions and blocking rules:

| Input / state | Local behavior |
| --- | --- |
| Gate-approved draft | PREPARED_NOT_SENT; reserve locally, block another draft |
| init / open | Observed pending/accepted; retain block |
| Timeout, auth error, 429 | UNKNOWN; never resend; survives restart |
| Unknown/malformed wire status | UNKNOWN; preserve the last valid report |
| Valid partial/full fill | Track cumulative mock quantity/cost/fees; position exposure blocks new entry |
| Rejected / cancelled with proven zero fill | Require matching mock account reconciliation before releasing the reservation |
| partially_cancelled | Quarantine as UNVERIFIED_PARTIAL_CANCELLATION; do not infer execution from ambiguous cancellation remainder fields |
| Duplicate identical status | No-op; no duplicate fill/cost/event |
| Changed identity, regressed fill/fee/time/average or reused server ID | Durable fault; new drafts blocked |
| Report/failure for an unknown local request | Durable UNEXPECTED_ORDER fault, including after reopen |
| Invalid or mismatched mock account report | Durable ACCOUNT_MISMATCH fault |
| Emergency halt | Persistently latch; feed that latch into the shared gate; no cancel/exit request sent |

Raw spot statuses are whitelisted to documented fields. Created/updated times
must be valid milliseconds, nonfuture and consistent; order IDs are positive
numeric strings. The transition graph is a **conservative local admissibility
policy**, not a claimed exchange guarantee. Same-quantity average corrections,
late terminal changes and ambiguous partial cancellations stay unresolved pending
independent evidence. Failures never silently remove known exposure.

expected_mock_account projects total INR (including locked funds) and asset units
from mocked fills, explicitly assuming fee_amount is in quote currency. The
MockAccountReport fields cash_total, asset_quantity and open_order_ids are
**internal synthetic fields, not a CoinDCX response schema**. The official balance
shape is currency/balance/locked_balance; exact balance semantics and fee currency
were not independently verified. No real balance translator or account fetcher
is enabled. The comparison tests local-state mismatches; it does not prove an
exchange account was reconciled. Excessive costs latch a fault; there is no
automatic repair, refund, forced balancing, exit model or fault-clear command.

Known status plus matching mock-account evidence can resolve a recoverable UNKNOWN
with no fills and release a reservation. Fault latches are permanent for this
unreleased model; manual investigation/design review is required. Filled positions
remain held and block new entries; this phase implements no exit/trading loop.
Request preparation does not increment actual paper daily counts or create fills.
All actual paper entries still use Phase 5/6A/6B. Before any real integration,
partial fills, risk reservations, daily counts and account identity must have one
transactionally consistent execution authority; this journal is not that bridge.

Client-ID uniqueness is local to one journal; CoinDCX documents uniqueness per
user. A new file/account cannot establish server-wide uniqueness. Do not infer
exactly-once exchange execution from these tests. A live handle detects rollback
against its pinned chain; a fresh open can take expected_head=<trusted prior
JournalSnapshot>. Without independent latest evidence, whole-valid-file rollback
cannot be detected in a fresh process. Hashes detect corruption, not malicious
forgery. There is no automated backup/restore/compaction service; use validated
storage procedures and never recover by inventing missing requests or balances.

## Verification and Phase 8 prerequisites

From native Windows PowerShell (instructions only; not executed here):

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
.\.venv\Scripts\python.exe -c "import sys,platform,sqlite3; print(platform.platform(),sys.version,sqlite3.sqlite_version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3,12)"
if ($LASTEXITCODE -ne 0) { throw "Native Windows/Python 3.12 required for Windows evidence." }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest tests.test_exchange_adapter tests.test_order_reconciliation tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v
if ($LASTEXITCODE -ne 0) { throw "Safety verification failed." }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Full regression failed." }
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_coindcx_public -v
if ($LASTEXITCODE -ne 0) { throw "Read-only public smoke failed." }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
~~~

Before Phase 8, obtain approval and resolve the intended next scope explicitly.
Any exchange-execution readiness requires independently qualified real history/
liquidity/instruments/costs, native Windows evidence if Windows is the target,
verified permission scope and separately approved read-only account validation,
verified numeric precision/minimum/tick/fee-currency behavior, complete account
pagination and reconciliation, unambiguous partial-cancellation/trade evidence,
and an atomic link between real fill lifecycle and the authoritative risk state.
No assumption of sandbox availability, live stop protection, derivatives support,
24/7 operation or profitable strategies is justified by the current mocks.
Durable hosting, monitoring and capacity/physical-failure testing remain separate
requirements. Publishing the environment does not start or keep a worker alive.
