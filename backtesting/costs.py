"""Explicit simulation assumptions, not an exchange fee or execution schedule."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from decimal import Context, ROUND_HALF_EVEN, localcontext
from functools import wraps

from config import Settings


def fixed_decimal(function):
    """Replay math is independent of a Python caller's ambient Decimal context."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
            return function(*args, **kwargs)
    return wrapped


@dataclass(frozen=True, slots=True)
class CostModel:
    fee_rate: Decimal
    slippage_rate: Decimal

    @classmethod
    def from_settings(cls, settings: Settings) -> "CostModel":
        return cls(settings.fee_rate, settings.slippage_rate)

    def entry_fill(self, reference: Decimal) -> Decimal:
        return reference * (1 + self.slippage_rate)

    def exit_fill(self, reference: Decimal) -> Decimal:
        return reference * (1 - self.slippage_rate)

    def fee(self, quantity: Decimal, fill: Decimal) -> Decimal:
        return quantity * fill * self.fee_rate

    def assumptions(self) -> dict:
        return {**asdict(self), "schedule_verified": False,
                "rate_basis": "user-configurable fraction of filled notional on EACH entry and exit",
                "fill_basis": "adverse fractional price adjustment on EACH entry and exit",
                "spread": "not separately modeled; no historical bid/ask evidence",
                "funding": "not modeled; no supported funding data or derivatives contract",
                "partial_fills": "not modeled; no order-book/queue evidence",
                "other_costs": "tax, borrow, liquidation and exchange size rules not modeled",
                "leverage": "abstract collateral simulation, not a verified CoinDCX margin product"}
