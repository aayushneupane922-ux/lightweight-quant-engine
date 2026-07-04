"""docs/14 (v4, M23/M24): every new sleeve C/D/F strategy repeatedly
declares itself "long-only" in its manifest's `failure_modes` (this
engine's short-selling path is explicitly out of scope -- `risk/rules.py`
rejects any SELL that would take a position net-short, and
`portfolio/accounting.py` raises rather than silently going short). That
claim is verified here, not just asserted in prose: every model in the
104-model scaled catalog is run through a real, audited multi-symbol
backtest with both an uptrend and a downtrend (and a perp premium, to
tempt the basis-carry models) -- across the whole catalog, on this
adversarial bar stream, not a single `SignalEvent` may ever carry
`direction == "SHORT"`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.catalog_scale import build_scaled_catalog

SYMBOL: Symbol = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _adversarial_bars(n: int) -> list[MarketEvent]:
    """Up for the first half, down for the second half -- a real reversal
    that would tempt a short-seller on the way down -- plus a perp trading
    at a rich premium throughout, an underperforming alt, and a second
    exchange's funding-adjacent alt, so every sleeve gets a real chance to
    misbehave if it were ever going to."""
    bars: list[MarketEvent] = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        half = n // 2
        btc = 100.0 + i if i < half else 100.0 + half - (i - half)
        eth = btc * 0.4 - i * 0.05  # a steady underperformer
        sol = btc * 0.2 + (5.0 if i % 2 == 0 else -5.0)  # whipsaws
        perp = btc * 1.01
        for symbol, price in (
            ("ETH-USDT", eth), ("SOL-USDT", sol), ("BTC-USDT-PERP", perp), (SYMBOL, btc),
        ):
            p = Decimal(str(round(price, 4)))
            bars.append(
                MarketEvent(
                    exchange="synthetic", symbol=symbol, timeframe="1m", ts_open=ts,
                    o=p, h=p + Decimal("0.5"), l=p - Decimal("0.5"), c=p,
                    v=100.0, source_version="test",
                )
            )
    return bars


def test_no_model_in_the_full_scaled_catalog_ever_signals_short() -> None:
    bars = _adversarial_bars(400)
    catalog, _ = build_scaled_catalog(SYMBOL)
    offenders: dict[str, list[str]] = {}
    for entry in catalog.all():
        strategy = entry.strategy_factory()
        session = run_backtest(
            run_id=f"no-shorting:{entry.manifest.id}", symbol=SYMBOL, bars=bars,
            strategy=strategy, starting_cash=Decimal("10000"),
        )
        assert session.engine.audit.verify()
        shorts = [
            envelope.payload["reason"]
            for envelope in session.engine.audit.records
            if envelope.type == "SignalEvent" and envelope.payload["direction"] == "SHORT"
        ]
        if shorts:
            offenders[entry.manifest.id] = shorts
    assert offenders == {}, f"models emitted a SHORT signal: {offenders}"
