"""`PyPortfolioOptAdapter` (docs/03 §3.3, family: portfolio). `PyPortfolioOpt`
(MIT) is kept in the optional `models` extra, not the base runtime —
imported lazily so a base install never needs it. See
`_portfolio_projection.py` for why this is a one-shot static weight
projection rather than a rebalancing multi-instrument book.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from lqe.core.types import Symbol
from lqe.models.adapters._portfolio_projection import StaticWeightProjectionAdapter


class PyPortfolioOptAdapter(StaticWeightProjectionAdapter):
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
            from pypfopt import EfficientFrontier, expected_returns, risk_models
        except ImportError as exc:
            raise ImportError(
                "PyPortfolioOptAdapter requires the optional 'models' extra: "
                "pip install '.[models]'"
            ) from exc

        def weight_fn(universe: Mapping[Symbol, Sequence[float]]) -> Mapping[Symbol, float]:
            prices = pd.DataFrame({sym: list(closes) for sym, closes in universe.items()})
            mu = expected_returns.mean_historical_return(prices)
            cov = risk_models.sample_cov(prices)
            ef = EfficientFrontier(mu, cov)
            ef.max_sharpe()
            weights: Mapping[Symbol, float] = dict(ef.clean_weights())
            return weights

        super().__init__(
            symbol=symbol, name=name, universe_closes=universe_closes, weight_fn=weight_fn,
            min_weight=min_weight, params={"min_weight": min_weight},
        )
