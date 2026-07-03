"""`RiskfolioAdapter` (docs/03 §3.3, family: risk_allocation). `riskfolio-lib`
(BSD-3) is kept in the optional `models` extra, not the base runtime —
imported lazily so a base install never needs it. See
`_portfolio_projection.py` for why this is a one-shot static weight
projection rather than a rebalancing multi-instrument book.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from lqe.core.types import Symbol
from lqe.models.adapters._portfolio_projection import StaticWeightProjectionAdapter


class RiskfolioAdapter(StaticWeightProjectionAdapter):
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        universe_closes: Mapping[Symbol, Sequence[float]],
        min_weight: float = 0.01,
    ) -> None:
        try:
            import pandas as pd
            import riskfolio as rp
        except ImportError as exc:
            raise ImportError(
                "RiskfolioAdapter requires the optional 'models' extra: pip install '.[models]'"
            ) from exc

        def weight_fn(universe: Mapping[Symbol, Sequence[float]]) -> Mapping[Symbol, float]:
            prices = pd.DataFrame({sym: list(closes) for sym, closes in universe.items()})
            returns = prices.pct_change().dropna()
            port = rp.Portfolio(returns=returns)
            port.assets_stats(method_mu="hist", method_cov="hist")
            allocation = port.rp_optimization(model="Classic", rm="MV", rf=0, b=None)
            weights: Mapping[Symbol, float] = dict(allocation["weights"])
            return weights

        super().__init__(
            symbol=symbol, name=name, universe_closes=universe_closes, weight_fn=weight_fn,
            min_weight=min_weight, params={"min_weight": min_weight},
        )
