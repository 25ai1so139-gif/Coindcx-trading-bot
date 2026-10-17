"""Verified spot documentation identifiers; these constants send no requests."""

DOCUMENTATION = "https://docs.coindcx.com/"
DOC_SECTIONS = ("markets", "markets-details", "candles", "authentication", "order",
                "new-order", "order-status", "active-orders", "get-balances", "spot-api-rate-limits")
SPOT_CREATE = "https://api.coindcx.com/exchange/v1/orders/create"
READ_ONLY = {
    "balances": "https://api.coindcx.com/exchange/v1/users/balances",
    "order_status": "https://api.coindcx.com/exchange/v1/orders/status",
    "active_orders": "https://api.coindcx.com/exchange/v1/orders/active_orders",
}
WIRE_STATUSES = {"init", "open", "partially_filled", "filled", "cancelled", "rejected", "partially_cancelled"}
TERMINAL = {"filled", "cancelled", "rejected", "partially_cancelled"}


class ExchangeBlocked(ValueError):
    """Only static local codes; never put credentials or raw responses here."""


def require(condition, reason):
    if not condition:
        raise ExchangeBlocked(reason)


class DisabledExecution:
    """No switch, transport argument, socket, signing or credential lookup."""
    def submit(self, *args, **kwargs):
        raise ExchangeBlocked("REAL_ORDER_EXECUTION_UNAVAILABLE")

    def cancel(self, *args, **kwargs):
        raise ExchangeBlocked("REAL_ORDER_EXECUTION_UNAVAILABLE")

    def modify(self, *args, **kwargs):
        raise ExchangeBlocked("REAL_ORDER_EXECUTION_UNAVAILABLE")

    def read_account(self, *args, **kwargs):
        raise ExchangeBlocked("PRIVATE_NETWORK_TRANSPORT_UNAVAILABLE")
