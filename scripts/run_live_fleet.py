#!/usr/bin/env python3
"""Live multi-model paper trading against REAL market data (post-v1.0
extension, user-requested — see HANDOFF.md / COMPONENT-GUIDE.md). This is
NOT part of the v1.0-tagged `lqe` CLI surface; it's a runnable script that
composes already-tested pieces (`LiveFeed`, `LiveMultiModelRunner`,
`Orchestrator`, the Obsidian Desk) into one continuously-running session.

    python scripts/run_live_fleet.py
    python scripts/run_live_fleet.py --llm --llm-model llama3.2:3b

What it does:
  1. Builds the 51-model scaled catalog; every ADMITTED model (no
     `.[models]` extra needed for the native ones) gets its own independent
     $10,000 simulated paper book (`LiveMultiModelRunner`/`build_fleet`).
  2. Seeds real recent OHLCV bars from a public exchange endpoint (ccxt, no
     API key) and replays them through the fleet to populate the desk
     immediately.
  3. Polls for new real bars forever (default every 60s) and feeds each one
     to every model's book.
  4. Every `--autonomy-every` new bars, runs one turn of the same
     OBSERVE→HYPOTHESIZE→SEARCH→VALIDATE→DECIDE→NARRATE loop `lqe autopilot`
     runs, searching a broad 10-model surface
     (`autonomy.searchable_scaled.broad_searchable_models`) against the
     accumulated real history, narrated by the rule-based narrator or an
     optional local Ollama model (`--llm`).
  5. Serves the Obsidian Desk on 127.0.0.1, refreshing its view of the
     merged trading + autonomy audit trail as new events arrive.

Still paper-only end to end: `PaperBroker` is still the only
`ExecutionAdapter`, `make_order` is still the only `Order` constructor, ccxt
is used read-only for public OHLCV (never an order-capable call), and one
shared, disk-persistable `KillSwitch` halts every model's new entries at
once — un-overridable by the LLM (the same fail-closed 5-tool vocabulary as
`lqe autopilot`; there is no kill/clear/order tool in it). Press Ctrl+C to
stop.
"""

from __future__ import annotations

import argparse
import threading
import time
import warnings
import webbrowser
from decimal import Decimal
from pathlib import Path

from lqe.autonomy.narrator import make_narrator
from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.searchable_scaled import broad_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.clock import ManualClock
from lqe.core.engine import Engine
from lqe.core.events import MarketEvent
from lqe.data.ccxt_adapter import CcxtMarketDataAdapter
from lqe.live.control import ControlPlane
from lqe.live.live_feed import LiveFeed
from lqe.live.merge import merged_records
from lqe.live.multi_model_runner import LiveMultiModelRunner, build_fleet
from lqe.models.catalog import ModelCatalog
from lqe.models.catalog_scale import build_scaled_catalog
from lqe.risk.kill_switch import KillSwitch
from lqe.risk.model import RiskModel
from lqe.storage.state_reader import CatalogModelInfo, StateReader
from lqe.ui.app import BIND_HOST, serve
from lqe.ui.data import CatalogRow, DeskData


def _catalog_rows(catalog: ModelCatalog) -> list[CatalogRow]:
    rows = [
        CatalogRow(
            model_id=e.manifest.id, family=e.manifest.family,
            one_liner=e.manifest.one_liner, oss_libs=list(e.manifest.oss_libs),
            status=e.manifest.status,
        )
        for e in catalog.all()
    ]
    rows += [
        CatalogRow(
            model_id=q.model_id, family="—", one_liner="", oss_libs=[],
            status="unproven", quarantined=True, quarantine_reason="; ".join(q.reasons),
        )
        for q in catalog.quarantined()
    ]
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbol", default="BTC-USDT")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--lookback-bars", type=int, default=300)
    parser.add_argument("--starting-cash", type=float, default=10_000.0)
    parser.add_argument(
        "--autonomy-every", type=int, default=5,
        help="run one autonomy step every N new live bars",
    )
    parser.add_argument("--n-trials", type=int, default=8)
    parser.add_argument("--min-periods", type=int, default=200)
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--llm-model", default="llama3.2:3b")
    parser.add_argument("--kill-switch", default=None)
    parser.add_argument("--port", type=int, default=8137)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Cosmetic only: the arch/statsmodels/sklearn heavy adapters print
    # convergence and feature-name advisories to stderr on every fit --
    # harmless (they don't affect determinism or the audit) but spam a
    # long-running live session's console. Nothing in the audit log or the
    # desk depends on these; suppressing them is safe.
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", module="arch.*")
    warnings.filterwarnings("ignore", module="statsmodels.*")

    args = _build_parser().parse_args(argv)
    symbol = args.symbol
    starting_cash = Decimal(str(args.starting_cash))

    print(f"lqe live-fleet: {args.exchange} {symbol} {args.timeframe} (paper-only, real data)")
    catalog, results = build_scaled_catalog(symbol)
    admitted = catalog.all()
    print(f"fleet: {len(admitted)}/{len(results)} models admitted (rest transparently quarantined)")

    feed = LiveFeed(
        adapter=CcxtMarketDataAdapter(args.exchange), symbol=symbol,
        timeframe=args.timeframe, poll_seconds=args.poll_seconds,
    )
    print(f"seeding {args.lookback_bars} recent real bars...")
    history = feed.seed_history(lookback_bars=args.lookback_bars)
    if not history:
        print("no bars returned -- check network/exchange/symbol.")
        return 1
    print(f"seeded {len(history)} bars, last close={history[-1].c}")

    kill_switch = KillSwitch(Path(args.kill_switch)) if args.kill_switch else KillSwitch.in_memory()
    risk_model = RiskModel(kill_switch=kill_switch)

    fleet = build_fleet(admitted, starting_cash=starting_cash)
    trade_clock = ManualClock(history[0].ts_open)
    trade_engine = Engine(run_id="live-fleet", book="sandbox", clock=trade_clock)
    runner = LiveMultiModelRunner(
        engine=trade_engine, fleet=fleet, symbol=symbol, risk_model=risk_model
    )

    bars_so_far: list[MarketEvent] = []
    for bar in history:
        trade_clock.set(bar.ts_open)
        runner.process_bar(bar)
        bars_so_far.append(bar)

    orchestrator = Orchestrator(
        validator=Validator(),
        gate=PromotionGate(thresholds=GateThresholds(min_periods=args.min_periods)),
        optimizer=OptunaOptimizer(),
        searchable_models=broad_searchable_models(),
        bars=list(bars_so_far),
        symbol=symbol,
        starting_cash=starting_cash,
        run_id="live-fleet-autonomy",
        n_trials=args.n_trials,
        narrator=make_narrator(use_llm=args.llm, model=args.llm_model, seed=0, timeout_s=45.0),
    )

    catalog_info = [
        # Every admitted model is author-declared "unproven" at intake
        # (models.manifest); only a gate PASS elsewhere ever sets "validated".
        CatalogModelInfo(model_id=e.manifest.id, family=e.manifest.family, status="unproven")
        for e in admitted
    ]

    def rebuild_state_reader() -> StateReader:
        return StateReader(
            merged_records(trade_engine, orchestrator.engine), catalog=catalog_info
        )

    control = ControlPlane(kill_switch=kill_switch)
    desk_data = DeskData(
        state_reader=rebuild_state_reader(), control=control, catalog_rows=_catalog_rows(catalog)
    )

    url = f"http://{BIND_HOST}:{args.port}"
    server_thread = threading.Thread(target=lambda: serve(desk_data, port=args.port), daemon=True)
    server_thread.start()
    print(f"Obsidian Desk -> {url}  (paper-only, localhost)")
    if not args.no_browser:
        webbrowser.open(url)

    bars_since_step = 0
    step_count = 0

    def on_new_bars(new_bars: list[MarketEvent]) -> None:
        nonlocal bars_since_step, step_count
        for bar in new_bars:
            trade_clock.set(bar.ts_open)
            runner.process_bar(bar)
            bars_so_far.append(bar)
            bars_since_step += 1

        # Grow the orchestrator's data window as real history accumulates.
        # `bars` is a public dataclass field; `_search_bars` mirrors exactly
        # the slice `Orchestrator.__post_init__` itself computes from
        # `bars`/`search_fraction` -- re-deriving it here (rather than
        # re-running `__post_init__`, which would also reset its own engine
        # and discard prior autonomy events) keeps that invariant intact.
        orchestrator.bars = list(bars_so_far)
        cut = max(2, int(len(orchestrator.bars) * orchestrator.search_fraction))
        orchestrator._search_bars = list(orchestrator.bars[:cut])  # noqa: SLF001

        if bars_since_step >= args.autonomy_every:
            bars_since_step = 0
            step_count += 1
            state = orchestrator.step(now=new_bars[-1].ts_open)
            tag = " -> promoted" if state.promoted else ""
            print(f"[autonomy step {step_count}] {state.focus_model}: {state.verdict}{tag}")
            if state.narration:
                print(f"    {state.narration}")

        desk_data.set_state_reader(rebuild_state_reader())
        print(
            f"processed {len(new_bars)} new bar(s); total bars={len(bars_so_far)}; "
            f"kill_active={kill_switch.active}"
        )

    print(
        f"polling {args.exchange} every {args.poll_seconds:.0f}s for new {symbol} "
        f"{args.timeframe} bars... Ctrl+C to stop."
    )
    try:
        while True:
            time.sleep(args.poll_seconds)
            try:
                new_bars = feed.poll_new_bars()
            except Exception as exc:  # noqa: BLE001 - a transient network/exchange
                # hiccup must not crash a long-running live demo session;
                # log it and simply retry on the next poll cycle.
                print(f"  [poll error, retrying next cycle] {type(exc).__name__}: {exc}")
                continue
            if new_bars:
                on_new_bars(new_bars)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
