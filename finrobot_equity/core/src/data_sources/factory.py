"""
适配器工厂 — 根据配置返回对应的数据源适配器。
支持三大市场：美股、A股、加密货币。
新增数据源只需在这里注册。
"""
import re
from .base import DataSourceAdapter
from .yahoo_adapter import YahooFinanceAdapter
from .akshare_adapter import AKShareAdapter
from .eastmoney_adapter import EastMoneyAdapter
from .ths_adapter import THSAdapter
from .crypto_adapter import CryptoAdapter, COINGECKO_IDS

# 注册所有可用的适配器
_ADAPTERS = {
    'yahoo': YahooFinanceAdapter,       # 美股（yfinance）
    'akshare': AKShareAdapter,          # A 股 - 新浪源
    'eastmoney': EastMoneyAdapter,      # A 股 - 东方财富源
    'ths': THSAdapter,                  # A 股 - 同花顺源
    'crypto': CryptoAdapter,            # 加密货币（CCXT + CoinGecko）
    # 'fmp': FMPAdapter,                # 未来: FMP 付费 API
}

# 默认数据源
DEFAULT_SOURCE = 'yahoo'


def detect_market(ticker: str) -> str:
    """
    自动检测 ticker 所属市场。

    Returns:
        'a_share' | 'crypto' | 'us_stock'
    """
    t = ticker.strip().upper()
    # A股: 6位数字
    if re.match(r'^\d{6}$', t):
        return 'a_share'
    # 加密货币: 在已知列表中，或含 -USD/USDT
    if t in COINGECKO_IDS or t.endswith('-USD') or t.endswith('USDT'):
        return 'crypto'
    # 默认: 美股
    return 'us_stock'


def get_adapter(source: str = None, ticker: str = None) -> DataSourceAdapter:
    """
    获取数据源适配器实例。

    Args:
        source: 数据源名称。'auto' 或 None 时根据 ticker 自动选择。
        ticker: 股票/币种代码，用于自动检测市场。

    Returns:
        DataSourceAdapter 实例

    Usage:
        adapter = get_adapter()                     # 默认 Yahoo
        adapter = get_adapter('crypto')             # 指定加密货币
        adapter = get_adapter('auto', 'BTC')        # 自动检测 → crypto
        adapter = get_adapter('auto', '600519')     # 自动检测 → akshare
        adapter = get_adapter('auto', 'AAPL')       # 自动检测 → yahoo
    """
    if source in (None, 'auto') and ticker:
        market = detect_market(ticker)
        if market == 'a_share':
            source = 'akshare'
        elif market == 'crypto':
            source = 'crypto'
        else:
            source = 'yahoo'

    source = source or DEFAULT_SOURCE
    source = source.lower()

    if source not in _ADAPTERS:
        available = ', '.join(_ADAPTERS.keys())
        raise ValueError(f"Unknown data source '{source}'. Available: {available}")

    return _ADAPTERS[source]()


def list_adapters() -> dict:
    """列出所有可用的适配器"""
    return {name: cls.__name__ for name, cls in _ADAPTERS.items()}
