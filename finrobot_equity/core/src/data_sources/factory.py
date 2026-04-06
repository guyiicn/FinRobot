"""
适配器工厂 — 根据配置返回对应的数据源适配器。
新增数据源只需在这里注册。
"""
from .base import DataSourceAdapter
from .yahoo_adapter import YahooFinanceAdapter
from .akshare_adapter import AKShareAdapter
from .eastmoney_adapter import EastMoneyAdapter
from .ths_adapter import THSAdapter

# 注册所有可用的适配器
_ADAPTERS = {
    'yahoo': YahooFinanceAdapter,       # 美股（yfinance）
    'akshare': AKShareAdapter,          # A 股 - 新浪源
    'eastmoney': EastMoneyAdapter,      # A 股 - 东方财富源
    'ths': THSAdapter,                  # A 股 - 同花顺源
    # 'fmp': FMPAdapter,                # 未来: FMP 付费 API
}

# 默认数据源
DEFAULT_SOURCE = 'yahoo'


def get_adapter(source: str = None) -> DataSourceAdapter:
    """
    获取数据源适配器实例。

    Args:
        source: 数据源名称 ('yahoo', 'fmp', 等)。None 使用默认值。

    Returns:
        DataSourceAdapter 实例

    Usage:
        adapter = get_adapter()          # 默认 Yahoo
        adapter = get_adapter('yahoo')   # 指定 Yahoo
        adapter = get_adapter('fmp')     # 指定 FMP (需先实现)
    """
    source = source or DEFAULT_SOURCE
    source = source.lower()

    if source not in _ADAPTERS:
        available = ', '.join(_ADAPTERS.keys())
        raise ValueError(f"Unknown data source '{source}'. Available: {available}")

    return _ADAPTERS[source]()


def list_adapters() -> dict:
    """列出所有可用的适配器"""
    return {name: cls.__name__ for name, cls in _ADAPTERS.items()}
