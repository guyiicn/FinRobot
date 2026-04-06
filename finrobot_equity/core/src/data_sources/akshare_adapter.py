"""
AKShare A 股适配器 — 基于 akshare 库，免费数据源，支持沪深 A 股。

注意事项：
1. Ticker 格式：6 位数字（如 600519=茅台, 000001=平安, 300750=宁德时代, 688981=科创板）
2. 货币单位：人民币 CNY，财报数据单位为元
3. 财报列名为中文
4. AKShare 有请求频率限制，每次请求间隔 1 秒
5. 年报/季报时间：A 股年报 4 月底前披露
"""
import time
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import contextmanager

from .base import DataSourceAdapter
from .models import FinancialStatement, CompanyProfile, NewsItem

# 请求间隔（秒），防止被封
REQUEST_INTERVAL = 1.0


@contextmanager
def no_proxy():
    """临时去掉代理环境变量，让国内 API 直连"""
    saved = {}
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        yield
    finally:
        os.environ.update(saved)


def _safe_float(val, default=None):
    """安全转 float"""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        v = float(val)
        return v if not np.isnan(v) and v != 0.0 else default
    except (TypeError, ValueError):
        return default


def _is_annual(report_date: str) -> bool:
    """判断是否为年报（1231 结尾）"""
    return str(report_date).endswith('1231')


def _is_quarterly(report_date: str, quarter: int = None) -> bool:
    """判断是否为指定季报"""
    s = str(report_date)
    if quarter is None:
        return True
    endings = {1: '0331', 2: '0630', 3: '0930', 4: '1231'}
    return s.endswith(endings.get(quarter, ''))


class AKShareAdapter(DataSourceAdapter):
    """AKShare A 股数据适配器"""

    @property
    def name(self) -> str:
        return "AKShare (A股)"

    def _normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker 格式，去掉可能的前缀"""
        # 支持 sh600519, sz000001, 600519.SH 等格式
        ticker = ticker.strip().upper()
        for prefix in ['SH', 'SZ', 'BJ']:
            ticker = ticker.replace(prefix, '')
        ticker = ticker.replace('.', '').strip()
        # 确保 6 位数字
        return ticker.zfill(6)

    def fetch_all(self, ticker: str, period: str = 'annual', limit: int = 5):
        """重写 fetch_all，整个过程去掉代理"""
        with no_proxy():
            return super().fetch_all(ticker, period, limit)

    def fetch_financial_statements(
        self, ticker: str, period: str = 'annual', limit: int = 5
    ) -> List[FinancialStatement]:
        """从 AKShare 获取 A 股财务报表"""
        import akshare as ak

        ticker = self._normalize_ticker(ticker)
        statements = []

        try:
            # 1. 利润表
            print(f"  [AKShare] 获取利润表 {ticker}...")
            income_df = ak.stock_financial_report_sina(stock=ticker, symbol='利润表')
            time.sleep(REQUEST_INTERVAL)

            # 2. 资产负债表
            print(f"  [AKShare] 获取资产负债表 {ticker}...")
            balance_df = ak.stock_financial_report_sina(stock=ticker, symbol='资产负债表')
            time.sleep(REQUEST_INTERVAL)

            # 3. 现金流量表
            print(f"  [AKShare] 获取现金流量表 {ticker}...")
            cashflow_df = ak.stock_financial_report_sina(stock=ticker, symbol='现金流量表')
            time.sleep(REQUEST_INTERVAL)

            # 筛选年报或季报
            if period == 'annual':
                income_df = income_df[income_df['报告日'].astype(str).str.endswith('1231')]
                balance_df = balance_df[balance_df['报告日'].astype(str).str.endswith('1231')]
                cashflow_df = cashflow_df[cashflow_df['报告日'].astype(str).str.endswith('1231')]

            # 按日期排序，取最近 limit 条
            income_df = income_df.sort_values('报告日', ascending=False).head(limit).reset_index(drop=True)
            balance_df = balance_df.sort_values('报告日', ascending=False).head(limit).reset_index(drop=True)
            cashflow_df = cashflow_df.sort_values('报告日', ascending=False).head(limit).reset_index(drop=True)

            # 构建索引：报告日 → row
            balance_map = {str(row['报告日']): row for _, row in balance_df.iterrows()}
            cashflow_map = {str(row['报告日']): row for _, row in cashflow_df.iterrows()}

            for _, inc_row in income_df.iterrows():
                report_date = str(inc_row['报告日'])
                year = int(report_date[:4])

                bal_row = balance_map.get(report_date)
                cf_row = cashflow_map.get(report_date)

                # 计算 SG&A = 销售费用 + 管理费用
                sales_expense = _safe_float(inc_row.get('销售费用'))
                admin_expense = _safe_float(inc_row.get('管理费用'))
                sga = None
                if sales_expense is not None or admin_expense is not None:
                    sga = (sales_expense or 0) + (admin_expense or 0)

                # 计算 EBITDA = 营业利润 + 折旧摊销（简化：用营业利润 + 财务费用近似）
                operating_profit = _safe_float(inc_row.get('营业利润'))
                depreciation = None
                if cf_row is not None:
                    # 现金流量表中的"固定资产折旧、油气资产折耗、生产性生物资产折旧"
                    depreciation = _safe_float(cf_row.get('固定资产折旧、油气资产折耗、生产性生物资产折旧'))
                ebitda = None
                if operating_profit is not None:
                    ebitda = operating_profit + (depreciation or 0)

                # Gross profit = 营业收入 - 营业成本
                revenue = _safe_float(inc_row.get('营业收入')) or _safe_float(inc_row.get('营业总收入'))
                cost_of_revenue = _safe_float(inc_row.get('营业成本'))
                gross_profit = None
                if revenue and cost_of_revenue:
                    gross_profit = revenue - cost_of_revenue

                stmt = FinancialStatement(
                    year=year,
                    period=period,
                    # 利润表
                    revenue=revenue,
                    cost_of_revenue=cost_of_revenue,
                    gross_profit=gross_profit,
                    operating_expenses=_safe_float(inc_row.get('营业总成本')),
                    sga_expenses=sga,
                    ebitda=ebitda,
                    operating_income=operating_profit,
                    net_income=_safe_float(inc_row.get('归属于母公司所有者的净利润')) or _safe_float(inc_row.get('净利润')),
                    eps=_safe_float(inc_row.get('基本每股收益')),
                    # 资产负债表
                    total_assets=_safe_float(bal_row.get('资产总计')) if bal_row is not None else None,
                    total_liabilities=_safe_float(bal_row.get('负债合计')) if bal_row is not None else None,
                    shareholders_equity=_safe_float(bal_row.get('归属于母公司所有者权益合计')) or (_safe_float(bal_row.get('所有者权益(或股东权益)合计')) if bal_row is not None else None),
                    total_debt=(_safe_float(bal_row.get('短期借款', 0)) or 0) + (_safe_float(bal_row.get('长期借款', 0)) or 0) if bal_row is not None else None,
                    cash_and_equivalents=_safe_float(bal_row.get('货币资金')) if bal_row is not None else None,
                    # 现金流量表
                    operating_cash_flow=_safe_float(cf_row.get('经营活动产生的现金流量净额')) if cf_row is not None else None,
                    investing_cash_flow=_safe_float(cf_row.get('投资活动产生的现金流量净额')) if cf_row is not None else None,
                    financing_cash_flow=_safe_float(cf_row.get('筹资活动产生的现金流量净额')) if cf_row is not None else None,
                    capital_expenditure=_safe_float(cf_row.get('购建固定资产、无形资产和其他长期资产支付的现金')) if cf_row is not None else None,
                )

                # 计算 free cash flow
                if stmt.operating_cash_flow is not None and stmt.capital_expenditure is not None:
                    stmt.free_cash_flow = stmt.operating_cash_flow - stmt.capital_expenditure

                statements.append(stmt)

            return statements

        except Exception as e:
            print(f"  [AKShare] 获取财务报表失败 {ticker}: {e}")
            return []

    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """从 AKShare（东方财富）获取公司信息"""
        import akshare as ak

        ticker = self._normalize_ticker(ticker)
        first_digit = ticker[0]
        if first_digit in ('6', '9'):
            exchange = '上交所 (SSE)'
        elif first_digit in ('0', '2', '3'):
            exchange = '深交所 (SZSE)'
        else:
            exchange = '北交所 (BSE)'

        try:
            info_df = ak.stock_individual_info_em(symbol=ticker)
            time.sleep(REQUEST_INTERVAL)
            info_map = {str(row['item']): row['value'] for _, row in info_df.iterrows()}

            pe_ratio = None
            pb_ratio = None
            try:
                indicator_df = ak.stock_a_indicator_lg(symbol=ticker)
                time.sleep(REQUEST_INTERVAL)
                if indicator_df is not None and not indicator_df.empty:
                    latest = indicator_df.iloc[-1]
                    pe_ratio = _safe_float(latest.get('pe'))
                    pb_ratio = _safe_float(latest.get('pb'))
            except Exception:
                pass

            return CompanyProfile(
                ticker=ticker,
                name=str(info_map.get('股票简称', '')),
                sector=str(info_map.get('行业', '')),
                industry=str(info_map.get('行业', '')),
                price=_safe_float(info_map.get('最新')),
                market_cap=_safe_float(info_map.get('总市值')),
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
                exchange=exchange,
                country='中国',
                currency='CNY',
            )
        except Exception as e:
            print(f"  [AKShare] 获取公司信息失败 {ticker}: {str(e)[:80]}")
            return CompanyProfile(ticker=ticker, exchange=exchange, country='中国', currency='CNY')

    def fetch_news(self, ticker: str, days: int = 30, limit: int = 20) -> List[NewsItem]:
        """从东方财富获取 A 股新闻"""
        import akshare as ak

        ticker = self._normalize_ticker(ticker)

        try:
            news_df = ak.stock_news_em(symbol=ticker)
            time.sleep(REQUEST_INTERVAL)

            if news_df is None or news_df.empty:
                return []

            items = []
            for _, row in news_df.head(limit).iterrows():
                try:
                    pub_date = pd.to_datetime(row.get('发布时间', ''))
                except:
                    pub_date = datetime.now()

                # 过滤时间范围
                if (datetime.now() - pub_date).days > days:
                    continue

                items.append(NewsItem(
                    date=pub_date,
                    title=str(row.get('新闻标题', '')),
                    content=str(row.get('新闻内容', ''))[:500],
                    source=str(row.get('文章来源', '东方财富')),
                    url=str(row.get('新闻链接', '')),
                ))

            return items

        except Exception as e:
            print(f"  [AKShare] 获取新闻失败 {ticker}: {e}")
            return []

    def fetch_technical_indicators(self, ticker: str) -> dict:
        """从 AKShare 获取日 K 数据并计算技术指标"""
        import akshare as ak

        ticker = self._normalize_ticker(ticker)

        try:
            # 获取一年日 K 数据
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')

            hist = ak.stock_zh_a_hist(
                symbol=ticker,
                period='daily',
                start_date=start_date,
                end_date=end_date,
                adjust='qfq'  # 前复权
            )
            time.sleep(REQUEST_INTERVAL)

            if hist is None or hist.empty:
                return {}

            close = hist['收盘'].astype(float)
            indicators = {}

            # SMA
            for period in [20, 50, 200]:
                if len(close) >= period:
                    sma = close.rolling(window=period).mean()
                    if not sma.empty and not np.isnan(sma.iloc[-1]):
                        indicators[f'SMA_{period}'] = round(float(sma.iloc[-1]), 2)

            # RSI (14-day)
            if len(close) >= 14:
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                if not rsi.empty and not np.isnan(rsi.iloc[-1]):
                    indicators['RSI_14'] = round(float(rsi.iloc[-1]), 2)

            # MACD
            if len(close) >= 26:
                ema12 = close.ewm(span=12, adjust=False).mean()
                ema26 = close.ewm(span=26, adjust=False).mean()
                macd_line = ema12 - ema26
                signal = macd_line.ewm(span=9, adjust=False).mean()
                indicators['MACD'] = round(float(macd_line.iloc[-1]), 4)
                indicators['MACD_Signal'] = round(float(signal.iloc[-1]), 4)

            # 52 周高低
            if len(close) >= 200:
                indicators['52W_High'] = round(float(close.tail(252).max()), 2)
                indicators['52W_Low'] = round(float(close.tail(252).min()), 2)

            # 当前价格
            indicators['Current_Price'] = round(float(close.iloc[-1]), 2)

            # 成交量均值
            if '成交量' in hist.columns:
                vol = hist['成交量'].astype(float)
                indicators['Avg_Volume_20d'] = int(vol.tail(20).mean())

            return indicators

        except Exception as e:
            print(f"  [AKShare] 获取技术指标失败 {ticker}: {str(e)[:80]}")
            return {}
