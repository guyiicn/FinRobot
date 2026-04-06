"""
数据源适配器基类 — 所有数据源必须实现这 6 个方法。
新增数据源只需继承此类并实现接口，上游代码零改动。
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from .models import FinancialStatement, CompanyProfile, NewsItem, CompanyData


class DataSourceAdapter(ABC):
    """数据源适配器基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称"""
        pass

    @abstractmethod
    def fetch_financial_statements(
        self, ticker: str, period: str = 'annual', limit: int = 5
    ) -> List[FinancialStatement]:
        """获取财务报表（利润表+资产负债表+现金流量表合并）"""
        pass

    @abstractmethod
    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """获取公司基本信息和市场数据"""
        pass

    @abstractmethod
    def fetch_news(
        self, ticker: str, days: int = 30, limit: int = 20
    ) -> List[NewsItem]:
        """获取新闻"""
        pass

    @abstractmethod
    def fetch_technical_indicators(self, ticker: str) -> dict:
        """获取技术指标（SMA, RSI, MACD 等）"""
        pass

    def fetch_all(self, ticker: str, period: str = 'annual', limit: int = 5) -> CompanyData:
        """一次性获取所有数据，返回统一的 CompanyData 容器"""
        print(f"[{self.name}] Fetching all data for {ticker}...")

        profile = self.fetch_company_profile(ticker)
        print(f"  ✅ Company profile: {profile.name}")

        statements = self.fetch_financial_statements(ticker, period, limit)
        print(f"  ✅ Financial statements: {len(statements)} periods")

        news = self.fetch_news(ticker)
        print(f"  ✅ News: {len(news)} items")

        indicators = self.fetch_technical_indicators(ticker)
        print(f"  ✅ Technical indicators: {len(indicators)} items")

        return CompanyData(
            profile=profile,
            financial_statements=statements,
            news=news,
            technical_indicators=indicators,
        )
