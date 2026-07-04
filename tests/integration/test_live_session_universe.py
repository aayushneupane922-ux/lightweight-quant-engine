"""`LiveSession` running a genuine multi-symbol universe (V5 M27's disclosed
live-loop follow-up): proves the shared `PortfolioContext` this session
builds actually aggregates across every symbol's runner and every model's
book -- not just one book's view -- the same "true sum, not one model's
view" property `test_live_multi_model_runner.py` already proves at the
single-runner level, exercised here end-to-end through `LiveSession.setup()`
with a real (offline, deterministic) two-symbol universe.

Uses `CsvReplayUniverseAdapter` (a test-only fixture adapter -- the CLI's
`--csv-path` stays single-symbol; real multi-symbol live is a `--adapter
ccxt` concern) so this runs offline and deterministically, same pattern as
`test_live_async_autonomy.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from lqe.data.csv_replay import CsvReplayUniverseAdapter
from lqe.live.session import LiveSession, LiveSessionConfig
from lqe.risk.kill_switch import KillSwitch

pytest.importorskip("fastapi")
pytest.importorskip("optuna")

BTC = "BTC-USDT"
ETH = "ETH-USDT"
N_BARS = 80


def _fixture_csv(path: Path, *, offset_minutes: int, start_price: float) -> Path:
    # Interleaves with the other symbol's fixture by staggering each row's
    # minute offset by `offset_minutes` (0 for BTC, 1 for ETH) -- same
    # "genuinely interleaved by ts_open" pattern as
    # test_ccxt_adapter.py's multi-symbol test.
    now = datetime.now(UTC)
    rows = ["ts_open,open,high,low,close,volume"]
    price = start_price
    for i in range(N_BARS):
        ts = now - timedelta(minutes=(N_BARS - i) * 2 + 10) + timedelta(minutes=offset_minutes)
        close = start_price + 0.01 * i
        high = max(price, close) + 0.5
        low = min(price, close) - 0.5
        rows.append(f"{ts.isoformat()},{price:.2f},{high:.2f},{low:.2f},{close:.2f},{10 + i % 5}")
        price = close
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _session(tmp_path: Path) -> LiveSession:
    btc_csv = _fixture_csv(tmp_path / "btc.csv", offset_minutes=0, start_price=100.0)
    eth_csv = _fixture_csv(tmp_path / "eth.csv", offset_minutes=1, start_price=10.0)
    adapter = CsvReplayUniverseAdapter(
        {BTC: btc_csv, ETH: eth_csv}, exchange="demo", timeframe="1m"
    )
    session = LiveSession(
        adapter=adapter,
        kill_switch=KillSwitch(path=tmp_path / "kill.json"),
        config=LiveSessionConfig(
            symbols=[BTC, ETH], timeframe="1m", poll_seconds=0.0, lookback_bars=60,
            starting_cash=Decimal("10000"), autonomy_every=10_000,  # no autonomy step in setup
            n_trials=1, min_periods=50, use_llm=False,
        ),
    )
    assert session.setup()
    return session


def test_live_session_builds_one_runner_per_symbol(tmp_path: Path) -> None:
    session = _session(tmp_path)
    assert set(session.runners) == {BTC, ETH}
    assert session.runners[BTC].symbol == BTC
    assert session.runners[ETH].symbol == ETH
    # both bars actually flowed through -- not just one symbol's feed
    assert {bar.symbol for bar in session.bars_so_far} == {BTC, ETH}


def test_portfolio_context_reflects_the_true_multi_symbol_sum(tmp_path: Path) -> None:
    session = _session(tmp_path)

    # `session.portfolio_context` itself lags one cycle by design (refreshed
    # BEFORE each cycle's bars, from state as of the end of the PREVIOUS
    # cycle -- no-look-ahead, same as the backtest side). Recomputing the
    # snapshot fresh from `_last_close` (now fully caught up after setup())
    # proves `_portfolio_snapshot` genuinely sums every symbol x model book,
    # not just whichever runner happened to be built/processed last.
    book_equity, book_notional, _ = session._portfolio_snapshot()  # noqa: SLF001
    total_equity = sum(book_equity.values(), Decimal("0"))

    btc_only = sum(
        (v for k, v in book_equity.items() if k.startswith(f"{BTC}::")), Decimal("0")
    )
    eth_only = sum(
        (v for k, v in book_equity.items() if k.startswith(f"{ETH}::")), Decimal("0")
    )

    assert btc_only > 0
    assert eth_only > 0
    # the true aggregate must exceed either symbol's own subtotal alone --
    # proves this isn't accidentally reading just one symbol's books.
    assert total_equity == btc_only + eth_only
    assert total_equity > btc_only
    assert total_equity > eth_only

    # `session.portfolio_context` (the actual object every runner's risk
    # check reads) was genuinely refreshed with real book state during
    # setup(), not left at its Decimal("0") constructor default.
    assert session.portfolio_context.equity > 0
