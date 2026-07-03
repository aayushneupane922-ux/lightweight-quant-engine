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
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lqe.live.control import Command
from lqe.ui.data import DeskData

# Hard invariant (GUARDRAILS.md, docs/11 §11.11): localhost only. There is
# no config knob to change this — binding anywhere else would expose an
# un-authed control surface.
BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8137

_HERE = Path(__file__).resolve().parent
_TEMPLATES = _HERE / "templates"
_THEME = _HERE / "theme"

_VALID_COMMANDS: frozenset[str] = frozenset(
    ["START", "STOP", "KILL", "FREEZE", "FLATTEN", "AUTOPILOT_ON", "AUTOPILOT_OFF"]
)

_NAV = [
    ("floor", "Floor", "F1", "/"),
    ("catalog", "Catalog", "F2", "/catalog"),
    ("research", "Research", "F3", "/research"),
    ("risk", "Risk", "F5", "/risk"),
    ("daily", "Daily", "F6", "/daily"),
]


def create_app(data: DeskData) -> FastAPI:
    app = FastAPI(title="Obsidian Desk", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(_TEMPLATES))
    app.mount("/theme", StaticFiles(directory=str(_THEME)), name="theme")

    def _ctx(request: Request, active: str, **extra: Any) -> dict[str, Any]:
        return {
            "request": request,
            "nav": _NAV,
            "active": active,
            "snapshot": data.snapshot(),
            "kill_active": data.kill_active,
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

    @app.get("/risk", response_class=HTMLResponse)
    def risk(request: Request) -> Any:
        return templates.TemplateResponse(request, "risk.html", _ctx(request, "risk"))

    @app.get("/daily", response_class=HTMLResponse)
    def daily(request: Request) -> Any:
        return templates.TemplateResponse(
            request, "daily.html", _ctx(request, "daily", rows=data.daily())
        )

    # --- read-only JSON (UI polling / tests) -----------------------------

    @app.get("/api/snapshot")
    def api_snapshot() -> JSONResponse:
        return JSONResponse(data.snapshot().model_dump(mode="json"))

    @app.get("/api/tape")
    def api_tape(after_seq: int = 0) -> JSONResponse:
        rows = [r.model_dump(mode="json") for r in data.tape(after_seq=after_seq)]
        return JSONResponse(rows)

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

    # --- live push -------------------------------------------------------

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            payload = {
                "snapshot": data.snapshot().model_dump(mode="json"),
                "tape": [r.model_dump(mode="json") for r in data.tape(limit=60)],
            }
            await websocket.send_text(json.dumps(payload, default=str))
            # Read-only stream: the client may ping for a refresh; we never
            # accept a mutating message here (writes go through /api/control).
            while True:
                await websocket.receive_text()
                refreshed = {
                    "snapshot": data.snapshot().model_dump(mode="json"),
                    "tape": [r.model_dump(mode="json") for r in data.tape(limit=60)],
                }
                await websocket.send_text(json.dumps(refreshed, default=str))
        except WebSocketDisconnect:
            return

    return app


def serve(data: DeskData, *, port: int = DEFAULT_PORT) -> None:  # pragma: no cover - real server
    """Blocking run on 127.0.0.1 only. Imported lazily so a base install
    without the `ui` extra can still import the rest of `lqe`."""
    import uvicorn

    uvicorn.run(create_app(data), host=BIND_HOST, port=port, log_level="warning")


__all__ = ["BIND_HOST", "DEFAULT_PORT", "Command", "create_app", "serve"]
