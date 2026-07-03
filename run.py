#!/usr/bin/env python3
"""One-command local launcher for the Obsidian Desk (docs/10 M12).

    python run.py                 # serve the desk, open your browser
    python run.py --window        # open a native desktop window (needs pywebview)
    python run.py --audit runs/audit.jsonl --kill-switch runs/kill.json

This is a thin convenience wrapper over `lqe desk`; both bind **127.0.0.1
only** — the app has no auth because it is never reachable off the loopback
interface, and it can place no real order (paper-only lockout, non-negotiable
#1). The desktop window is optional and imported lazily: without `pywebview`
installed it degrades to a printed localhost URL rather than failing.
"""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path


def _build_data(audit: str | None, kill_switch: str | None, symbol: str):  # type: ignore[no-untyped-def]
    from lqe.live.control import ControlPlane
    from lqe.risk.kill_switch import KillSwitch
    from lqe.ui.builder import build_desk_data

    ks = KillSwitch(Path(kill_switch)) if kill_switch else KillSwitch.in_memory()
    return build_desk_data(
        control=ControlPlane(kill_switch=ks),
        audit_path=Path(audit) if audit else None,
        symbol=symbol,
    )


def _serve_in_thread(data, port: int) -> threading.Thread:  # type: ignore[no-untyped-def]
    from lqe.ui.app import serve

    thread = threading.Thread(target=lambda: serve(data, port=port), daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the local Obsidian Desk (paper-only).")
    parser.add_argument("--audit", default=None, help="Audit JSONL log to render (optional).")
    parser.add_argument("--kill-switch", default=None, help="Persistent kill-switch file path.")
    parser.add_argument("--symbol", default="BTC-USDT")
    parser.add_argument("--port", type=int, default=8137)
    parser.add_argument("--window", action="store_true", help="Native desktop window (pywebview).")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser tab.")
    args = parser.parse_args(argv)

    from lqe.ui.app import BIND_HOST  # 127.0.0.1, hard-coded

    url = f"http://{BIND_HOST}:{args.port}"
    data = _build_data(args.audit, args.kill_switch, args.symbol)

    if args.window:
        try:
            import webview  # type: ignore[import-not-found]  # pywebview — optional dep
        except ImportError:
            print("pywebview not installed; falling back to a browser tab.")
            print("  install it with:  pip install pywebview")
        else:
            _serve_in_thread(data, args.port)
            print(f"Obsidian Desk (desktop window) -> {url}  (paper-only, localhost)")
            webview.create_window("lightweight-quant-engine", url)
            webview.start()
            return 0

    print(f"Obsidian Desk -> {url}  (paper-only, localhost)")
    if not args.no_browser:
        _serve_in_thread(data, args.port)
        webbrowser.open(url)
        print("serving... press Ctrl+C to stop.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            print("\nstopped.")
        return 0

    # Blocking serve, no browser.
    from lqe.ui.app import serve

    serve(data, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
