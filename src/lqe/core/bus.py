"""A minimal synchronous, ordered event bus.

Single-threaded, seq-ordered dispatch: handlers run in registration order,
in the same call stack as `publish` — no background threads, no queues that
could reorder events. That ordering guarantee is what keeps the engine loop
deterministic.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from lqe.core.events import EventEnvelope

Handler = Callable[[EventEnvelope], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, envelope: EventEnvelope) -> None:
        for handler in self._handlers.get(envelope.type, ()):
            handler(envelope)
