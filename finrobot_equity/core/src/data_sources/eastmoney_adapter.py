"""
东方财富适配器 — 基于 akshare 的东方财富 (em) 接口，免费 A 股数据源。
与 AKShareAdapter（新浪源）形成双数据源交叉验证。

底层接口区别：
- AKShareAdapter: stock_financial_report_sina（新浪财经原始三表）
- EastMoneyAdapter: stock_financial_analysis_indicator（东方财富加工指标）
  + stock_individual_info_em（公司信息）
  + stock_zh_a_hist（日K行情）
  + stock_news_em（新闻）
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

REQUEST_INTERVAL = 1.5


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
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        v = float(val)
        return v if not np.isnan(v) else default
    except (TypeError, ValueError):
        return default


class EastMoneyAdapter(DataSourceAdapter):
    """东方财富数据适配器（独立于新浪源，用于交叉验证）"""

    @property
    def name(self) -> str:
        return "东方财富 (EastMoney)"

    def fetch_all(self, ticker: str, period: str = 'annual', limit: int = 5):
        """重写 fetch_all，整个过程去掉代理"""
        with no_proxy():
            return super().fetch_all(ticker, period, limit)

    def _normalize_ticker(self, ticker: str) -> str:
        ticker = ticker.strip().upper()
        for prefix in ['SH', 'SZ', 'BJ']:
            ticker = ticker.replace(prefix, '')
        ticker = ticker.replace('.', '').strip()
        return ticker.zfill(6)

    def fetch_financial_statements(
        self, ticker: str, period: str = 'annual', limit: int = 5
    ) -> List[FinancialStatement]:
        """
        从东方财富获取财务分析指标。
        注意：东方财富的 stock_financial_analysis_indicator 返回的是加工后的指标，
        不是原始三表数据。部分绝对值字段（如 revenue）需要从其他接口补充。
        这里尝试用新浪三表做补充（如果可用）。
        """
        import akshare as ak

        ticker = self._normalize_ticker(ticker)
        statements = []

        try:
            # 东方财富财务指标（包含 PE/ROE/毛利率等丰富的比率）
            print(f"  [东方财富] 获取财务分析指标 {ticker}...")
            start_year = str(datetime.now().year - limit - 1)
            indicator_df = ak.stock_financial_analysis_indicator(symbol=ticker, start_year=start_year)
            time.sleep(REQUEST_INTERVAL)

            if indicator_df is None or indicator_df.empty:
                print(f"  [东方财富] 无财务指标数据")
                return []

            # 筛选年报
            if period == 'annual':
                indicator_df['日期'] = pd.to_datetime(indicator_df['日期'])
                indicator_df = indicator_df[indicator_df['日期'].dt.month == 12]

            indicator_df = indicator_df.sort_values('日期', ascending=False).head(limit).reset_index(drop=True)

            # 尝试从新浪获取原始三表数据做补充
            income_map = {}
            balance_map = {}
            cashflow_map = {}
            try:
                print(f"  [东方财富] 补充新浪利润表数据...")
                inc_df = ak.stock_financial_report_sina(stock=ticker, symbol='利润表')
                time.sleep(REQUEST_INTERVAL)
                if period == 'annual':
                    inc_df = inc_df[inc_df['报告日'].astype(str).str.endswith('1231')]
                for _, row in inc_df.iterrows():
                    year = int(str(row['报告日'])[:4])
                    income_map[year] = row

                print(f"  [东方财富] 补充新浪资产负债表数据...")
                bal_df = ak.stock_financial_report_sina(stock=ticker, symbol='资产负债表')
                time.sleep(REQUEST_INTERVAL)
                if period == 'annual':
                    bal_df = bal_df[bal_df['报告日'].astype(str).str.endswith('1231')]
                for _, row in bal_df.iterrows():
                    year = int(str(row['报告日'])[:4])
                    balance_map[year] = row

                print(f"  [东方财富] 补充新浪现金流量表数据...")
                cf_df = ak.stock_financial_report_sina(stock=ticker, symbol='现金流量表')
                time.sleep(REQUEST_INTERVAL)
                if period == 'annual':
                    cf_df = cf_df[cf_df['报告日'].astype(str).str.endswith('1231')]
                for _, row in cf_df.iterrows():
                    year = int(str(row['报告日'])[:4])
                    cashflow_map[year] = row
            except Exception as e:
                print(f"  [东方财富] 补充新浪数据失败: {e}，仅使用东方财富指标")

            for _, ind_row in indicator_df.iterrows():
                year = ind_row['日期'].year if hasattr(ind_row['日期'], 'year') else int(str(ind_row['日期'])[:4])

                inc_row = income_map.get(year, None)
                bal_row = balance_map.get(year, None)
                cf_row = cashflow_map.get(year, None)

                def _has(row):
                    """判断 row 是否有有效数据（支持 dict 和 Series）"""
                    if row is None:
                        return False
                    if isinstance(row, pd.Series):
                        return not row.empty
                    return bool(row)

                def _get(row, key, default=None):
                    """安全从 dict 或 Series 取值"""
                    if row is None:
                        return default
                    try:
                        val = row.get(key)
                        return val if val is not None else default
                    except:
                        return default

                # 从新浪三表取绝对值
                revenue = _safe_float(_get(inc_row, '营业收入')) or _safe_float(_get(inc_row, '营业总收入'))
                cost_of_revenue = _safe_float(_get(inc_row, '营业成本'))
                net_income = _safe_float(_get(inc_row, '归属于母公司所有者的净利润')) or _safe_float(_get(inc_row, '净利润'))

                sga = None
                sales_exp = _safe_float(_get(inc_row, '销售费用'))
                admin_exp = _safe_float(_get(inc_row, '管理费用'))
                if sales_exp is not None or admin_exp is not None:
                    sga = (sales_exp or 0) + (admin_exp or 0)

                gross_profit = None
                if revenue and cost_of_revenue:
                    gross_profit = revenue - cost_of_revenue

                operating_income = _safe_float(_get(inc_row, '营业利润'))

                # EBITDA 从东方财富的营业利润率反推，或从新浪补充
                ebitda = None
                if operating_income is not None:
                    depreciation = _safe_float(_get(cf_row, '固定资产折旧、油气资产折耗、生产性生物资产折旧')) if _has(cf_row) else None
                    ebitda = operating_income + (depreciation or 0)

                # 从东方财富指标取比率和 EPS
                eps = _safe_float(ind_row.get('加权每股收益(元)'))
                roe = _safe_float(ind_row.get('净资产收益率(%)'))
                if roe:
                    roe = roe / 100  # 转为小数

                gross_margin_pct = _safe_float(ind_row.get('销售毛利率(%)'))
                net_margin_pct = _safe_float(ind_row.get('销售净利率(%)'))
                operating_margin_pct = _safe_float(ind_row.get('营业利润率(%)'))

                total_assets = _safe_float(ind_row.get('总资产(元)')) or (_safe_float(_get(bal_row, '资产总计')) if _has(bal_row) else None)

                stmt = FinancialStatement(
                    year=year,
                    period=period,
                    revenue=revenue,
                    cost_of_revenue=cost_of_revenue,
                    gross_profit=gross_profit,
                    sga_expenses=sga,
                    ebitda=ebitda,
                    operating_income=operating_income,
                    net_income=net_income,
                    eps=eps,
                    total_assets=total_assets,
                    total_liabilities=_safe_float(_get(bal_row, '负债合计')) if _has(bal_row) else None,
                    shareholders_equity=_safe_float(_get(bal_row, '归属于母公司所有者权益合计')) if _has(bal_row) else None,
                    cash_and_equivalents=_safe_float(_get(bal_row, '货币资金')) if _has(bal_row) else None,
                    operating_cash_flow=_safe_float(_get(cf_row, '经营活动产生的现金流量净额')) if _has(cf_row) else None,
                    investing_cash_flow=_safe_float(_get(cf_row, '投资活动产生的现金流量净额')) if _has(cf_row) else None,
                    financing_cash_flow=_safe_float(_get(cf_row, '筹资活动产生的现金流量净额')) if _has(cf_row) else None,
                    # 东方财富指标补充的比率
                    gross_margin=gross_margin_pct / 100 if gross_margin_pct else None,
                    operating_margin=operating_margin_pct / 100 if operating_margin_pct else None,
                    net_margin=net_margin_pct / 100 if net_margin_pct else None,
                    roe=roe,
                )

                # 计算 free cash flow
                capex = _safe_float(_get(cf_row, '购建固定资产、无形资产和其他长期资产支付的现金')) if _has(cf_row) else None
                if stmt.operating_cash_flow and capex:
                    stmt.free_cash_flow = stmt.operating_cash_flow - capex
                    stmt.capital_expenditure = capex

                statements.append(stmt)

            return statements

        except Exception as e:
            print(f"  [东方财富] 获取财务报表失败 {ticker}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """从东方财富获取公司信息"""
        import akshare as ak

        ticker = self._normalize_ticker(ticker)

        try:
            info_df = ak.stock_individual_info_em(symbol=ticker)
            time.sleep(REQUEST_INTERVAL)

            info_map = {str(row['item']): row['value'] for _, row in info_df.iterrows()}

            first_digit = ticker[0]
            if first_digit in ('6', '9'):
                exchange = '上交所 (SSE)'
            elif first_digit in ('0', '2', '3'):
                exchange = '深交所 (SZSE)'
            else:
                exchange = '北交所 (BSE)'

            price = _safe_float(info_map.get('最新'))
            market_cap = _safe_float(info_map.get('总市值'))

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
                price=price,
                market_cap=market_cap,
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
                exchange=exchange,
                country='中国',
                currency='CNY',
            )

        except Exception as e:
            print(f"  [东方财富] 获取公司信息失败 {ticker}: {e}")
            return CompanyProfile(ticker=ticker, country='中国', currency='CNY')

    def fetch_news(self, ticker: str, days: int = 30, limit: int = 20) -> List[NewsItem]:
        """东方财富新闻（与 AKShare 适配器共用接口但独立实例）"""
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

                if (datetime.now() - pub_date).days > days:
                    continue

                items.append(NewsItem(
                    date=pub_date,
                    title=str(row.get('新闻标题', '')),
                    content=str(row.get('新闻内容', ''))[:500],
                    source='东方财富',
                    url=str(row.get('新闻链接', '')),
                ))

            return items

        except Exception as e:
            print(f"  [东方财富] 获取新闻失败 {ticker}: {e}")
            return []

    def fetch_technical_indicators(self, ticker: str) -> dict:
        """从东方财富日K数据计算技术指标"""
        import akshare as ak

        ticker = self._normalize_ticker(ticker)

        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')

            hist = ak.stock_zh_a_hist(
                symbol=ticker, period='daily',
                start_date=start_date, end_date=end_date,
                adjust='qfq'
            )
            time.sleep(REQUEST_INTERVAL)

            if hist is None or hist.empty:
                return {}

            close = hist['收盘'].astype(float)
            indicators = {}

            for p in [20, 50, 200]:
                if len(close) >= p:
                    sma = close.rolling(window=p).mean()
                    if not sma.empty and not np.isnan(sma.iloc[-1]):
                        indicators[f'SMA_{p}'] = round(float(sma.iloc[-1]), 2)

            if len(close) >= 14:
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                if not rsi.empty and not np.isnan(rsi.iloc[-1]):
                    indicators['RSI_14'] = round(float(rsi.iloc[-1]), 2)

            if len(close) >= 26:
                ema12 = close.ewm(span=12, adjust=False).mean()
                ema26 = close.ewm(span=26, adjust=False).mean()
                macd_line = ema12 - ema26
                signal = macd_line.ewm(span=9, adjust=False).mean()
                indicators['MACD'] = round(float(macd_line.iloc[-1]), 4)
                indicators['MACD_Signal'] = round(float(signal.iloc[-1]), 4)

            if len(close) >= 200:
                indicators['52W_High'] = round(float(close.tail(252).max()), 2)
                indicators['52W_Low'] = round(float(close.tail(252).min()), 2)

            indicators['Current_Price'] = round(float(close.iloc[-1]), 2)

            if '成交量' in hist.columns:
                vol = hist['成交量'].astype(float)
                indicators['Avg_Volume_20d'] = int(vol.tail(20).mean())

            return indicators

        except Exception as e:
            print(f"  [东方财富] 获取技术指标失败 {ticker}: {e}")
            return {}
