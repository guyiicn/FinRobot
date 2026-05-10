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

    def _fetch_realtime_price(self, ticker: str) -> Optional[float]:
        """从新浪财经获取实时股价（直连，无需代理）"""
        import requests
        first_digit = ticker[0]
        prefix = 'sh' if first_digit in ('6', '9') else 'sz'
        symbol = f"{prefix}{ticker}"
        url = f"https://hq.sinajs.cn/list={symbol}"
        try:
            r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
            # 格式: var hq_str_sz301062="上海艾录,昨收,今开,最高,最低,现价,..."
            content = r.text
            if '="' in content:
                fields = content.split('="')[1].split('"')[0].split(',')
                if len(fields) > 5:
                    price = _safe_float(fields[3])  # index 3 = 当前价/最新价
                    if price and price > 0:
                        return price
        except Exception as e:
            print(f"  [新浪] 获取股价失败 {ticker}: {e}")
        return None

    def _fetch_valuation(self, ticker: str) -> dict:
        """
        从同花顺财务摘要 + 新浪实时股价计算 PE/PB/市值。
        返回 dict: price, eps, nav_per_share, pe_ratio, pb_ratio, market_cap, net_income, revenue
        """
        import akshare as ak
        result = {}
        try:
            abstract_df = ak.stock_financial_abstract_ths(symbol=ticker, indicator='按年度')
            time.sleep(REQUEST_INTERVAL)
            if abstract_df is None or abstract_df.empty:
                return result

            # 优先取2024年，否则取最新
            row_2024 = abstract_df[abstract_df['报告期'].astype(str).str.contains('2024')]
            row = row_2024.iloc[0] if not row_2024.empty else abstract_df.iloc[0]

            eps = _safe_float(row.get('基本每股收益'))
            nav = _parse_cn_number(row.get('每股净资产'))
            revenue = _parse_cn_number(row.get('营业总收入'))
            net_income = _parse_cn_number(row.get('净利润'))

            result['eps'] = eps
            result['nav_per_share'] = nav
            result['revenue'] = revenue
            result['net_income'] = net_income

            # 实时股价
            price = self._fetch_realtime_price(ticker)
            if price:
                result['price'] = price
                if eps and eps > 0:
                    result['pe_ratio'] = round(price / eps, 2)
                elif eps and eps <= 0:
                    result['pe_ratio'] = None  # 亏损，PE无意义
                if nav and nav > 0:
                    result['pb_ratio'] = round(price / nav, 2)
        except Exception as e:
            print(f"  [THS估值] {ticker} 失败: {str(e)[:80]}")
        return result

    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """从同花顺获取公司信息，含 PE/PB/市值"""
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
            val = self._fetch_valuation(ticker)
            price     = val.get('price')
            pe_ratio  = val.get('pe_ratio')
            pb_ratio  = val.get('pb_ratio')

            # 市值 = 股价 × 总股本（用净利润/EPS 估算总股本）
            market_cap = None
            eps = val.get('eps')
            net_income = val.get('net_income')
            if price and eps and eps > 0 and net_income:
                total_shares = net_income / eps
                market_cap = price * total_shares

            print(f"  [THS估值] {ticker}: 价格={price} PE={pe_ratio} PB={pb_ratio} 市值={round(market_cap/1e8,1) if market_cap else 'N/A'}亿")

            return CompanyProfile(
                ticker=ticker,
                name='',
                sector='', industry='',
                exchange=exchange,
                country='中国', currency='CNY',
                price=price,
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
                market_cap=market_cap,
            )

        except Exception as e:
            print(f"  [同花顺] 获取公司信息失败 {ticker}: {str(e)[:80]}")
            return CompanyProfile(ticker=ticker, exchange=exchange, country='中国', currency='CNY')

    def fetch_comparables(self, peer_tickers: list) -> list:
        """
        批量采集同行估值数据，供 comparables table 使用。
        返回 list of dict，每项包含 ticker/name/price/PE/PB/市值/营收/净利润/净利率
        """
        with no_proxy():
            return self._fetch_comparables_impl(peer_tickers)

    def _fetch_comparables_impl(self, peer_tickers: list, years: int = 3) -> list:
        """
        批量采集同行估值 + 历史财务数据。
        每家公司返回:
          - 实时估值: price/pe_ratio/pb_ratio/market_cap
          - 最新年度: revenue/net_income/net_margin/gross_margin/roe/asset_liability_ratio/eps_cfs
          - 历史3年: history=[{year, revenue, net_income, net_margin, gross_margin, roe, ...}, ...]
        """
        import akshare as ak
        results = []
        for raw_ticker in peer_tickers:
            ticker = self._normalize_ticker(raw_ticker)
            rec = {'ticker': ticker}
            try:
                # --- 1. 实时估值 ---
                val = self._fetch_valuation(ticker)
                rec.update({
                    'price':          val.get('price'),
                    'pe_ratio':       val.get('pe_ratio'),
                    'pb_ratio':       val.get('pb_ratio'),
                    'eps':            val.get('eps'),
                    'nav_per_share':  val.get('nav_per_share'),
                    'market_cap':     None,  # 下面补
                })
                # 市值估算
                price = val.get('price')
                eps   = val.get('eps')
                net_inc_latest = val.get('net_income')
                if price and eps and eps > 0 and net_inc_latest:
                    rec['market_cap'] = price * (net_inc_latest / eps)
                time.sleep(REQUEST_INTERVAL)

                # --- 2. 历史财务数据（同花顺年度摘要）---
                df = ak.stock_financial_abstract_ths(symbol=ticker, indicator='按年度')
                # 字段（已确认存在）:
                #   报告期, 净利润, 营业总收入, 销售毛利率, 销售净利率,
                #   净资产收益率, 资产负债率, 每股经营现金流, 基本每股收益
                df['_year'] = df['报告期'].astype(str).str[:4].astype(int, errors='ignore')
                df = df.sort_values('_year', ascending=False).head(years)

                def pct(s):
                    """'20.84%' → 20.84"""
                    if s is None: return None
                    try: return float(str(s).replace('%','').replace('--','').strip())
                    except: return None
                def cn_num(s):
                    """'3.5亿' → 3.5e8"""
                    if s is None: return None
                    s = str(s).strip()
                    try:
                        if '亿' in s: return float(s.replace('亿','')) * 1e8
                        if '万' in s: return float(s.replace('万','')) * 1e4
                        return float(s)
                    except: return None

                history = []
                for _, row in df.iterrows():
                    yr = str(row.get('报告期', ''))[:4]
                    rev = cn_num(row.get('营业总收入'))
                    ni  = cn_num(row.get('净利润'))
                    history.append({
                        'year':         yr,
                        'revenue':      rev,
                        'net_income':   ni,
                        'gross_margin': pct(row.get('销售毛利率')),
                        'net_margin':   pct(row.get('销售净利率')),
                        'roe':          pct(row.get('净资产收益率')),
                        'asset_liability_ratio': pct(row.get('资产负债率')),
                        'eps_cfs':      _safe_float(row.get('每股经营现金流')),
                        'revenue_growth': pct(row.get('营业总收入同比增长率')),
                        'net_income_growth': pct(row.get('净利润同比增长率')),
                    })

                rec['history'] = history
                # 最新一年数据也放在顶层（方便快速访问）
                if history:
                    latest = history[0]
                    rec['revenue']   = latest['revenue']
                    rec['net_income'] = latest['net_income']
                    rec['net_margin'] = latest['net_margin']
                    rec['gross_margin'] = latest['gross_margin']
                    rec['roe']       = latest['roe']
                    rec['asset_liability_ratio'] = latest['asset_liability_ratio']
                    rec['eps_cfs']   = latest['eps_cfs']
                    rec['revenue_growth'] = latest['revenue_growth']
                    rec['net_income_growth'] = latest['net_income_growth']

                time.sleep(REQUEST_INTERVAL)
                print(f"  [comparables] {ticker}: PE={rec.get('pe_ratio')} 毛利率={rec.get('gross_margin')}% ROE={rec.get('roe')}%")

            except Exception as e:
                print(f"  [fetch_comparables] {ticker} 失败: {e}")
                rec['error'] = str(e)

            results.append(rec)
        return results

    def fetch_auto_peers(self, ticker: str, top_n: int = 4) -> List[str]:
        """
        自动从东财行业分类找同行，按市值与 ticker 最接近的 top_n 家。
        返回 ticker 列表（不含自身）。
        """
        with no_proxy():
            return self._fetch_auto_peers_impl(ticker, top_n)

    def _fetch_auto_peers_impl(self, ticker: str, top_n: int = 4) -> List[str]:
        import akshare as ak
        ticker = self._normalize_ticker(ticker)
        try:
            # 1. 获取标的所属行业
            info_df = ak.stock_individual_info_em(symbol=ticker)
            # info_df 格式: item/value 两列
            info = dict(zip(info_df.iloc[:, 0], info_df.iloc[:, 1]))
            industry = info.get('行业') or info.get('所属行业') or info.get('所属板块')
            if not industry:
                print(f"  [自动同行] 无法获取 {ticker} 行业信息")
                return []
            print(f"  [自动同行] {ticker} 所属行业: {industry}")

            # 2. 获取同行业成分股
            industry_df = ak.stock_board_industry_cons_em(symbol=industry)
            # 列: 代码/名称/最新价/涨跌幅/...
            if '总市值' not in industry_df.columns:
                # 补充市值：用现价×总股本粗估，或直接用相对排序
                all_tickers = industry_df['代码'].astype(str).tolist()
            else:
                all_tickers = industry_df['代码'].astype(str).tolist()

            # 3. 获取标的市值
            main_val = self._fetch_valuation(ticker)
            main_mktcap = main_val.get('market_cap') or 0
            time.sleep(REQUEST_INTERVAL)

            # 4. 对同行业成分股算市值，找最近的 top_n 家
            peer_caps = []
            sample = [t for t in all_tickers if t != ticker][:30]  # 最多采样30家
            for pt in sample:
                try:
                    val = self._fetch_valuation(pt)
                    cap = val.get('market_cap') or 0
                    if cap > 0:
                        peer_caps.append((pt, cap, abs(cap - main_mktcap)))
                    time.sleep(0.5)
                except:
                    continue

            # 按市值差排序，取最近的 top_n
            peer_caps.sort(key=lambda x: x[2])
            result = [p[0] for p in peer_caps[:top_n]]
            print(f"  [自动同行] 找到 {len(result)} 家: {result}")
            return result

        except Exception as e:
            print(f"  [自动同行] 失败: {str(e)[:100]}")
            return []

    def fetch_news(self, ticker: str, days: int = 30, limit: int = 20) -> List[NewsItem]:
        """从东财获取个股新闻，优先返回与公司直接相关的条目。
        注意：fetch_all 已套 no_proxy()，单独调用时此方法本身也无需代理（东财直连可用）。
        策略：
        1. 拉取东财全部新闻（最多10条）
        2. 优先筛选标题含 ticker 或公司名的
        3. 不足 limit 条时补充行业新闻
        4. 最终返回不超过 limit 条
        """
        import akshare as ak
        ticker = self._normalize_ticker(ticker)
        items: List[NewsItem] = []
        try:
            df = ak.stock_news_em(symbol=ticker)
            time.sleep(REQUEST_INTERVAL)
            if df is None or df.empty:
                return items

            # 优先：标题含 ticker 的（真正个股新闻）
            direct = df[df['新闻标题'].str.contains(ticker, na=False)]
            others = df[~df['新闻标题'].str.contains(ticker, na=False)]
            ordered = pd.concat([direct, others]).head(limit)

            for _, row in ordered.iterrows():
                try:
                    pub_time = pd.to_datetime(row.get('发布时间'))
                except:
                    pub_time = datetime.now()
                items.append(NewsItem(
                    date=pub_time,
                    title=str(row.get('新闻标题', '')),
                    content=str(row.get('新闻内容', ''))[:500],
                    source=str(row.get('文章来源', '东方财富')),
                    url=str(row.get('新闻链接', '')),
                ))
            print(f"  [新闻] {ticker}: 获取 {len(items)} 条（直接相关 {len(direct)} 条）")
        except Exception as e:
            print(f"  [新闻] {ticker} 获取失败: {str(e)[:80]}")
        return items

    def fetch_technical_indicators(self, ticker: str) -> dict:
        """同花顺没有日K接口，返回空（可用 AKShare 的新浪源补充）"""
        return {}
