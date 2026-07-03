"""`lqe` command-line entry point. Thin wiring only — no decision logic lives
here; every subcommand just builds an adapter and calls into `lqe.data`/
`lqe.storage` (docs/10 M2: `cli lqe ingest`).
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from lqe.analytics.metrics import compute_metrics
from lqe.analytics.registry import ExperimentRegistry
from lqe.analytics.tearsheet import render_tearsheet
from lqe.autonomy.promotion_gate import PromotionGate
from lqe.autonomy.validator import PromotionCandidate, Validator
from lqe.backtest.runner import run_backtest
from lqe.core.errors import LqeError
from lqe.data.base import MarketDataAdapter
from lqe.data.ccxt_adapter import CcxtMarketDataAdapter
from lqe.data.csv_replay import CsvReplayAdapter
from lqe.data.ingest import ingest
from lqe.models.base import Strategy
from lqe.models.plugins.trend_ma_cross import TrendMaCross
from lqe.storage.catalog import Catalog
from lqe.storage.replay_bundle import load_bundle

STRATEGIES = {"trend_ma_cross"}


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        )
        return completed.stdout.strip()
    except Exception:
        return "unknown"


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _cmd_ingest(args: argparse.Namespace) -> int:
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    adapter: MarketDataAdapter
    if args.adapter == "ccxt":
        adapter = CcxtMarketDataAdapter(args.exchange)
    else:
        adapter = CsvReplayAdapter(
            args.csv_path, exchange=args.exchange, symbol=args.symbol, timeframe=args.timeframe
        )

    with Catalog(root / args.catalog) as catalog:
        result = ingest(
            adapter,
            exchange=args.exchange,
            symbol=args.symbol,
            timeframe=args.timeframe,
            root=root,
            catalog=catalog,
            start=_parse_ts(args.start),
            end=_parse_ts(args.end),
        )

    print(
        f"ingested {result.rows} bars -> version {result.version_id} "
        f"(checksum {result.checksum[:12]}...)"
    )
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    root = Path(args.root)
    bundle, bars = load_bundle(root, args.bundle)
    symbol_bars = [bar for bar in bars if bar.symbol == args.symbol]
    if not symbol_bars:
        print(f"no bars for symbol {args.symbol!r} in bundle {args.bundle!r}")
        return 1

    strategy: Strategy = TrendMaCross(symbol=args.symbol, fast=args.fast, slow=args.slow)
    session = run_backtest(
        run_id=f"backtest:{args.bundle}:{strategy.name}",
        symbol=args.symbol,
        bars=symbol_bars,
        strategy=strategy,
        starting_cash=Decimal(str(args.starting_cash)),
        slippage_bps=args.slippage_bps,
        commission_bps=args.commission_bps,
    )

    final_equity = session.accounting.equity({args.symbol: symbol_bars[-1].c})
    print(f"bundle {bundle.bundle_id} ({len(symbol_bars)} bars) -> strategy {strategy.name}")
    print(f"starting cash: {args.starting_cash}  final equity: {final_equity}")
    print(f"audit hash-chain verifies: {session.engine.audit.verify()}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root)
    bundle, bars = load_bundle(root, args.bundle)
    symbol_bars = [bar for bar in bars if bar.symbol == args.symbol]
    if not symbol_bars:
        print(f"no bars for symbol {args.symbol!r} in bundle {args.bundle!r}")
        return 1

    starting_cash = Decimal(str(args.starting_cash))

    def _strategy_factory() -> Strategy:
        return TrendMaCross(symbol=args.symbol, fast=args.fast, slow=args.slow)

    candidate = PromotionCandidate(
        candidate_id=f"{args.bundle}:{args.strategy}:{args.fast}-{args.slow}",
        model_id=args.strategy,
        params={"fast": args.fast, "slow": args.slow},
        book="sandbox",
        hypo_id=args.hypo_id,
        study_id=args.study_id,
        data_version=bundle.bundle_id,
        seed=bundle.seed,
        n_trials_context=args.n_trials_context,
    )

    validator = Validator(n_folds=args.n_folds, random_control_reps=args.random_control_reps)
    result = validator.validate(
        candidate,
        bars=symbol_bars,
        symbol=args.symbol,
        strategy_factory=_strategy_factory,
        starting_cash=starting_cash,
    )
    gate_result = PromotionGate().check(candidate, result, n_periods=len(symbol_bars))

    full_session = run_backtest(
        run_id=f"validate-report:{candidate.candidate_id}",
        symbol=args.symbol,
        bars=symbol_bars,
        strategy=_strategy_factory(),
        starting_cash=starting_cash,
        commission_bps=args.commission_bps,
    )
    metrics = compute_metrics(
        equity_curve=full_session.equity_curve,
        trade_pnls=full_session.trade_pnls,
        trade_notionals=full_session.trade_notionals,
        periods_per_year=365 * 24 * 60,
    )
    sheet = render_tearsheet(
        model_id=args.strategy,
        metrics=metrics,
        gate_result=gate_result,
        cost_bps_used=args.commission_bps,
    )

    with Catalog(root / args.catalog) as catalog:
        registry = ExperimentRegistry(catalog)
        registry.record_experiment(
            run_id=f"validate:{candidate.candidate_id}",
            mode="backtest",
            book="sandbox",
            strategy=args.strategy,
            params=candidate.params,
            data_version=bundle.bundle_id,
            git_sha=_git_sha(),
            seed=bundle.seed,
            date_start=symbol_bars[0].ts_open,
            date_end=symbol_bars[-1].ts_open,
            split="full",
            sharpe=metrics.sharpe,
            dsr=gate_result.dsr,
            pbo=gate_result.pbo,
            max_dd=metrics.max_drawdown,
            turnover=metrics.turnover,
            n_trades=metrics.n_trades,
            cost_bps=args.commission_bps,
            passed_gate=gate_result.verdict == "PASS",
            created_at=datetime.now(UTC),
        )

    print(sheet)
    if args.tearsheet_out:
        Path(args.tearsheet_out).write_text(sheet, encoding="utf-8")
        print(f"tearsheet written to {args.tearsheet_out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lqe")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Fetch, validate, and curate OHLCV bars.")
    ingest_parser.add_argument("--adapter", choices=["ccxt", "csv"], required=True)
    ingest_parser.add_argument("--exchange", required=True)
    ingest_parser.add_argument(
        "--symbol", required=True, help="Canonical BASE-QUOTE, e.g. BTC-USDT"
    )
    ingest_parser.add_argument("--timeframe", required=True)
    ingest_parser.add_argument("--root", default="data", help="Storage root (default: ./data)")
    ingest_parser.add_argument(
        "--catalog", default="catalog.duckdb", help="Catalog path, relative to root"
    )
    ingest_parser.add_argument("--csv-path", help="Required when --adapter csv")
    ingest_parser.add_argument("--start", default=None, help="ISO-8601 UTC, inclusive")
    ingest_parser.add_argument("--end", default=None, help="ISO-8601 UTC, exclusive")
    ingest_parser.set_defaults(func=_cmd_ingest)

    backtest_parser = subparsers.add_parser("backtest", help="Run a deterministic backtest.")
    backtest_parser.add_argument("--bundle", required=True, help="Replay bundle id")
    backtest_parser.add_argument("--root", default="data", help="Storage root (default: ./data)")
    backtest_parser.add_argument(
        "--symbol", required=True, help="Canonical BASE-QUOTE, e.g. BTC-USDT"
    )
    backtest_parser.add_argument(
        "--strategy", choices=sorted(STRATEGIES), default="trend_ma_cross"
    )
    backtest_parser.add_argument("--fast", type=int, default=12)
    backtest_parser.add_argument("--slow", type=int, default=48)
    backtest_parser.add_argument("--starting-cash", type=str, default="10000")
    backtest_parser.add_argument("--slippage-bps", type=float, default=5.0)
    backtest_parser.add_argument("--commission-bps", type=float, default=10.0)
    backtest_parser.set_defaults(func=_cmd_backtest)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Run the promotion gate (walk-forward + DSR/PBO + cost sweep + benchmarks).",
    )
    validate_parser.add_argument("--bundle", required=True, help="Replay bundle id")
    validate_parser.add_argument("--root", default="data", help="Storage root (default: ./data)")
    validate_parser.add_argument(
        "--symbol", required=True, help="Canonical BASE-QUOTE, e.g. BTC-USDT"
    )
    validate_parser.add_argument(
        "--strategy", choices=sorted(STRATEGIES), default="trend_ma_cross"
    )
    validate_parser.add_argument("--fast", type=int, default=12)
    validate_parser.add_argument("--slow", type=int, default=48)
    validate_parser.add_argument("--starting-cash", type=str, default="10000")
    validate_parser.add_argument("--commission-bps", type=float, default=10.0)
    validate_parser.add_argument("--n-folds", type=int, default=4)
    validate_parser.add_argument("--random-control-reps", type=int, default=20)
    validate_parser.add_argument(
        "--n-trials-context", type=int, default=1, help="Honest trial count feeding DSR/PBO"
    )
    validate_parser.add_argument("--hypo-id", default="manual")
    validate_parser.add_argument("--study-id", default="manual")
    validate_parser.add_argument(
        "--catalog", default="catalog.duckdb", help="Catalog path, relative to root"
    )
    validate_parser.add_argument(
        "--tearsheet-out", default=None, help="Optional file to write the tearsheet to"
    )
    validate_parser.set_defaults(func=_cmd_validate)

    catalog_parser = subparsers.add_parser(
        "catalog", help="List the scaled model catalog (admitted + transparently quarantined)."
    )
    catalog_parser.add_argument("--symbol", default="BTC-USDT")
    catalog_parser.set_defaults(func=_cmd_catalog)

    check_config_parser = subparsers.add_parser(
        "check-config", help="Validate a config file against the paper-only lockout schema."
    )
    check_config_parser.add_argument("path", help="Path to a .json or .toml config file.")
    check_config_parser.set_defaults(func=_cmd_check_config)

    autopilot_parser = subparsers.add_parser(
        "autopilot", help="Run the rule-based autonomy loop over a replay bundle (paper-only)."
    )
    autopilot_parser.add_argument("--root", default="runs")
    autopilot_parser.add_argument("--bundle", required=True)
    autopilot_parser.add_argument("--symbol", default="BTC-USDT")
    autopilot_parser.add_argument("--steps", type=int, default=3)
    autopilot_parser.add_argument("--trials", type=int, default=12)
    autopilot_parser.add_argument("--seed", type=int, default=0)
    autopilot_parser.add_argument("--starting-cash", type=float, default=10_000.0)
    autopilot_parser.add_argument("--min-periods", type=int, default=10_000)
    autopilot_parser.add_argument("--out", default=None, help="Write the audit JSONL here.")
    autopilot_parser.add_argument(
        "--catalog",
        default=None,
        help="DuckDB catalog filename under --root for persistent trial provenance "
        "(honest cross-campaign trial counting). Omit to count in-memory only.",
    )
    autopilot_parser.add_argument(
        "--llm",
        action="store_true",
        help="Use a local Ollama narrator (falls back to rule-based if the server is absent).",
    )
    autopilot_parser.add_argument("--llm-model", default="llama3.1")
    autopilot_parser.set_defaults(func=_cmd_autopilot)

    desk_parser = subparsers.add_parser(
        "desk", help="Serve the Obsidian Desk web UI on 127.0.0.1 (localhost only)."
    )
    desk_parser.add_argument(
        "--audit", default=None, help="Path to an audit JSONL log to render (optional)."
    )
    desk_parser.add_argument("--symbol", default="BTC-USDT")
    desk_parser.add_argument(
        "--kill-switch", default=None, help="Path to the persistent kill-switch file."
    )
    desk_parser.add_argument("--port", type=int, default=8137)
    desk_parser.set_defaults(func=_cmd_desk)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Read-only health check: lockout, config, audit, kill switch, catalog, "
        "license gate.",
    )
    doctor_parser.add_argument(
        "--audit", default=None, help="Optional audit JSONL log to hash-chain verify."
    )
    doctor_parser.add_argument(
        "--kill-switch", default=None, help="Optional persistent kill-switch file to inspect."
    )
    doctor_parser.add_argument("--symbol", default="BTC-USDT")
    doctor_parser.add_argument(
        "--no-license", action="store_true", help="Skip the (slower) license-gate subprocess."
    )
    doctor_parser.set_defaults(func=_cmd_doctor)

    backup_parser = subparsers.add_parser(
        "backup", help="Snapshot data/, runs/, and catalog.duckdb into a timestamped zip."
    )
    backup_parser.add_argument("--root", default=".", help="Working root to back up (default: .)")
    backup_parser.add_argument(
        "--dest", default=None, help="Backup directory (default: <root>/backups)"
    )
    backup_parser.set_defaults(func=_cmd_backup)

    return parser


def _cmd_doctor(args: argparse.Namespace) -> int:
    from lqe.ops.health import format_report, run_health_checks, worst_status

    checks = run_health_checks(
        audit_path=Path(args.audit) if args.audit else None,
        kill_switch_path=Path(args.kill_switch) if args.kill_switch else None,
        symbol=args.symbol,
        run_license_gate=not args.no_license,
    )
    print("lqe doctor - local paper-only quant engine")
    print(format_report(checks))
    status = worst_status(checks)
    print(f"\noverall: {status}")
    # A FAIL is a broken invariant (exit 1). A WARN (e.g. no audit log supplied,
    # kill switch active) is informational and still exits 0.
    return 1 if status == "FAIL" else 0


def _cmd_backup(args: argparse.Namespace) -> int:
    from lqe.ops.backup import create_backup

    result = create_backup(
        Path(args.root), dest_dir=Path(args.dest) if args.dest else None
    )
    included = ", ".join(result.included) if result.included else "(nothing found to back up)"
    print(f"backup -> {result.archive}")
    print(f"  included: {included}")
    if result.skipped:
        print(f"  skipped (absent): {', '.join(result.skipped)}")
    print(f"  {result.files} files, {result.bytes_total:,} bytes")
    return 0


def _cmd_catalog(args: argparse.Namespace) -> int:
    from collections import Counter

    from lqe.models.catalog_scale import build_scaled_catalog

    catalog, results = build_scaled_catalog(args.symbol)
    admitted = catalog.all()
    quarantined = catalog.quarantined()
    by_family = Counter(e.manifest.family for e in admitted)
    print(f"scaled catalog: {len(results)} models registered for {args.symbol}")
    print(f"  admitted (constructible now): {len(admitted)}")
    for family, count in sorted(by_family.items()):
        print(f"    {family}: {count}")
    print(f"  quarantined (transparent, e.g. optional 'models' extra absent): {len(quarantined)}")
    for record in quarantined:
        print(f"    {record.model_id}: {record.reasons[0]}")
    print("  every admitted model is 'unproven' until a gate PASS promotes it.")
    return 0


def _cmd_check_config(args: argparse.Namespace) -> int:
    from lqe.core.config import load_config
    from lqe.core.errors import ConfigError, LockoutViolation

    try:
        config = load_config(args.path)
    except LockoutViolation as exc:
        print(f"LOCKOUT: {exc}")
        return 2
    except ConfigError as exc:
        print(f"invalid config: {exc}")
        return 1
    print(
        f"config OK — mode={config.engine.mode}, execution.adapter={config.execution.adapter}, "
        f"data.adapter={config.data.adapter} (paper-only lockout satisfied)"
    )
    return 0


def _cmd_autopilot(args: argparse.Namespace) -> int:
    # Imported lazily: the autonomy loop needs the optional `search` extra
    # (Optuna). Base/non-autopilot commands must import without it.
    from lqe.autonomy.narrator import make_narrator
    from lqe.autonomy.optimizer import OptunaOptimizer
    from lqe.autonomy.orchestrator import Orchestrator
    from lqe.autonomy.promotion_gate import GateThresholds
    from lqe.autonomy.searchable import default_searchable_models

    root = Path(args.root)
    bundle, bars = load_bundle(root, args.bundle)
    symbol_bars = [bar for bar in bars if bar.symbol == args.symbol]
    if not symbol_bars:
        print(f"no bars for symbol {args.symbol!r} in bundle {args.bundle!r}")
        return 1

    # A run_id that is stable per (bundle, seed, steps) campaign: re-running
    # the identical campaign REPLACEs its trials (no double-count), while a
    # different seed/bundle/steps accumulates honestly (docs/03 §3.6).
    run_id = f"autopilot:{args.bundle}:{args.symbol}:seed{args.seed}:steps{args.steps}"
    catalog_cm = Catalog(root / args.catalog) if args.catalog else None
    registry = ExperimentRegistry(catalog_cm) if catalog_cm is not None else None

    try:
        orchestrator = Orchestrator(
            validator=Validator(),
            gate=PromotionGate(thresholds=GateThresholds(min_periods=args.min_periods)),
            optimizer=OptunaOptimizer(),
            searchable_models=default_searchable_models(),
            bars=symbol_bars,
            symbol=args.symbol,
            starting_cash=Decimal(str(args.starting_cash)),
            run_id=run_id,
            seed=args.seed,
            n_trials=args.trials,
            registry=registry,
            narrator=make_narrator(use_llm=args.llm, model=args.llm_model, seed=args.seed),
        )
        states = orchestrator.run(steps=args.steps, start=symbol_bars[-1].ts_open)

        promoted = sum(1 for s in states if s.promoted)
        tracked_count = len(orchestrator.tracked_book.entries())
        print(f"autopilot: {args.steps} steps over {len(symbol_bars)} bars ({args.symbol})")
        for s in states:
            tag = " -> promoted" if s.promoted else ""
            print(f"  step {s.step_index} {s.focus_model}: {s.verdict}{tag}")
        print(f"promoted {promoted}/{args.steps}; tracked book has {tracked_count} models")
        if registry is not None:
            print(f"trials recorded (all campaigns): {registry.trial_count()}")
        print(f"audit hash-chain verifies: {orchestrator.engine.audit.verify()}")
        if args.out:
            out = Path(args.out)
            orchestrator.engine.audit.write_jsonl(out)
            print(f"wrote audit log -> {out}")
    finally:
        if catalog_cm is not None:
            catalog_cm.close()
    return 0


def _cmd_desk(args: argparse.Namespace) -> int:
    # Imported lazily so `lqe ingest/backtest/validate` work without the
    # optional `ui` extra installed (fastapi/uvicorn/jinja2). The CLI (not
    # `ui/`) owns the risk/kill-switch import and builds the ControlPlane.
    from lqe.live.control import ControlPlane
    from lqe.risk.kill_switch import KillSwitch
    from lqe.ui.app import BIND_HOST, serve
    from lqe.ui.builder import build_desk_data

    kill_switch = KillSwitch(Path(args.kill_switch)) if args.kill_switch else KillSwitch.in_memory()
    data = build_desk_data(
        control=ControlPlane(kill_switch=kill_switch),
        audit_path=Path(args.audit) if args.audit else None,
        symbol=args.symbol,
    )
    print(f"Obsidian Desk on http://{BIND_HOST}:{args.port} (paper-only, localhost)")
    serve(data, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
    except LqeError as exc:
        # Expected, typed failures (missing bundle, bad config, reconciliation
        # halt, ...) print a clean line + non-zero exit instead of a traceback.
        print(f"error: {exc}")
        return 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
