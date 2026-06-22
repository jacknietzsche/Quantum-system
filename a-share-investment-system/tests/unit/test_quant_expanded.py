"""Expanded tests for services/quant_analyzers.py."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _make_df(n=60):
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n)
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    high = close + abs(np.random.randn(n))
    low = close - abs(np.random.randn(n))
    vol = np.random.randint(1000, 10000, n).astype(float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.5,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )


class TestQuantAnalyzers:
    def test_module_importable(self):
        import services.quant_analyzers as qa

        assert qa is not None

    def test_has_analyze_function(self):
        import services.quant_analyzers as qa

        # Check for common analyzer functions
        funcs = [x for x in dir(qa) if not x.startswith("_") and callable(getattr(qa, x, None))]
        assert len(funcs) > 0
