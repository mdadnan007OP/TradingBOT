"""Broker integration package.

Exports the core broker interface and mock adapter. MT5 adapter is imported
lazily when MetaTrader5 package is available to avoid circular dependencies.
"""

from src.broker.base import BrokerAdapter, MockBrokerAdapter
from src.models import TradeResultModel

__all__ = ["BrokerAdapter", "MockBrokerAdapter", "TradeResultModel"]

# MT5 adapter is optional - import lazily to avoid circular dependencies
# and allow the package to work without MetaTrader5 installed.
try:
    from src.broker.mt5 import MT5BrokerAdapter
    __all__.append("MT5BrokerAdapter")
except ImportError:
    # MT5 adapter not available (MetaTrader5 not installed)
    pass