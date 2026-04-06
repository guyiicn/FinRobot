"""
Yahoo Finance 适配器 — 基于 yfinance 库，免费数据源。
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional
from .base import DataSourceAdapter
from .models import FinancialStatement, CompanyProfile, NewsItem


class YahooFinanceAdapter(DataSourceAdapter):
    """Yahoo Finance 数据适配器"""

    @property
    def name(self) -> str:
        return "Yahoo Finance"

    def _safe_get(self, series, keys, default=None):
        """从 pandas Series 中安全获取值，尝试多个可能的字段名"""
        if series is None:
            return default
        for key in keys:
            try:
                if key in series.index:
                    val = series[key]
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return float(val)
            except (KeyError, TypeError, ValueError):
                continue
        return default

    def fetch_financial_statements(
        self, ticker: str, period: str = 'annual', limit: int = 5
    ) -> List[FinancialStatement]:
        """从 Yahoo Finance 获取财务报表"""
        try:
            stock = yf.Ticker(ticker)

            # 获取三张报表
            if period == 'annual':
                income_df = stock.financials
                balance_df = stock.balance_sheet
                cashflow_df = stock.cashflow
            else:
                income_df = stock.quarterly_financials
                balance_df = stock.quarterly_balance_sheet
                cashflow_df = stock.quarterly_cashflow

            # yfinance DataFrame: 行=指标名, 列=日期(Timestamp)
            # 获取所有日期列（取并集）
            dates = set()
            for df in [income_df, balance_df, cashflow_df]:
                if df is not None and not df.empty:
                    dates.update(df.columns.tolist())
            dates = sorted(dates, reverse=True)[:limit]

            statements = []
            for date in dates:
                year = date.year if hasattr(date, 'year') else int(date)

                # 取该日期列作为 Series（index=指标名, values=数值）
                inc = income_df[date] if income_df is not None and not income_df.empty and date in income_df.columns else None
                bal = balance_df[date] if balance_df is not None and not balance_df.empty and date in balance_df.columns else None
                cf = cashflow_df[date] if cashflow_df is not None and not cashflow_df.empty and date in cashflow_df.columns else None

                stmt = FinancialStatement(
                    year=year,
                    period=period,
                    # Income Statement
                    revenue=self._safe_get(inc, ['Total Revenue', 'Total Sales', 'Revenue']),
                    cost_of_revenue=self._safe_get(inc, ['Cost Of Revenue', 'Cost Of Sales', 'Cost Of Goods Sold']),
                    gross_profit=self._safe_get(inc, ['Gross Profit']),
                    operating_expenses=self._safe_get(inc, ['Total Operating Expenses', 'Operating Expense']),
                    sga_expenses=self._safe_get(inc, ['Selling General And Administration', 'Selling General Administrative']),
                    ebitda=self._safe_get(inc, ['EBITDA', 'Normalized EBITDA']),
                    operating_income=self._safe_get(inc, ['Operating Income', 'Operating Revenue']),
                    net_income=self._safe_get(inc, ['Net Income', 'Net Income Common Stockholders']),
                    eps=self._safe_get(inc, ['Basic EPS', 'Diluted EPS']),
                    # Balance Sheet
                    total_assets=self._safe_get(bal, ['Total Assets']),
                    total_liabilities=self._safe_get(bal, ['Total Liabilities Net Minority Interest', 'Total Liabilities']),
                    shareholders_equity=self._safe_get(bal, ['Stockholders Equity', 'Total Equity Gross Minority Interest', 'Shareholders Equity']),
                    total_debt=self._safe_get(bal, ['Total Debt', 'Net Debt']),
                    cash_and_equivalents=self._safe_get(bal, ['Cash And Cash Equivalents', 'Cash Cash Equivalents And Short Term Investments']),
                    # Cash Flow
                    operating_cash_flow=self._safe_get(cf, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities']),
                    investing_cash_flow=self._safe_get(cf, ['Investing Cash Flow', 'Cash Flow From Continuing Investing Activities']),
                    financing_cash_flow=self._safe_get(cf, ['Financing Cash Flow', 'Cash Flow From Continuing Financing Activities']),
                    free_cash_flow=self._safe_get(cf, ['Free Cash Flow']),
                    capital_expenditure=self._safe_get(cf, ['Capital Expenditure']),
                )

                # 如果 gross_profit 没有但有 revenue 和 cost
                if stmt.gross_profit is None and stmt.revenue and stmt.cost_of_revenue:
                    stmt.gross_profit = stmt.revenue - stmt.cost_of_revenue

                # 如果 free_cash_flow 没有但有 operating_cf 和 capex
                if stmt.free_cash_flow is None and stmt.operating_cash_flow and stmt.capital_expenditure:
                    stmt.free_cash_flow = stmt.operating_cash_flow + stmt.capital_expenditure  # capex 通常是负数

                statements.append(stmt)

            return statements

        except Exception as e:
            print(f"[Yahoo] Error fetching financial statements for {ticker}: {e}")
            return []

    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """从 Yahoo Finance 获取公司信息"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}

            return CompanyProfile(
                ticker=ticker,
                name=info.get('longName', info.get('shortName', ticker)),
                sector=info.get('sector', ''),
                industry=info.get('industry', ''),
                description=info.get('longBusinessSummary'),
                price=info.get('currentPrice', info.get('regularMarketPrice')),
                market_cap=info.get('marketCap'),
                volume=info.get('averageVolume'),
                pe_ratio=info.get('trailingPE', info.get('forwardPE')),
                pb_ratio=info.get('priceToBook'),
                ps_ratio=info.get('priceToSalesTrailing12Months'),
                dividend_yield=info.get('dividendYield'),
                beta=info.get('beta'),
                exchange=info.get('exchange', ''),
                country=info.get('country', ''),
                currency=info.get('currency', 'USD'),
                employees=info.get('fullTimeEmployees'),
                website=info.get('website'),
            )
        except Exception as e:
            print(f"[Yahoo] Error fetching company profile for {ticker}: {e}")
            return CompanyProfile(ticker=ticker)

    def fetch_news(self, ticker: str, days: int = 30, limit: int = 20) -> List[NewsItem]:
        """从 Yahoo Finance 获取新闻"""
        try:
            stock = yf.Ticker(ticker)
            raw_news = stock.news or []

            items = []
            for n in raw_news[:limit]:
                content = n.get('title', '')
                pub_date = datetime.fromtimestamp(n.get('providerPublishTime', 0)) if n.get('providerPublishTime') else datetime.now()

                # 过滤时间范围
                if (datetime.now() - pub_date).days > days:
                    continue

                items.append(NewsItem(
                    date=pub_date,
                    title=n.get('title', ''),
                    content=content,
                    source=n.get('publisher', ''),
                    url=n.get('link'),
                ))

            return items
        except Exception as e:
            print(f"[Yahoo] Error fetching news for {ticker}: {e}")
            return []

    def fetch_technical_indicators(self, ticker: str) -> dict:
        """计算技术指标"""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='1y')

            if hist.empty:
                return {}

            close = hist['Close']
            indicators = {}

            # SMA
            for period in [20, 50, 200]:
                sma = close.rolling(window=period).mean()
                if not sma.empty and not np.isnan(sma.iloc[-1]):
                    indicators[f'SMA_{period}'] = round(float(sma.iloc[-1]), 2)

            # RSI (14-day)
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            if not rsi.empty and not np.isnan(rsi.iloc[-1]):
                indicators['RSI_14'] = round(float(rsi.iloc[-1]), 2)

            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal = macd_line.ewm(span=9, adjust=False).mean()
            if not macd_line.empty:
                indicators['MACD'] = round(float(macd_line.iloc[-1]), 4)
                indicators['MACD_Signal'] = round(float(signal.iloc[-1]), 4)

            # 52-week high/low
            high_52w = close.rolling(window=252).max()
            low_52w = close.rolling(window=252).min()
            if not high_52w.empty:
                indicators['52W_High'] = round(float(high_52w.iloc[-1]), 2)
                indicators['52W_Low'] = round(float(low_52w.iloc[-1]), 2)

            # Current price
            indicators['Current_Price'] = round(float(close.iloc[-1]), 2)

            return indicators
        except Exception as e:
            print(f"[Yahoo] Error computing technical indicators for {ticker}: {e}")
            return {}
