"""Fail-closed Phase 2 eligibility for historical simulation entry points."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from config import Settings
from data.loader import MarketData, load_csv
from data.models import Candle
from data.quality import DataPolicy, assess
from data.schema import utc
from data.storage import read_csv
from risk.proposal import MarketContext


class BacktestBlocked(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EligibleDataset:
    market: MarketData
    evidence: dict
    risk_context: MarketContext | None = None


def market_digest(market: MarketData) -> str:
    return hashlib.sha256(json.dumps(asdict(market), sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def load_eligible(path: str | Path, settings: Settings, *, allow_synthetic: bool = False,
                  as_of: datetime | None = None, policy: DataPolicy | None = None,
                  loaded_market: MarketData | None = None) -> EligibleDataset:
    """Freshness is relative to an explicit historical cutoff, never relabeled as current.

    The legacy loader stays compatible; CLI simulations now additionally require
    the same strict Phase 2 history/liquidity checks as real-data signal review.
    """
    try:
        market = loaded_market or load_csv(path, settings.min_history_bars, allow_synthetic)
        if market.kind == "synthetic" and not allow_synthetic:
            raise ValueError("synthetic data requires explicit opt-in")
        imported = read_csv(path)
        stored = DataPolicy(**{"min_history_bars": settings.min_history_bars,
                               **imported.metadata.get("data_policy", {})})
        selected = policy or stored
        strict = replace(selected, min_history_bars=max(settings.min_history_bars, stored.min_history_bars,
                                                       selected.min_history_bars),
                         min_completeness=1, max_zero_volume_fraction=0,
                         max_staleness_minutes=min(30, stored.max_staleness_minutes, selected.max_staleness_minutes),
                         require_verified_liquidity=market.kind != "synthetic")
        cutoff = utc(as_of) if as_of is not None else market.candles[-1].closed_at
        if cutoff > datetime.now(timezone.utc):
            raise ValueError("historical data cutoff cannot be in the future")
        result = assess(imported.rows, imported.metadata, strict, cutoff)
        if not result.report["eligible"]:
            raise BacktestBlocked("BLOCKED: " + ", ".join(result.report["reasons"]))
        assessed = tuple(Candle(row.timestamp, row.open, row.high, row.low, row.close, row.volume)
                         for row in result.completed)
        if (assessed != market.candles or imported.metadata["symbol"] != market.symbol
                or imported.metadata["kind"] != market.kind or imported.metadata["source"] != market.source
                or (market.kind == "historical" and imported.metadata.get("quality_reviewed") is not True)):
            raise ValueError("data or provenance changed between eligibility reads")
        host = urlparse(market.source).hostname
        source_class = ("synthetic" if market.kind == "synthetic" else
                        "coindcx_public_provenance" if host in {"api.coindcx.com", "public.coindcx.com"}
                        else "imported_external_provenance")
        return EligibleDataset(market, {
            "source": market.source, "source_class": source_class, "kind": market.kind,
            "csv_sha256": hashlib.sha256(imported.raw).hexdigest(),
            "market_sha256": market_digest(market),
            "sidecar_sha256": hashlib.sha256(Path(path).with_suffix(".json").read_bytes()).hexdigest(),
            "quality": result.report, "freshness_reference": "historical_as_of",
            "historical_as_of": cutoff.isoformat(),
            "current_market_freshness_qualified": False,
            "provenance_limit": "operator attestation/checksum, not independently authenticated history or liquidity"},
            MarketContext.reviewed(imported.metadata, result.report, settings))
    except BacktestBlocked:
        raise
    except (ValueError, OSError, TypeError) as exc:
        raise BacktestBlocked(f"BLOCKED: {exc}") from exc
