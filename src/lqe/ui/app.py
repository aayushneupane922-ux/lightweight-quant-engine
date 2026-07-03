"""The Obsidian Desk web app (docs/05, docs/11 §11.9): FastAPI + Jinja2 on
`127.0.0.1` only, no auth (unreachable), no CLI/stdout — every log line a
console would print is a designed component instead (phase strips, tables,
KPIs, a structured Tape of one row per audit event).

Read path: `DeskData.snapshot()`/`tape()` (a read-only `StateReader`).
Write path: `DeskData.submit_control()` (the whitelisted `ControlPlane`,
the *only* mutating call the UI can make). This module imports no `risk`,
`execution`, `autonomy`, or `models` internals, and constructs no `Order` —
enforced by the safety tests (docs/11 §11.12).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lqe.live.control import Command
from lqe.ui.data import DeskData

if TYPE_CHECKING:
    # docs/13 M18: only used for the type hint below -- see ui/data.py's
    # identical note on why importing `lqe.ops.jobs` here doesn't cross the
    # ui-boundary safety test (it isn't risk/execution/autonomy/models).
    from lqe.ops.jobs import LaunchState

# Hard invariant (GUARDRAILS.md, docs/11 §11.11): localhost only. There is
# no config knob to change this — binding anywhere else would expose an
# un-authed control surface.
BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8137

_HERE = Path(__file__).resolve().parent
_TEMPLATES = _HERE / "templates"
_THEME = _HERE / "theme"
# The viz3d package (sibling of ui) holds the neural-web scene assets; the
# app mounts them as static — a read-only file mount, not a code import, so
# the ui-imports-no-viz3d boundary is preserved.
_VIZ3D = _HERE.parent / "viz3d"

_VALID_COMMANDS: frozenset[str] = frozenset(
    ["START", "STOP", "KILL", "FREEZE", "FLATTEN", "AUTOPILOT_ON", "AUTOPILOT_OFF"]
)

_NAV = [
    ("floor", "Floor", "F1", "/"),
    ("catalog", "Catalog", "F2", "/catalog"),
    ("research", "Research", "F3", "/research"),
    ("intel", "Intel", "F4", "/intel"),
    ("engine", "Engine", "F7", "/engine"),
    ("risk", "Risk", "F5", "/risk"),
    ("daily", "Daily", "F6", "/daily"),
    ("blotter", "Blotter", "F8", "/blotter"),
]


def _primary_symbol(data: DeskData) -> str | None:
    health = data.snapshot().data_health
    return health[0].symbol if health else None


def create_app(data: DeskData, *, launch_state: LaunchState | None = None) -> FastAPI:
    app = FastAPI(title="Obsidian Desk", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(_TEMPLATES))
    app.mount("/theme", StaticFiles(directory=str(_THEME)), name="theme")
    app.mount("/viz3d", StaticFiles(directory=str(_VIZ3D)), name="viz3d")

    # docs/13 M18: while first-run setup (auto-ingest, doctor checks) is
    # still in progress, every page request gets the onboarding screen
    # instead -- a plain-language status page, never raw stdout, never a
    # stack trace. `/api/launch-status` is exempt so the onboarding page's
    # own poll can ask "are we ready yet?"; static theme/viz3d assets are
    # exempt so the onboarding page itself can render styled.
    _EXEMPT_PREFIXES = ("/api/launch-status", "/theme", "/viz3d")

    @app.middleware("http")
    async def _onboarding_gate(request: Request, call_next):  # type: ignore[no-untyped-def]
        blocked = launch_state is not None and not launch_state.ready
        if blocked and not request.url.path.startswith(_EXEMPT_PREFIXES):
            assert launch_state is not None  # narrowed by `blocked` above, for mypy
            return templates.TemplateResponse(
                request, "onboarding.html",
                {"request": request, "message": launch_state.message},
            )
        return await call_next(request)

    @app.get("/api/launch-status")
    def api_launch_status() -> JSONResponse:
        if launch_state is None:
            return JSONResponse({"ready": True, "message": "ready"})
        return JSONResponse({"ready": launch_state.ready, "message": launch_state.message})

    def _ctx(request: Request, active: str, **extra: Any) -> dict[str, Any]:
        return {
            "request": request,
            "nav": _NAV,
            "active": active,
            "snapshot": data.snapshot(),
            "kill_active": data.kill_active,
            "autopilot_on": data.autopilot_on,
            "jobs_enabled": data.jobs is not None,
            **extra,
        }

    @app.get("/", response_class=HTMLResponse)
    def floor(request: Request) -> Any:
        snap = data.snapshot()
        return templates.TemplateResponse(
            request, "floor.html", _ctx(request, "floor", tape=data.tape(limit=60), snapshot=snap)
        )

    @app.get("/catalog", response_class=HTMLResponse)
    def catalog(request: Request) -> Any:
        return templates.TemplateResponse(
            request, "catalog.html", _ctx(request, "catalog", rows=data.catalog())
        )

    @app.get("/research", response_class=HTMLResponse)
    def research(request: Request) -> Any:
        return templates.TemplateResponse(
            request, "research.html", _ctx(request, "research", rows=data.experiments())
        )

    @app.get("/intel", response_class=HTMLResponse)
    def intel(request: Request) -> Any:
        return templates.TemplateResponse(
            request, "intel.html",
            _ctx(
                request, "intel", cards=data.decision_cards(),
                conversation=data.conversation(),
            ),
        )

    @app.get("/engine", response_class=HTMLResponse)
    def engine(request: Request) -> Any:
        return templates.TemplateResponse(request, "engine.html", _ctx(request, "engine"))

    @app.get("/risk", response_class=HTMLResponse)
    def risk(request: Request) -> Any:
        return templates.TemplateResponse(request, "risk.html", _ctx(request, "risk"))

    @app.get("/daily", response_class=HTMLResponse)
    def daily(request: Request) -> Any:
        return templates.TemplateResponse(
            request, "daily.html", _ctx(request, "daily", rows=data.daily())
        )

    @app.get("/blotter", response_class=HTMLResponse)
    def blotter(request: Request) -> Any:
        rows = data.blotter()
        return templates.TemplateResponse(
            request, "blotter.html",
            _ctx(
                request, "blotter", rows=rows,
                empty_reason=data.blotter_empty_state(),
                reconciliation=data.reconciliation(),
            ),
        )

    # --- read-only JSON (UI polling / tests) -----------------------------

    @app.get("/api/snapshot")
    def api_snapshot() -> JSONResponse:
        return JSONResponse(data.snapshot().model_dump(mode="json"))

    @app.get("/api/tape")
    def api_tape(after_seq: int = 0) -> JSONResponse:
        rows = [r.model_dump(mode="json") for r in data.tape(after_seq=after_seq)]
        return JSONResponse(rows)

    @app.get("/api/blotter")
    def api_blotter(after_seq: int = 0) -> JSONResponse:
        rows = [r.model_dump(mode="json") for r in data.blotter(after_seq=after_seq)]
        return JSONResponse(rows)

    @app.get("/api/graph")
    def api_graph(at_seq: int | None = None) -> JSONResponse:
        # read-only; `at_seq` replays the neural-web at a point in the session
        return JSONResponse(data.graph(at_seq=at_seq).model_dump(mode="json"))

    @app.get("/api/conversation")
    def api_conversation(at_seq: int | None = None) -> JSONResponse:
        # docs/13 M21: the "Engine Room" feed; `at_seq` replays it exactly
        # as it was at that point in the session (same pattern as /api/graph)
        return JSONResponse(data.conversation(at_seq=at_seq).model_dump(mode="json"))

    # docs/13 M19: the Floor hero chart's data — read-only, same
    # `StateReader` the rest of the desk already reads from. `symbol`
    # defaults to whichever feed the snapshot's `data_health` names first
    # (there's normally exactly one feed per session).

    @app.get("/api/chart/price")
    def api_chart_price(symbol: str | None = None, max_points: int = 1000) -> JSONResponse:
        sym = symbol or _primary_symbol(data)
        if sym is None:
            return JSONResponse([])
        return JSONResponse(
            [b.model_dump(mode="json") for b in data.price_series(sym, max_points=max_points)]
        )

    @app.get("/api/chart/equity")
    def api_chart_equity(max_points: int = 1000) -> JSONResponse:
        return JSONResponse(
            [p.model_dump(mode="json") for p in data.equity_curve(max_points=max_points)]
        )

    # --- the single write path -------------------------------------------

    @app.post("/api/control")
    async def api_control(request: Request) -> JSONResponse:
        body = await request.json()
        command = str(body.get("command", ""))
        operator = str(body.get("operator", "") or "desk-operator")
        note = str(body.get("note", ""))
        if command == "CLEAR_KILL":
            data.clear_kill(operator=operator)
        elif command in _VALID_COMMANDS:
            data.submit_control(
                command,  # type: ignore[arg-type]  # membership-checked against the whitelist above
                source="ui",
                operator=operator,
                note=note,
            )
        else:
            return JSONResponse({"error": f"unknown command {command!r}"}, status_code=400)
        return JSONResponse({"kill_active": data.kill_active})

    # --- GUI job triggers (docs/13 M18) -----------------------------------
    # A second, separate write surface from /api/control above: these
    # trigger long-running operations (ingest/backtest/live start-stop) in
    # a background thread via `JobManager` rather than flipping a control
    # flag. Every op it calls is the same already-tested function the CLI
    # uses (data.ingest.ingest, backtest.runner.run_backtest,
    # live.session.LiveSession) -- no new Order-construction path. All
    # return 404 if the caller (e.g. `lqe desk`'s read-only render path)
    # never enabled jobs.

    @app.get("/api/jobs")
    def api_jobs() -> JSONResponse:
        if data.jobs is None:
            return JSONResponse({"error": "jobs not enabled on this session"}, status_code=404)
        return JSONResponse(
            [
                {
                    "name": s.name, "state": s.state, "message": s.message,
                    "updated_at": s.updated_at.isoformat(),
                }
                for s in data.jobs.statuses()
            ]
        )

    @app.post("/api/jobs/ingest")
    async def api_jobs_ingest(request: Request) -> JSONResponse:
        if data.jobs is None:
            return JSONResponse({"error": "jobs not enabled on this session"}, status_code=404)
        body = await request.json()
        started = data.jobs.start_ingest(
            adapter=str(body.get("adapter", "ccxt")),
            exchange=str(body.get("exchange", "binance")),
            symbol=str(body.get("symbol", "BTC-USDT")),
            timeframe=str(body.get("timeframe", "1m")),  # type: ignore[arg-type]
            # ^ raw JSON body input; JobManager wraps the whole job in
            # try/except, so an invalid value surfaces as a job "error"
            # status, not a crash -- no need to hand-validate against the
            # Literal here.
            root=str(body.get("root", "data")),
            csv_path=body.get("csv_path"),
        )
        return JSONResponse({"started": started})

    @app.post("/api/jobs/backtest")
    async def api_jobs_backtest(request: Request) -> JSONResponse:
        if data.jobs is None:
            return JSONResponse({"error": "jobs not enabled on this session"}, status_code=404)
        body = await request.json()
        started = data.jobs.start_backtest(
            root=str(body.get("root", "data")),
            bundle=str(body.get("bundle", "")),
            symbol=str(body.get("symbol", "BTC-USDT")),
            fast=int(body.get("fast", 12)),
            slow=int(body.get("slow", 48)),
            starting_cash=float(body.get("starting_cash", 10_000.0)),
        )
        return JSONResponse({"started": started})

    @app.post("/api/jobs/live/start")
    async def api_jobs_live_start(request: Request) -> JSONResponse:
        if data.jobs is None:
            return JSONResponse({"error": "jobs not enabled on this session"}, status_code=404)
        body = await request.json()
        started = data.jobs.start_live(
            adapter=str(body.get("adapter", "ccxt")),
            exchange=str(body.get("exchange", "binance")),
            csv_path=body.get("csv_path"),
            symbol=str(body.get("symbol", "BTC-USDT")),
            timeframe=str(body.get("timeframe", "1m")),  # type: ignore[arg-type]
            poll_seconds=float(body.get("poll_seconds", 60.0)),
            lookback_bars=int(body.get("lookback_bars", 300)),
            starting_cash=float(body.get("starting_cash", 10_000.0)),
            autonomy_every=int(body.get("autonomy_every", 5)),
            n_trials=int(body.get("n_trials", 8)),
            min_periods=int(body.get("min_periods", 200)),
            use_llm=bool(body.get("use_llm", False)),
            llm_model=str(body.get("llm_model", "llama3.2:3b")),
            out_path=body.get("out_path"),
        )
        return JSONResponse({"started": started})

    @app.post("/api/jobs/live/stop")
    def api_jobs_live_stop() -> JSONResponse:
        if data.jobs is None:
            return JSONResponse({"error": "jobs not enabled on this session"}, status_code=404)
        return JSONResponse({"stopped": data.jobs.stop_live()})

    # --- live push -------------------------------------------------------

    def _ws_frame() -> dict[str, Any]:
        # docs/13 M20: blotter rows ride the same live push as snapshot/tape
        # so a new fill reaches the client without a separate poll loop.
        return {
            "snapshot": data.snapshot().model_dump(mode="json"),
            "tape": [r.model_dump(mode="json") for r in data.tape(limit=60)],
            "blotter": [r.model_dump(mode="json") for r in data.blotter(limit=60)],
        }

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            await websocket.send_text(json.dumps(_ws_frame(), default=str))
            # Read-only stream: the client may ping for a refresh; we never
            # accept a mutating message here (writes go through /api/control).
            while True:
                await websocket.receive_text()
                await websocket.send_text(json.dumps(_ws_frame(), default=str))
        except WebSocketDisconnect:
            return

    return app


def serve(
    data: DeskData, *, port: int = DEFAULT_PORT, launch_state: LaunchState | None = None
) -> None:  # pragma: no cover - real server
    """Blocking run on 127.0.0.1 only. Imported lazily so a base install
    without the `ui` extra can still import the rest of `lqe`."""
    import uvicorn

    uvicorn.run(
        create_app(data, launch_state=launch_state), host=BIND_HOST, port=port,
        log_level="warning",
    )


__all__ = ["BIND_HOST", "DEFAULT_PORT", "Command", "create_app", "serve"]
