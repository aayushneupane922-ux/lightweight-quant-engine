"""The control plane (docs/11 §11.9): the ONLY write path the UI is
allowed. The UI never constructs an `Order`, never imports risk/execution
internals, and never flips a flag directly — it calls `ControlPlane`, which
emits an audited `ControlEvent` and, for `KILL`, flips the persistent,
human-owned kill switch the risk model reads.

Two hard invariants (GUARDRAILS.md):
- The whitelisted command set is exactly the seven in `ControlEvent`
  (START/STOP/KILL/FREEZE/FLATTEN/AUTOPILOT_ON/AUTOPILOT_OFF). Nothing here
  can place or size an order.
- `KILL` is un-overridable by software. `clear_kill` is a *separate*
  method that requires a named human operator (the `KillSwitch` itself
  raises if none is given); it is deliberately NOT reachable through the
  generic `submit()` command path, so no automated caller can clear a kill
  by sending a command.
"""

from __future__ import annotations

from typing import Literal

from lqe.core.events import ControlEvent
from lqe.risk.kill_switch import KillSwitch

Command = Literal["START", "STOP", "KILL", "FREEZE", "FLATTEN", "AUTOPILOT_ON", "AUTOPILOT_OFF"]

_WHITELIST: frozenset[str] = frozenset(
    ["START", "STOP", "KILL", "FREEZE", "FLATTEN", "AUTOPILOT_ON", "AUTOPILOT_OFF"]
)


class ControlPlane:
    def __init__(self, *, kill_switch: KillSwitch | None = None) -> None:
        self._kill_switch = kill_switch or KillSwitch.in_memory()
        self._log: list[ControlEvent] = []
        self._autopilot_on = False

    @property
    def kill_active(self) -> bool:
        return self._kill_switch.active

    @property
    def kill_reason(self) -> str:
        return self._kill_switch.reason

    @property
    def autopilot_on(self) -> bool:
        """Whether autonomous management is engaged. Flipping this OFF is the
        UI's "take the wheel" (docs/02 §2.3); it never overrides the kill
        switch, which halts autonomy regardless of this flag."""
        return self._autopilot_on and not self._kill_switch.active

    def submit(
        self, command: Command, *, source: str, operator: str, note: str = ""
    ) -> ControlEvent:
        """Apply a whitelisted control command and audit it. Unknown
        commands are refused (fail closed) rather than logged-and-ignored,
        so a typo can never silently do nothing."""
        if command not in _WHITELIST:
            raise ValueError(f"{command!r} is not a whitelisted control command")

        if command == "KILL":
            self._kill_switch.trigger(reason=note or f"manual KILL by {operator or source}")
        elif command == "AUTOPILOT_ON":
            self._autopilot_on = True
        elif command in ("AUTOPILOT_OFF", "STOP", "FREEZE"):
            self._autopilot_on = False  # take-the-wheel / halt disengages autonomy

        event = ControlEvent(command=command, source=source, operator=operator, note=note)
        self._log.append(event)
        return event

    def clear_kill(self, *, operator: str, source: str = "ui") -> ControlEvent:
        """Human-only kill reset. Requires a named operator (the switch
        raises otherwise). Not reachable via `submit()` by design."""
        self._kill_switch.clear(operator=operator)  # raises ValueError if operator is falsy
        event = ControlEvent(
            command="START", source=source, operator=operator, note=f"kill cleared by {operator}"
        )
        self._log.append(event)
        return event

    def log(self) -> list[ControlEvent]:
        return list(self._log)
