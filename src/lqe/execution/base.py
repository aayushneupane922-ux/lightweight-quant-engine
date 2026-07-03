"""The `ExecutionAdapter` protocol (docs/11 §11.2, docs/archive/10 §10.15).

`is_paper` is the MVP invariant: it must be `True`, and every session
startup asserts it (`core/config.assert_paper_only`) rather than trusting
the type system alone. `PaperBroker` is the only adapter that's actually
constructible for use; `execution/_locked_out.py` exists only to give a
future real adapter one obviously-guarded starting point.
"""

from __future__ import annotations

from typing import Protocol

from lqe.core.events import Order


class ExecutionAdapter(Protocol):
    is_paper: bool

    def submit(self, order: Order) -> None: ...

    def cancel(self, order_id: str) -> None: ...

    def working_orders(self) -> list[Order]: ...
