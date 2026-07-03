"""`broad_searchable_models` (post-v1.0 extension): one SearchableModel per
native indicator preset (9) plus the reference trend_ma_cross (10 total),
each of which must actually build a working `Strategy`.
"""

from __future__ import annotations

from lqe.autonomy.searchable_scaled import broad_searchable_models


def test_ten_models_spanning_all_four_native_families() -> None:
    models = broad_searchable_models()
    assert len(models) == 10
    assert {m.model_id for m in models} == {
        "macd_trend", "donchian_breakout", "adx_trend", "tsmom", "roc_momentum",
        "zscore_reversion", "bollinger_fade", "rsi_fade", "vol_breakout", "trend_ma_cross",
    }
    assert {m.family for m in models} == {"trend", "momentum", "mean_reversion", "volatility"}


def test_every_model_builds_a_working_strategy_at_its_range_midpoint() -> None:
    for model in broad_searchable_models():
        params = {k: (r.low + r.high) / 2 for k, r in model.space.ranges.items()}
        strategy = model.build("BTC-USDT", params)
        assert strategy.name == model.model_id
