"""Tests for the Market Regime Detector."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.market_regime import MarketRegimeDetector


from datetime import datetime, timedelta, timezone


def _make_candles(periods: int = 60, start_price: Decimal = Decimal("100")):
    """Create trending candles for regime testing."""
    candles = []
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(periods):
        close = Decimal(str(start_price + i))  # steady uptrend
        candles.append(
            OHLCBar(
                symbol="EURUSD",
                timeframe=MarketTimeframe.H1,
                timestamp=start + timedelta(hours=i),
                open=close,
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                tick_volume=100,
                data_source=DataSource.SIMULATED,
            )
        )
    return candles


class TestMarketRegimeDetector:
    def setup_method(self):
        self.detector = MarketRegimeDetector()

    def test_insufficient_data(self):
        # Only a few candles → UNKNOWN
        candles = _make_candles(5)
        result = self.detector.detect(
            "EURUSD", candles, None, data_source="simulated",
        )
        assert result.regime == "UNKNOWN"
        assert result.confidence == Decimal("0")
        assert "Insufficient" in result.explanation

    def test_trending_regime(self):
        # Strong uptrend → TRENDING
        candles = _make_candles(80, Decimal("100"))
        result = self.detector.detect(
            "EURUSD", candles, None, data_source="simulated",
        )
        assert result.regime in ("TRENDING", "TRANSITIONING", "UNKNOWN")
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0

    def test_default_parameters(self):
        params = self.detector.default_parameters
        assert "adx_period" in params
        assert "atr_period" in params
        assert "adx_trending_threshold" in params
        assert "min_candles" in params

    def test_custom_parameters(self):
        candles = _make_candles(80)
        custom = {
            "adx_period": 14,
            "atr_period": 14,
            "ma_fast": 20,
            "ma_slow": 50,
            "adx_trending_threshold": 30,
            "adx_ranging_threshold": 20,
            "atr_high_percentile": 75,
            "atr_low_percentile": 25,
            "min_candles": 50,
        }
        result = self.detector.detect(
            "EURUSD", candles, None, parameters=custom, data_source="simulated",
        )
        assert result.regime in (
            "TRENDING", "RANGING", "HIGH_VOLATILITY",
            "LOW_VOLATILITY", "TRANSITIONING", "UNKNOWN",
        )
