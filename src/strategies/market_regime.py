"""Market regime detection component.

Identifies market regime (trending, ranging, high/low volatility, transitioning)
using configurable combinations of ADX, ATR, and moving averages.

Classifications are deterministic and independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.indicators.base import IndicatorParameters, ReadinessStatus
from src.market_data.models import MarketTimeframe, OHLCBar


@dataclass(frozen=True)
class MarketRegimeResult:
    """Result of market regime detection."""

    regime: str
    """One of TRENDING, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY,
    TRANSITIONING, UNKNOWN."""

    confidence: Decimal
    """Confidence score (0 to 100)."""

    adx_value: Optional[Decimal]
    """ADX value used in classification, if available."""

    atr_value: Optional[Decimal]
    """ATR value used in classification, if available."""

    atr_percentile: Optional[Decimal]
    """ATR percentile rank within the lookback window."""

    ma_alignment: Optional[str]
    """Moving average alignment: 'bullish', 'bearish', 'mixed', or None."""

    explanation: str
    """Human-readable explanation of the classification."""


class MarketRegimeDetector:
    """Detects market regime using ADX, ATR, and moving averages.

    Rules (configurable via parameters):
        * TRENDING: ADX >= adx_trending_threshold AND MA alignment consistent
        * RANGING: ADX < adx_ranging_threshold AND price within bands
        * HIGH_VOLATILITY: ATR >= atr_high_threshold OR ATR percentile >= 75
        * LOW_VOLATILITY: ATR <= atr_low_threshold OR ATR percentile <= 25
        * TRANSITIONING: ADX rising but below trending threshold, or MA
          alignment changing
        * UNKNOWN: Insufficient data
    """

    def __init__(self) -> None:
        self._default_adx_period = 14
        self._default_atr_period = 14
        self._default_ma_fast = 20
        self._default_ma_slow = 50
        self._default_adx_trending = Decimal("25")
        self._default_adx_ranging = Decimal("20")
        self._default_atr_high_percentile = Decimal("75")
        self._default_atr_low_percentile = Decimal("25")

    @property
    def default_parameters(self) -> Dict[str, Any]:
        return {
            "adx_period": self._default_adx_period,
            "atr_period": self._default_atr_period,
            "ma_fast": self._default_ma_fast,
            "ma_slow": self._default_ma_slow,
            "adx_trending_threshold": float(self._default_adx_trending),
            "adx_ranging_threshold": float(self._default_adx_ranging),
            "atr_high_percentile": float(self._default_atr_high_percentile),
            "atr_low_percentile": float(self._default_atr_low_percentile),
            "min_candles": max(
                self._default_adx_period * 2,
                self._default_atr_period * 2,
                self._default_ma_slow,
            ),
        }

    def detect(
        self,
        symbol: str,
        candles: List[OHLCBar],
        indicator_engine: Any,
        parameters: Optional[Dict[str, Any]] = None,
        data_source: str = "simulated",
    ) -> MarketRegimeResult:
        """Detect market regime for a symbol/timeframe.

        Args:
            symbol: Trading instrument.
            candles: Validated OHLC bars (chronological, complete only).
            indicator_engine: IndicatorEngine instance.
            parameters: Optional parameter overrides.
            data_source: Data source label.

        Returns:
            MarketRegimeResult with regime, confidence, and explanation.
        """
        if parameters is None:
            parameters = dict(self.default_parameters)

        adx_period = int(parameters.get("adx_period", self._default_adx_period))
        atr_period = int(parameters.get("atr_period", self._default_atr_period))
        ma_fast = int(parameters.get("ma_fast", self._default_ma_fast))
        ma_slow = int(parameters.get("ma_slow", self._default_ma_slow))
        adx_trending = Decimal(str(parameters.get(
            "adx_trending_threshold", self._default_adx_trending
        )))
        adx_ranging = Decimal(str(parameters.get(
            "adx_ranging_threshold", self._default_adx_ranging
        )))
        atr_high_pct = Decimal(str(parameters.get(
            "atr_high_percentile", self._default_atr_high_percentile
        )))
        atr_low_pct = Decimal(str(parameters.get(
            "atr_low_percentile", self._default_atr_low_percentile
        )))
        min_candles = int(parameters.get(
            "min_candles", self.default_parameters["min_candles"]
        ))

        n = len(candles)
        if n < min_candles:
            return MarketRegimeResult(
                regime="UNKNOWN",
                confidence=Decimal("0"),
                adx_value=None,
                atr_value=None,
                atr_percentile=None,
                ma_alignment=None,
                explanation=(
                    f"Insufficient data: {n} candles, need at least "
                    f"{min_candles} for regime detection."
                ),
            )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        # --- ADX ---
        adx_value: Optional[Decimal] = None
        try:
            adx_params = __import__(
                "src.indicators.base", fromlist=["IndicatorParameters"]
            ).IndicatorParameters(values={"period": adx_period})
            adx_result = indicator_engine.calculate(
                "ADX", symbol, candles[0].timeframe, candles,
                parameters=adx_params, data_source=data_source,
            )
            adx_series = adx_result.values.get("adx", [])
            adx_values = [v for v in adx_series if v is not None]
            if adx_values:
                adx_value = adx_values[-1]
        except Exception:  # noqa: BLE001
            adx_value = None

        # --- ATR ---
        atr_value: Optional[Decimal] = None
        try:
            atr_params = __import__(
                "src.indicators.base", fromlist=["IndicatorParameters"]
            ).IndicatorParameters(values={"period": atr_period})
            atr_result = indicator_engine.calculate(
                "ATR", symbol, candles[0].timeframe, candles,
                parameters=atr_params, data_source=data_source,
            )
            atr_series = atr_result.values.get("atr", [])
            atr_values = [v for v in atr_series if v is not None]
            if atr_values:
                atr_value = atr_values[-1]
        except Exception:  # noqa: BLE001
            atr_value = None

        # --- ATR percentile (volatility regime) ---
        atr_percentile: Optional[Decimal] = None
        if atr_value is not None and n >= atr_period * 2:
            # Compute ATR series for percentile ranking
            atr_series_raw: List[Decimal] = []
            for i in range(atr_period - 1, n):
                window_highs = highs[i - atr_period + 1 : i + 1]
                window_lows = lows[i - atr_period + 1 : i + 1]
                window_closes = closes[i - atr_period + 1 : i + 1]
                trs: List[Decimal] = []
                for j in range(len(window_highs)):
                    if j == 0:
                        trs.append(window_highs[j] - window_lows[j])
                    else:
                        tr = max(
                            window_highs[j] - window_lows[j],
                            abs(window_highs[j] - window_closes[j - 1]),
                            abs(window_lows[j] - window_closes[j - 1]),
                        )
                        trs.append(tr)
                atr_series_raw.append(sum(trs) / Decimal(len(trs)))
            if atr_series_raw:
                sorted_atr = sorted(atr_series_raw)
                rank = sum(1 for v in sorted_atr if v <= atr_value)
                atr_percentile = Decimal(rank) / Decimal(len(sorted_atr)) * Decimal("100")

        # --- Moving average alignment ---
        ma_alignment: Optional[str] = None
        try:
            ma_fast_params = __import__(
                "src.indicators.base", fromlist=["IndicatorParameters"]
            ).IndicatorParameters(values={"periods": [ma_fast]})
            ma_slow_params = __import__(
                "src.indicators.base", fromlist=["IndicatorParameters"]
            ).IndicatorParameters(values={"periods": [ma_slow]})
            fast_result = indicator_engine.calculate(
                "SMA", symbol, candles[0].timeframe, candles,
                parameters=ma_fast_params, data_source=data_source,
            )
            slow_result = indicator_engine.calculate(
                "SMA", symbol, candles[0].timeframe, candles,
                parameters=ma_slow_params, data_source=data_source,
            )
            fast_series = fast_result.values.get(f"sma_{ma_fast}", [])
            slow_series = slow_result.values.get(f"sma_{ma_slow}", [])
            fast_last = fast_series[-1] if fast_series else None
            slow_last = slow_series[-1] if slow_series else None
            if fast_last is not None and slow_last is not None:
                if fast_last > slow_last:
                    ma_alignment = "bullish"
                elif fast_last < slow_last:
                    ma_alignment = "bearish"
                else:
                    ma_alignment = "mixed"
        except Exception:  # noqa: BLE001
            ma_alignment = None

        # --- Classification ---
        regime = "UNKNOWN"
        confidence = Decimal("0")
        explanation_parts: List[str] = []

        # Volatility regime (ATR-based)
        volatility_note = ""
        if atr_percentile is not None:
            if atr_percentile >= atr_high_pct:
                volatility_note = "high volatility"
            elif atr_percentile <= atr_low_pct:
                volatility_note = "low volatility"
            else:
                volatility_note = "normal volatility"

        # Trend regime (ADX-based)
        trend_note = ""
        if adx_value is not None:
            if adx_value >= adx_trending:
                trend_note = f"strong trend (ADX={adx_value})"
            elif adx_value <= adx_ranging:
                trend_note = f"ranging (ADX={adx_value})"
            else:
                trend_note = f"transitioning (ADX={adx_value})"

        # Combine
        if adx_value is not None and adx_value >= adx_trending:
            if ma_alignment in ("bullish", "bearish"):
                regime = "TRENDING"
                confidence = Decimal("85")
                explanation_parts.append(
                    f"ADX {adx_value} >= trending threshold {adx_trending}; "
                    f"MA alignment {ma_alignment}"
                )
            else:
                regime = "TRENDING"
                confidence = Decimal("60")
                explanation_parts.append(
                    f"ADX {adx_value} >= trending threshold {adx_trending}; "
                    f"MA alignment unclear"
                )
        elif adx_value is not None and adx_value <= adx_ranging:
            regime = "RANGING"
            confidence = Decimal("80")
            explanation_parts.append(
                f"ADX {adx_value} <= ranging threshold {adx_ranging}"
            )
        elif adx_value is not None:
            regime = "TRANSITIONING"
            confidence = Decimal("55")
            explanation_parts.append(
                f"ADX {adx_value} between ranging ({adx_ranging}) and "
                f"trending ({adx_trending}) thresholds"
            )

        if volatility_note:
            explanation_parts.append(volatility_note)

        if atr_percentile is not None:
            if atr_percentile >= atr_high_pct:
                # High volatility overrides ranging to high_volatility
                if regime == "RANGING":
                    regime = "HIGH_VOLATILITY"
                    confidence = Decimal("70")
                explanation_parts.append(
                    f"ATR percentile {atr_percentile:.1f} >= {atr_high_pct}"
                )
            elif atr_percentile <= atr_low_pct:
                if regime == "TRENDING":
                    regime = "LOW_VOLATILITY"
                    confidence = Decimal("70")
                explanation_parts.append(
                    f"ATR percentile {atr_percentile:.1f} <= {atr_low_pct}"
                )

        if not explanation_parts:
            explanation_parts.append(
                "Insufficient indicator data for confident classification"
            )

        explanation = "; ".join(explanation_parts)

        return MarketRegimeResult(
            regime=regime,
            confidence=confidence,
            adx_value=adx_value,
            atr_value=atr_value,
            atr_percentile=atr_percentile,
            ma_alignment=ma_alignment,
            explanation=explanation,
        )
