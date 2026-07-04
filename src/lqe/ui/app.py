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

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

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

# V5 M26: retires the ad-hoc Unicode glyphs the spine nav used to show
# (▦, ▤, ◇, …) for vendored Lucide icons -- inner shape markup only (no
# outer <svg> wrapper), source-of-truth copies in theme/vendor/lucide/.
_NAV_ICONS: dict[str, str] = {
    "floor": (
        '<rect width="7" height="7" x="3" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="14" rx="1"/>'
        '<rect width="7" height="7" x="3" y="14" rx="1"/>'
    ),
    "catalog": (
        '<path d="M3 5h.01"/><path d="M3 12h.01"/><path d="M3 19h.01"/>'
        '<path d="M8 5h13"/><path d="M8 12h13"/><path d="M8 19h13"/>'
    ),
    "research": (
        '<path d="M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96'
        'l5.51-10.08A2 2 0 0 0 10 8V2"/>'
        '<path d="M6.453 15h11.094"/><path d="M8.5 2h7"/>'
    ),
    "intel": (
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051'
        'a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0'
        'l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 '
        '1.594-1.594z"/>'
        '<path d="M20 2v4"/><path d="M22 4h-4"/><circle cx="4" cy="20" r="2"/>'
    ),
    "engine": (
        '<rect x="16" y="16" width="6" height="6" rx="1"/>'
        '<rect x="2" y="16" width="6" height="6" rx="1"/>'
        '<rect x="9" y="2" width="6" height="6" rx="1"/>'
        '<path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/>'
        '<path d="M12 12V8"/>'
    ),
    "risk": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 '
        '1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
        '<path d="M12 8v4"/><path d="M12 16h.01"/>'
    ),
    "daily": (
        '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/>'
        '<path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/>'
        '<path d="M8 18h.01"/><path d="M12 18h.01"/><path d="M16 18h.01"/>'
    ),
    "blotter": (
        '<path d="M12 17V7"/><path d="M16 8h-6a2 2 0 0 0 0 4h4a2 2 0 0 1 0 4H8"/>'
        '<path d="M4 3a1 1 0 0 1 1-1 1.3 1.3 0 0 1 .7.2l.933.6a1.3 1.3 0 0 0 1.4 0l.934-.6a1.3 '
        '1.3 0 0 1 1.4 0l.933.6a1.3 1.3 0 0 0 1.4 0l.933-.6a1.3 1.3 0 0 1 1.4 0l.934.6a1.3 1.3 '
        '0 0 0 1.4 0l.933-.6A1.3 1.3 0 0 1 19 2a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1 1.3 1.3 0 0 1-.7'
        '-.2l-.933-.6a1.3 1.3 0 0 0-1.4 0l-.934.6a1.3 1.3 0 0 1-1.4 0l-.933-.6a1.3 1.3 0 0 0-1.4 '
        '0l-.933.6a1.3 1.3 0 0 1-1.4 0l-.934-.6a1.3 1.3 0 0 0-1.4 0l-.933.6a1.3 1.3 0 0 1-.7.2 '
        '1 1 0 0 1-1-1z"/>'
    ),
}


def _nav_icon(nav_id: str) -> Markup:
    inner = _NAV_ICONS.get(nav_id, "")
    return Markup(
        '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + inner + "</svg>"
    )


def _primary_symbol(data: DeskData) -> str | None:
    health = data.snapshot().data_health
    return health[0].symbol if health else None


def _spark_points(values: list[float]) -> str:
    """V5 M26 living cells: normalize a model cell's raw `sim_return_pct`
    samples into an SVG polyline `points` string over an 86x26 viewBox. A
    flat (or single-sample) series renders as a flat mid-height line rather
    than dividing by a zero range."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo
    n = len(values)
    step = 86.0 / (n - 1) if n > 1 else 0.0
    points = []
    for i, v in enumerate(values):
        x = i * step
        y = 13.0 if span == 0 else 26.0 - ((v - lo) / span) * 26.0
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def create_app(data: DeskData, *, launch_state: LaunchState | None = None) -> FastAPI:
    app = FastAPI(title="Obsidian Desk", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(_TEMPLATES))
    templates.env.globals["spark_points"] = _spark_points
    templates.env.globals["nav_icon"] = _nav_icon
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

    # docs/13 M20: blotter rows ride the same live push as snapshot/tape so
    # a new fill reaches the client without a separate poll loop. The frame
    # itself is built (and serialized) once per StateReader by DeskData --
    # every ping between live polls reuses the cached string (perf phase 4).

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            await websocket.send_text(data.ws_frame_text())
            # Read-only stream: the client may ping for a refresh; we never
            # accept a mutating message here (writes go through /api/control).
            while True:
                await websocket.receive_text()
                await websocket.send_text(data.ws_frame_text())
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
