"""
同花顺适配器 — 基于 akshare 的同花顺 (ths/10jqka) 接口，免费 A 股数据源。
与 AKShareAdapter（新浪源）形成双数据源交叉验证。

同花顺数据特点：
1. 数值带中文单位（"亿"、"万"），需要解析
2. 列名带 * 前缀表示核心指标
3. 数据质量高，字段完整
"""
import time
import os
import re
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
    """临时去掉代理环境变量"""
    saved = {}
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        yield
    finally:
        os.environ.update(saved)


def _parse_cn_number(val) -> Optional[float]:
    """解析中文数字：'1709.0亿' → 170900000000.0, '44.79亿' → 4479000000.0"""
    if val is None:
        return None
    s = str(val).strip()
    if s in ('', '--', 'nan', 'None'):
        return None
    try:
        # 去掉逗号
        s = s.replace(',', '')
        if '万亿' in s:
            return float(s.replace('万亿', '')) * 1e12
        elif '亿' in s:
            return float(s.replace('亿', '')) * 1e8
        elif '万' in s:
            return float(s.replace('万', '')) * 1e4
        else:
            return float(s)
    except (ValueError, TypeError):
        return None


def _safe_float(val, default=None):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        v = float(str(val).replace(',', '').replace('--', ''))
        return v if not np.isnan(v) else default
    except (TypeError, ValueError):
        return default


class THSAdapter(DataSourceAdapter):
    """同花顺数据适配器"""

    @property
    def name(self) -> str:
        return "同花顺 (10jqka)"

    def _normalize_ticker(self, ticker: str) -> str:
        ticker = ticker.strip().upper()
        for prefix in ['SH', 'SZ', 'BJ']:
            ticker = ticker.replace(prefix, '')
        ticker = ticker.replace('.', '').strip()
        return ticker.zfill(6)

    def fetch_all(self, ticker: str, period: str = 'annual', limit: int = 5):
        """重写 fetch_all，去掉代理"""
        with no_proxy():
            return super().fetch_all(ticker, period, limit)

    def fetch_financial_statements(
        self, ticker: str, period: str = 'annual', limit: int = 5
    ) -> List[FinancialStatement]:
        """从同花顺获取财务报表"""
        import akshare as ak

        ticker = self._normalize_ticker(ticker)
        statements = []

        try:
            # 利润表
            print(f"  [同花顺] 获取利润表 {ticker}...")
            income_df = ak.stock_financial_benefit_ths(symbol=ticker, indicator='按报告期')
            time.sleep(REQUEST_INTERVAL)

            # 资产负债表
            print(f"  [同花顺] 获取资产负债表 {ticker}...")
            balance_df = ak.stock_financial_debt_ths(symbol=ticker, indicator='按报告期')
            time.sleep(REQUEST_INTERVAL)

            # 现金流量表
            print(f"  [同花顺] 获取现金流量表 {ticker}...")
            cashflow_df = ak.stock_financial_cash_ths(symbol=ticker, indicator='按报告期')
            time.sleep(REQUEST_INTERVAL)

            # 筛选年报
            if period == 'annual':
                income_df = income_df[income_df['报告期'].astype(str).str.endswith('12-31')]
                balance_df = balance_df[balance_df['报告期'].astype(str).str.endswith('12-31')]
                cashflow_df = cashflow_df[cashflow_df['报告期'].astype(str).str.endswith('12-31')]

            income_df = income_df.head(limit).reset_index(drop=True)
            balance_df = balance_df.head(limit).reset_index(drop=True)
            cashflow_df = cashflow_df.head(limit).reset_index(drop=True)

            # 构建索引
            bal_map = {str(row['报告期']): row for _, row in balance_df.iterrows()}
            cf_map = {str(row['报告期']): row for _, row in cashflow_df.iterrows()}

            for _, inc_row in income_df.iterrows():
                report_date = str(inc_row['报告期'])
                year = int(report_date[:4])
                bal_row = bal_map.get(report_date)
                cf_row = cf_map.get(report_date)

                # 利润表数据（同花顺列名）
                revenue = _parse_cn_number(inc_row.get('其中：营业收入')) or _parse_cn_number(inc_row.get('一、营业总收入'))
                cost_of_revenue = _parse_cn_number(inc_row.get('其中：营业成��'))
                gross_profit = (revenue - cost_of_revenue) if revenue and cost_of_revenue else None
                sga = None
                sales_exp = _parse_cn_number(inc_row.get('销售费用'))
                admin_exp = _parse_cn_number(inc_row.get('管理费用'))
                if sales_exp is not None or admin_exp is not None:
                    sga = (sales_exp or 0) + (admin_exp or 0)

                operating_income = _parse_cn_number(inc_row.get('三、营业利润'))
                net_income = _parse_cn_number(inc_row.get('*归属于母公司所有者的净利润')) or _parse_cn_number(inc_row.get('*净利润'))
                eps = _safe_float(inc_row.get('基本每股收益'))

                # EBITDA = 营业利润 + 折旧（从现金流表取）
                ebitda = None
                depreciation = None
                if cf_row is not None:
                    depreciation = _parse_cn_number(cf_row.get('固定资产折旧、油气资产折耗、生产性生物资产折旧'))
                if operating_income is not None:
                    ebitda = operating_income + (depreciation or 0)

                # 资产负债表
                total_assets = _parse_cn_number(bal_row.get('*资产合计')) if bal_row is not None else None
                total_liabilities = _parse_cn_number(bal_row.get('*负债合计')) if bal_row is not None else None
                equity = _parse_cn_number(bal_row.get('*归属于母公司所有者权益合计')) or _parse_cn_number(bal_row.get('*所有者权益（或股东权益）合计')) if bal_row is not None else None
                cash = _parse_cn_number(bal_row.get('货币资金')) if bal_row is not None else None

                # 现金流量表
                ocf = _parse_cn_number(cf_row.get('*经营活动产生的现金流量净额')) if cf_row is not None else None
                icf = _parse_cn_number(cf_row.get('*投资活动产生的现金流量净额')) if cf_row is not None else None
                fcf_val = _parse_cn_number(cf_row.get('*筹资活动产生的现金流量净额')) if cf_row is not None else None
                capex = _parse_cn_number(cf_row.get('购建固定资产、无形资产和其他长期资产支付的现金')) if cf_row is not None else None

                stmt = FinancialStatement(
                    year=year, period=period,
                    revenue=revenue, cost_of_revenue=cost_of_revenue,
                    gross_profit=gross_profit, sga_expenses=sga,
                    ebitda=ebitda, operating_income=operating_income,
                    net_income=net_income, eps=eps,
                    total_assets=total_assets, total_liabilities=total_liabilities,
                    shareholders_equity=equity, cash_and_equivalents=cash,
                    operating_cash_flow=ocf, investing_cash_flow=icf,
                    financing_cash_flow=fcf_val, capital_expenditure=capex,
                )
                if stmt.operating_cash_flow and stmt.capital_expenditure:
                    stmt.free_cash_flow = stmt.operating_cash_flow - stmt.capital_expenditure

                statements.append(stmt)

            return statements

        except Exception as e:
            print(f"  [同花顺] 获取财务报表失败 {ticker}: {e}")
            return []

    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """从同花顺获取公司信息（用 stock_info_global_ths）"""
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
            # 用财务摘要获取基本指标
            abstract_df = ak.stock_financial_abstract_ths(symbol=ticker, indicator='按报告期')
            time.sleep(REQUEST_INTERVAL)

            # 从最新一行提取
            if abstract_df is not None and not abstract_df.empty:
                latest = abstract_df.iloc[0]
                eps = _safe_float(latest.get('基本每股收益'))
                roe_val = latest.get('加权净资产收益率')
                # roe 可能带 %
                roe = None
                if roe_val and str(roe_val) not in ('--', 'nan'):
                    try:
                        roe = float(str(roe_val).replace('%', '')) / 100
                    except:
                        pass

            return CompanyProfile(
                ticker=ticker,
                name='',  # 同花顺没有直接的公司名接口，但新浪的 fetch_all 会补
                sector='', industry='',
                exchange=exchange,
                country='中国', currency='CNY',
            )

        except Exception as e:
            print(f"  [同花顺] 获取公司信息失败 {ticker}: {str(e)[:80]}")
            return CompanyProfile(ticker=ticker, exchange=exchange, country='中国', currency='CNY')

    def fetch_news(self, ticker: str, days: int = 30, limit: int = 20) -> List[NewsItem]:
        """同花顺没有独立新闻接口，返回空"""
        return []

    def fetch_technical_indicators(self, ticker: str) -> dict:
        """同花顺没有日K接口，返回空（可用 AKShare 的新浪源补充）"""
        return {}
