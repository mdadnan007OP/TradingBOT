"""MT5 symbol discovery and mapping."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set

from src.market_data.models import (
    InstrumentSpec,
    InstrumentType,
    MarketTimeframe,
    VolumeType,
)
from src.broker.mt5.exceptions import MT5SymbolError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MT5SymbolInfo:
    """Raw MT5 symbol information."""
    name: str
    description: str
    base_currency: str
    quote_currency: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_mode: int
    swap_long: float
    swap_short: float
    session_volume: int
    spread: int
    margin_initial: float
    margin_maintenance: float
    path: str


@dataclass
class SymbolMapping:
    """Mapping between canonical and broker symbols."""
    canonical_symbol: str
    broker_symbol: str
    confidence: float = 1.0
    notes: str = ""


class MT5SymbolDiscovery:
    """Discovers and maps broker symbols to internal canonical symbols."""

    # Known symbol mappings for common instruments
    # Key: canonical symbol, Value: list of possible broker symbol variants
    COMMON_MAPPINGS: Dict[str, List[str]] = {
        "XAUUSD": ["XAUUSD", "GOLD", "XAU/USD", "GOLDUSD"],
        "XAGUSD": ["XAGUSD", "SILVER", "XAG/USD", "SILVERUSD"],
        "EURUSD": ["EURUSD", "EUR/USD"],
        "GBPUSD": ["GBPUSD", "GBP/USD"],
        "USDJPY": ["USDJPY", "USD/JPY"],
        "AUDUSD": ["AUDUSD", "AUD/USD"],
        "USDCAD": ["USDCAD", "USD/CAD"],
        "NZDUSD": ["NZDUSD", "NZD/USD"],
        "USDCHF": ["USDCHF", "USD/CHF"],
        "WTIUSD": ["WTIUSD", "WTI", "USOIL", "CL", "XTIUSD"],
        "BRENTUSD": ["BRENTUSD", "BRENT", "UKOIL", "CO", "XBRUSD"],
        "NATGASUSD": ["NATGASUSD", "NGAS", "NATGAS", "XNGUSD"],
        "NAS100": ["NAS100", "NASDAQ", "USTEC", "NAS100.cash"],
        "US500": ["US500", "SP500", "SPX500", "US500.cash"],
        "US30": ["US30", "DJ30", "WS30", "US30.cash"],
        "GER40": ["GER40", "DE40", "DAX40", "GER40.cash"],
        "UK100": ["UK100", "FTSE100", "UK100.cash"],
        "BTCUSD": ["BTCUSD", "BTC/USD", "BITCOIN"],
        "ETHUSD": ["ETHUSD", "ETH/USD", "ETHEREUM"],
    }

    def __init__(self, mt5_module) -> None:
        self._mt5 = mt5_module
        self._all_symbols: Dict[str, MT5SymbolInfo] = {}
        self._mappings: List[SymbolMapping] = []
        self._discovered = False

    def discover_symbols(self) -> List[MT5SymbolInfo]:
        """Discover all available symbols from MT5 terminal.

        Returns:
            List of MT5SymbolInfo for all symbols.

        Raises:
            MT5SymbolError: If symbol discovery fails.
        """
        if self._discovered and self._all_symbols:
            return list(self._all_symbols.values())

        try:
            symbols = self._mt5.symbols_get()
            if symbols is None:
                error = self._mt5.last_error()
                raise MT5SymbolError(f"Failed to get symbols: {error}")

            for sym in symbols:
                info = MT5SymbolInfo(
                    name=sym.name,
                    description=getattr(sym, 'description', ''),
                    base_currency=getattr(sym, 'currency_base', ''),
                    quote_currency=getattr(sym, 'currency_profit', ''),
                    digits=getattr(sym, 'digits', 5),
                    point=getattr(sym, 'point', 0.00001),
                    tick_size=getattr(sym, 'trade_tick_size', getattr(sym, 'point', 0.00001)),
                    tick_value=getattr(sym, 'trade_tick_value', 0.0),
                    contract_size=getattr(sym, 'trade_contract_size', 100000.0),
                    volume_min=getattr(sym, 'volume_min', 0.01),
                    volume_max=getattr(sym, 'volume_max', 100.0),
                    volume_step=getattr(sym, 'volume_step', 0.01),
                    trade_mode=getattr(sym, 'trade_mode', 0),
                    swap_long=getattr(sym, 'swap_long', 0.0),
                    swap_short=getattr(sym, 'swap_short', 0.0),
                    session_volume=getattr(sym, 'session_volume', 0),
                    spread=getattr(sym, 'spread', 0),
                    margin_initial=getattr(sym, 'margin_initial', 0.0),
                    margin_maintenance=getattr(sym, 'margin_maintenance', 0.0),
                    path=getattr(sym, 'path', ''),
                )
                self._all_symbols[info.name] = info

            self._discovered = True
            logger.info("Discovered %d symbols from MT5", len(self._all_symbols))
            return list(self._all_symbols.values())

        except Exception as exc:
            if isinstance(exc, MT5SymbolError):
                raise
            raise MT5SymbolError(f"Symbol discovery failed: {exc}") from exc

    def get_symbol_info(self, broker_symbol: str) -> Optional[MT5SymbolInfo]:
        """Get symbol info for a specific broker symbol."""
        if not self._discovered:
            self.discover_symbols()
        return self._all_symbols.get(broker_symbol)

    def find_broker_symbol(self, canonical: str) -> List[str]:
        """Find possible broker symbols for a canonical symbol.

        Returns:
            List of broker symbol names that match, ordered by confidence.
        """
        if not self._discovered:
            self.discover_symbols()

        # Check common mappings first (including suffix variants).
        candidates = self.COMMON_MAPPINGS.get(canonical.upper(), [])
        found = []

        for candidate in candidates:
            if candidate in self._all_symbols:
                found.append(candidate)
            # Brokers often append suffixes like .s, .raw, .ecn, .pro.
            for suffix in [".s", ".raw", ".ecn", ".pro", ".cash", ".fx"]:
                variant = candidate + suffix
                if variant in self._all_symbols and variant not in found:
                    found.append(variant)

        # Also try exact match
        if canonical in self._all_symbols and canonical not in found:
            found.insert(0, canonical)

        # Try with common suffixes on the canonical symbol itself.
        for suffix in [".s", ".raw", ".ecn", ".pro", ".cash", ".fx"]:
            variant = canonical + suffix
            if variant in self._all_symbols and variant not in found:
                found.append(variant)

        return found

    def create_mapping(
        self,
        canonical: str,
        broker_symbol: str,
        confidence: float = 1.0,
        notes: str = "",
    ) -> SymbolMapping:
        """Create a symbol mapping."""
        return SymbolMapping(
            canonical_symbol=canonical,
            broker_symbol=broker_symbol,
            confidence=confidence,
            notes=notes,
        )

    def auto_map_symbols(self, canonical_symbols: List[str]) -> List[SymbolMapping]:
        """Automatically map a list of canonical symbols to broker symbols.

        Returns:
            List of SymbolMapping for successfully mapped symbols.
        """
        if not self._discovered:
            self.discover_symbols()

        mappings = []
        for canonical in canonical_symbols:
            matches = self.find_broker_symbol(canonical)
            if matches:
                # Use the first (highest confidence) match
                broker_sym = matches[0]
                confidence = 1.0 if len(matches) == 1 else 0.8
                notes = f"Auto-mapped from {len(matches)} candidates" if len(matches) > 1 else "Exact match"
                mappings.append(self.create_mapping(canonical, broker_sym, confidence, notes))
                logger.info("Mapped %s -> %s (%s)", canonical, broker_sym, notes)
            else:
                logger.warning("No broker symbol found for canonical: %s", canonical)

        self._mappings = mappings
        return mappings

    def get_mapping(self, canonical: str) -> Optional[SymbolMapping]:
        """Get mapping for a canonical symbol."""
        for m in self._mappings:
            if m.canonical_symbol == canonical:
                return m
        return None

    def get_broker_symbol(self, canonical: str) -> Optional[str]:
        """Get broker symbol for a canonical symbol."""
        mapping = self.get_mapping(canonical)
        return mapping.broker_symbol if mapping else None

    def to_instrument_spec(
        self,
        canonical: str,
        broker_symbol: str,
        mt5_info: MT5SymbolInfo,
    ) -> InstrumentSpec:
        """Convert MT5 symbol info to InstrumentSpec."""
        # Determine instrument type from path or name
        instrument_type = self._infer_instrument_type(mt5_info)

        # Determine volume type
        volume_type = VolumeType.TICK
        if mt5_info.session_volume > 0:
            volume_type = VolumeType.REAL

        # Determine supported timeframes (MT5 supports all standard timeframes)
        supported_timeframes = list(MarketTimeframe)

        return InstrumentSpec(
            canonical_symbol=canonical,
            broker_symbol=broker_symbol,
            name=mt5_info.description or canonical,
            instrument_type=instrument_type,
            base_currency=mt5_info.base_currency or None,
            quote_currency=mt5_info.quote_currency or None,
            price_precision=mt5_info.digits,
            tick_size=Decimal(str(mt5_info.tick_size)),
            pip_size=Decimal(str(mt5_info.point * 10)) if instrument_type == InstrumentType.FOREX else None,
            contract_size=Decimal(str(mt5_info.contract_size)),
            volume_type=volume_type,
            supported_timeframes=supported_timeframes,
            market_session=self._infer_market_session(instrument_type),
        )

    def _infer_instrument_type(self, info: MT5SymbolInfo) -> InstrumentType:
        """Infer instrument type from MT5 symbol info.

        More specific asset classes are checked before forex so that a metal
        or energy symbol listed under a generic path is not misclassified.
        """
        path = info.path.lower()
        name = info.name.lower()
        description = info.description.lower()

        # Metals (check before forex: gold/silver may sit under odd paths).
        if (
            "metal" in path
            or "gold" in name
            or "silver" in name
            or "xau" in name
            or "xag" in name
            or "xpt" in name
            or "xpd" in name
            or "gold" in description
            or "silver" in description
        ):
            return InstrumentType.METAL
        # Energy.
        if (
            "energy" in path
            or "oil" in name
            or "wti" in name
            or "brent" in name
            or "gas" in name
            or "crude" in description
        ):
            return InstrumentType.ENERGY
        # Indices.
        if (
            "index" in path
            or "indices" in path
            or "cash" in name
            or "nas" in name
            or "spx" in name
            or "sp500" in name
            or "dax" in name
            or "ftse" in name
            or "index" in description
        ):
            return InstrumentType.INDEX
        # Crypto.
        if (
            "crypto" in path
            or "btc" in name
            or "eth" in name
            or "bitcoin" in description
            or "ethereum" in description
        ):
            return InstrumentType.CRYPTO
        # Forex fallback.
        return InstrumentType.FOREX

    def _infer_market_session(self, instrument_type: InstrumentType) -> str:
        """Map instrument type to market session."""
        mapping = {
            InstrumentType.FOREX: "forex",
            InstrumentType.METAL: "metals",
            InstrumentType.ENERGY: "energy",
            InstrumentType.INDEX: "indices",
            InstrumentType.CRYPTO: "crypto",
        }
        return mapping.get(instrument_type, "forex")

    def generate_discovery_report(self) -> str:
        """Generate a human-readable symbol discovery report."""
        if not self._discovered:
            self.discover_symbols()

        lines = [
            "=" * 60,
            "MT5 Symbol Discovery Report",
            "=" * 60,
            f"Total symbols discovered: {len(self._all_symbols)}",
            f"Successfully mapped: {len(self._mappings)}",
            "",
            "Mappings:",
            "-" * 60,
        ]

        for mapping in self._mappings:
            info = self._all_symbols.get(mapping.broker_symbol)
            if info:
                lines.append(
                    f"  {mapping.canonical_symbol:10} -> {mapping.broker_symbol:15} "
                    f"({info.description[:40]:40}) confidence={mapping.confidence:.1f}"
                )
            else:
                lines.append(f"  {mapping.canonical_symbol:10} -> {mapping.broker_symbol:15} (info unavailable)")

        lines.append("")
        lines.append("Available symbols (sample):")
        lines.append("-" * 60)
        for name, info in list(self._all_symbols.items())[:20]:
            lines.append(f"  {name:20} {info.description[:50]}")

        if len(self._all_symbols) > 20:
            lines.append(f"  ... and {len(self._all_symbols) - 20} more")

        return "\n".join(lines)