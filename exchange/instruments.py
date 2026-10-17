"""Read public constraint metadata without qualifying history or liquidity."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from config import decimal_value
from data.coindcx import PublicDataError
from data.schema import SYMBOL, utc
from exchange.contracts import ExchangeBlocked, require

NUMBERS = ("min_quantity", "max_quantity", "min_notional", "min_price", "max_price", "step")


@dataclass(frozen=True)
class Instrument:
    pair: str
    market: str
    quote: str
    asset: str
    price_precision: int
    quantity_precision: int
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal
    min_price: Decimal
    max_price: Decimal
    step: Decimal
    observed_at: datetime
    kind: str
    limit_orders_supported: bool = False

    def __post_init__(self):
        require(all(isinstance(v, str) and SYMBOL.fullmatch(v) for v in (self.pair, self.market, self.asset)), "INVALID_INSTRUMENT_SYMBOL")
        require(self.quote == "INR" and self.asset != self.quote, "UNSUPPORTED_INSTRUMENT_CURRENCY")
        require(self.kind in ("public_metadata", "synthetic_fixture"), "INVALID_METADATA_PROVENANCE")
        require(self.limit_orders_supported is True, "LIMIT_ORDER_SUPPORT_UNVERIFIED")
        for value in (self.price_precision, self.quantity_precision):
            require(type(value) is int and 0 <= value <= 18, "INVALID_INSTRUMENT_PRECISION")
        try:
            for name in NUMBERS:
                value = decimal_value(getattr(self, name), "instrument")
                require(value > 0 and len(value.as_tuple().digits) <= 32 and abs(value.as_tuple().exponent) <= 32,
                        "INVALID_INSTRUMENT_CONSTRAINTS")
                object.__setattr__(self, name, value)
            object.__setattr__(self, "observed_at", utc(self.observed_at))
        except (ValueError, TypeError, ArithmeticError):
            raise ExchangeBlocked("INVALID_INSTRUMENT_CONSTRAINTS") from None
        require(self.min_quantity <= self.max_quantity and self.min_price <= self.max_price, "INVALID_INSTRUMENT_BOUNDS")
        require(self.step % Decimal(1).scaleb(-self.quantity_precision) == 0, "INCONSISTENT_QUANTITY_PRECISION")

    def validate_size(self, quantity, price):
        quantity, price = decimal_value(quantity, "quantity"), decimal_value(price, "price")
        require(self.min_quantity <= quantity <= self.max_quantity and quantity % self.step == 0,
                "QUANTITY_CONSTRAINTS")
        require(quantity % Decimal(1).scaleb(-self.quantity_precision) == 0, "QUANTITY_PRECISION")
        require(self.min_price <= price <= self.max_price and price % Decimal(1).scaleb(-self.price_precision) == 0,
                "PRICE_CONSTRAINTS")
        require(quantity * price >= self.min_notional, "MINIMUM_NOTIONAL")


def discover_instrument(client, pair):
    """Reuse discovery/retries/cache; never interpret max_leverage=0 as 3x.

    Price precision uses the documented base-currency precision conservatively;
    no undocumented price-tick increment or derivatives capability is inferred.
    """
    discovered = client.discover()
    matches = [m for m in discovered if m.pair == pair and m.active_confirmed]
    require(len(matches) == 1, "MARKET_NOT_CONFIRMED_ACTIVE")
    market = matches[0]
    require(sum(m.active_confirmed and m.symbol == market.symbol for m in discovered) == 1,
            "AMBIGUOUS_ORDER_MARKET")
    def select(body):
        if not isinstance(body, list):
            raise ValueError("invalid details")
        rows = [row for row in body if isinstance(row, dict) and row.get("pair") == pair]
        if len(rows) != 1:
            raise ValueError("ambiguous details")
        row = rows[0]
        if (not isinstance(row.get("order_types"), list) or "limit_order" not in row["order_types"]
                or any(not isinstance(value, str) for value in row["order_types"])):
            raise ValueError("limit order not supported")
        if any(row.get(k) != v for k, v in (("symbol", market.symbol), ("status", "active"),
                    ("base_currency_short_name", market.quote_currency), ("target_currency_short_name", market.asset_currency))):
            raise ValueError("inconsistent details")
        return {name: row[name] for name in (*NUMBERS, "base_currency_precision", "target_currency_precision")}
    try:
        row = client._json("details", {}, select, timedelta(0))[0]
        return Instrument(pair, market.symbol, market.quote_currency, market.asset_currency,
                          row.pop("base_currency_precision"), row.pop("target_currency_precision"),
                          **row, observed_at=client.now(), kind="public_metadata", limit_orders_supported=True)
    except (ValueError, KeyError, TypeError, ArithmeticError):
        raise ExchangeBlocked("PUBLIC_INSTRUMENT_METADATA_UNAVAILABLE") from None
