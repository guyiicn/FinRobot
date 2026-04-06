"""
加密货币数据适配器 — 基于 CCXT (Bybit) + CoinGecko + CryptoCompare。

数据源分工:
- CCXT/Bybit: K线(OHLCV)、实时行情、24h成交量
- CoinGecko: 市值、供应量、代币经济学、排名、历史数据
- CryptoCompare: 新闻（可选）
- DeFiLlama: DeFi TVL（可选）

Ticker 格式: BTC, ETH, SOL (大写符号，不含 /USDT)
"""
import time
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from .base import DataSourceAdapter
from .models import FinancialStatement, CompanyProfile, NewsItem

REQUEST_INTERVAL = 0.5

# 常见加密货币 → CoinGecko ID 映射
COINGECKO_IDS = {
    'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana',
    'BNB': 'binancecoin', 'XRP': 'ripple', 'ADA': 'cardano',
    'DOGE': 'dogecoin', 'DOT': 'polkadot', 'AVAX': 'avalanche-2',
    'MATIC': 'matic-network', 'LINK': 'chainlink', 'UNI': 'uniswap',
    'ATOM': 'cosmos', 'LTC': 'litecoin', 'ETC': 'ethereum-classic',
    'FIL': 'filecoin', 'APT': 'aptos', 'ARB': 'arbitrum',
    'OP': 'optimism', 'NEAR': 'near', 'AAVE': 'aave',
    'MKR': 'maker', 'SNX': 'havven', 'CRV': 'curve-dao-token',
    'SUSHI': 'sushi', 'COMP': 'compound-governance-token',
    'SUI': 'sui', 'SEI': 'sei-network', 'TIA': 'celestia',
    'JUP': 'jupiter-exchange-solana', 'PEPE': 'pepe',
    'SHIB': 'shiba-inu', 'WIF': 'dogwifcoin',
}


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        v = float(val)
        return v if not np.isnan(v) else default
    except (TypeError, ValueError):
        return default


class CryptoAdapter(DataSourceAdapter):
    """加密货币数据适配器"""

    def __init__(self, exchange_id: str = 'bybit'):
        self._exchange_id = exchange_id
        self._exchange = None
        self._cg = None

    @property
    def name(self) -> str:
        return f"Crypto ({self._exchange_id.capitalize()} + CoinGecko)"

    def _get_exchange(self):
        if self._exchange is None:
            import ccxt
            self._exchange = getattr(ccxt, self._exchange_id)({
                'enableRateLimit': True,
            })
        return self._exchange

    def _get_coingecko(self):
        if self._cg is None:
            from pycoingecko import CoinGeckoAPI
            self._cg = CoinGeckoAPI()
        return self._cg

    def _normalize_ticker(self, ticker: str) -> str:
        return ticker.upper().replace('/USDT', '').replace('-USD', '').strip()

    def _to_trading_pair(self, ticker: str) -> str:
        t = self._normalize_ticker(ticker)
        return f"{t}/USDT"

    def _to_coingecko_id(self, ticker: str) -> str:
        t = self._normalize_ticker(ticker)
        return COINGECKO_IDS.get(t, t.lower())

    # ── OHLCV K线 (CCXT) ──

    def fetch_ohlcv(self, ticker: str, timeframe: str = '1d', limit: int = 365) -> pd.DataFrame:
        """获取 K 线数据，返回标准 OHLCV DataFrame。"""
        ex = self._get_exchange()
        pair = self._to_trading_pair(ticker)

        try:
            bars = ex.fetch_ohlcv(pair, timeframe, limit=limit)
            df = pd.DataFrame(bars, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('date', inplace=True)
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
            df['OpenInterest'] = 0
            return df
        except Exception as e:
            print(f"  [Crypto] OHLCV 失败 {pair}: {e}")
            return pd.DataFrame()

    # ── 基本面 (CoinGecko) ──

    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """获取加密货币基本信息"""
        cg = self._get_coingecko()
        coin_id = self._to_coingecko_id(ticker)
        t = self._normalize_ticker(ticker)

        try:
            data = cg.get_coin_by_id(coin_id, localization=False,
                                      tickers=False, community_data=False,
                                      developer_data=False)
            time.sleep(REQUEST_INTERVAL)

            md = data.get('market_data', {})
            price = _safe_float(md.get('current_price', {}).get('usd'))
            market_cap = _safe_float(md.get('market_cap', {}).get('usd'))
            volume = _safe_float(md.get('total_volume', {}).get('usd'))

            desc = data.get('description', {}).get('en', '')
            if desc and len(desc) > 500:
                desc = desc[:500] + '...'

            return CompanyProfile(
                ticker=t,
                name=data.get('name', t),
                sector='Cryptocurrency',
                industry=', '.join(data.get('categories', [])[:3]),
                description=desc,
                price=price,
                market_cap=market_cap,
                volume=volume,
                pe_ratio=None,
                pb_ratio=None,
                exchange=self._exchange_id.capitalize(),
                country='Global',
                currency='USD',
            )
        except Exception as e:
            print(f"  [Crypto] Profile 失败 {coin_id}: {e}")
            return CompanyProfile(ticker=t, name=t, sector='Cryptocurrency',
                                  exchange=self._exchange_id.capitalize(),
                                  country='Global', currency='USD')

    def fetch_coin_metrics(self, ticker: str) -> Dict:
        """获取加密货币核心指标（替代传统财务报表）"""
        cg = self._get_coingecko()
        coin_id = self._to_coingecko_id(ticker)

        try:
            data = cg.get_coin_by_id(coin_id, localization=False,
                                      tickers=False, community_data=True,
                                      developer_data=True)
            time.sleep(REQUEST_INTERVAL)

            md = data.get('market_data', {})

            metrics = {
                # 价格与市值
                'price_usd': _safe_float(md.get('current_price', {}).get('usd')),
                'market_cap': _safe_float(md.get('market_cap', {}).get('usd')),
                'market_cap_rank': data.get('market_cap_rank'),
                'total_volume_24h': _safe_float(md.get('total_volume', {}).get('usd')),
                'fdv': _safe_float(md.get('fully_diluted_valuation', {}).get('usd')),

                # 供应量
                'circulating_supply': _safe_float(md.get('circulating_supply')),
                'total_supply': _safe_float(md.get('total_supply')),
                'max_supply': _safe_float(md.get('max_supply')),

                # 涨跌幅
                'change_24h': _safe_float(md.get('price_change_percentage_24h')),
                'change_7d': _safe_float(md.get('price_change_percentage_7d')),
                'change_30d': _safe_float(md.get('price_change_percentage_30d')),
                'change_1y': _safe_float(md.get('price_change_percentage_1y')),

                # 历史极值
                'ath': _safe_float(md.get('ath', {}).get('usd')),
                'ath_change_pct': _safe_float(md.get('ath_change_percentage', {}).get('usd')),
                'atl': _safe_float(md.get('atl', {}).get('usd')),

                # 社区数据
                'twitter_followers': data.get('community_data', {}).get('twitter_followers'),
                'reddit_subscribers': data.get('community_data', {}).get('reddit_subscribers'),

                # 开发数据
                'github_stars': data.get('developer_data', {}).get('stars'),
                'github_forks': data.get('developer_data', {}).get('forks'),
            }

            # 计算衍生指标
            if metrics['market_cap'] and metrics['total_volume_24h'] and metrics['total_volume_24h'] > 0:
                metrics['volume_to_mcap'] = round(metrics['total_volume_24h'] / metrics['market_cap'] * 100, 2)

            if metrics['circulating_supply'] and metrics['total_supply'] and metrics['total_supply'] > 0:
                metrics['circulation_ratio'] = round(metrics['circulating_supply'] / metrics['total_supply'] * 100, 2)

            return metrics
        except Exception as e:
            print(f"  [Crypto] Metrics 失败 {coin_id}: {e}")
            return {}

    # ── DeFi TVL (DeFiLlama, 可选) ──

    def fetch_defi_tvl(self, protocol: str) -> Dict:
        """获取 DeFi 协议 TVL（通过 DeFiLlama 免费 API）"""
        try:
            import requests
            resp = requests.get(f'https://api.llama.fi/protocol/{protocol}', timeout=10)
            if resp.ok:
                data = resp.json()
                return {
                    'name': data.get('name'),
                    'tvl': _safe_float(data.get('tvl')),
                    'chain_tvls': {k: v for k, v in data.get('chainTvls', {}).items()
                                   if isinstance(v, (int, float))},
                    'category': data.get('category'),
                    'chains': data.get('chains', []),
                }
        except Exception as e:
            print(f"  [DeFiLlama] TVL 失败 {protocol}: {e}")
        return {}

    # ── 新闻 (CryptoCompare) ──

    def fetch_news(self, ticker: str, days: int = 7, limit: int = 10) -> List[NewsItem]:
        """获取加密货币新闻"""
        t = self._normalize_ticker(ticker)

        try:
            import requests
            # CryptoCompare 免费新闻 API
            resp = requests.get(
                'https://min-api.cryptocompare.com/data/v2/news/',
                params={'categories': t, 'extraParams': 'FinRobot'},
                timeout=10,
            )
            if resp.ok:
                articles = resp.json().get('Data', [])[:limit]
                news = []
                for a in articles:
                    news.append(NewsItem(
                        title=a.get('title', ''),
                        date=datetime.fromtimestamp(a.get('published_on', 0)).strftime('%Y-%m-%d'),
                        source=a.get('source', ''),
                        url=a.get('url', ''),
                        content=a.get('body', '')[:300],
                    ))
                return news
        except Exception as e:
            print(f"  [CryptoCompare] 新闻失败 {t}: {e}")

        return []

    # ── 标准接口（兼容 DataSourceAdapter）──

    def fetch_financial_statements(self, ticker: str, period: str = 'annual',
                                    limit: int = 5) -> List[FinancialStatement]:
        """加密货币没有传统财报，返回基于历史市值/成交量的"报表"。"""
        cg = self._get_coingecko()
        coin_id = self._to_coingecko_id(ticker)

        try:
            # 获取过去几年的市场数据
            market_chart = cg.get_coin_market_chart_by_id(
                coin_id, vs_currency='usd', days=365 * limit
            )
            time.sleep(REQUEST_INTERVAL)

            # 按年聚合
            prices = market_chart.get('prices', [])
            volumes = market_chart.get('total_volumes', [])
            caps = market_chart.get('market_caps', [])

            if not prices:
                return []

            df = pd.DataFrame(prices, columns=['timestamp', 'price'])
            df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['year'] = df['date'].dt.year

            vol_df = pd.DataFrame(volumes, columns=['timestamp', 'volume'])
            vol_df['date'] = pd.to_datetime(vol_df['timestamp'], unit='ms')
            vol_df['year'] = vol_df['date'].dt.year

            cap_df = pd.DataFrame(caps, columns=['timestamp', 'mcap'])
            cap_df['date'] = pd.to_datetime(cap_df['timestamp'], unit='ms')
            cap_df['year'] = cap_df['date'].dt.year

            statements = []
            for year in sorted(df['year'].unique())[-limit:]:
                yr_prices = df[df['year'] == year]['price']
                yr_vols = vol_df[vol_df['year'] == year]['volume']
                yr_caps = cap_df[cap_df['year'] == year]['mcap']

                avg_price = yr_prices.mean()
                year_open = yr_prices.iloc[0]
                year_close = yr_prices.iloc[-1]
                year_return = (year_close - year_open) / year_open * 100

                stmt = FinancialStatement(
                    year=year, period='annual',
                    revenue=yr_vols.sum(),          # "营收" = 年总成交量
                    net_income=None,
                    ebitda=yr_caps.mean(),           # "EBITDA" = 平均市值
                    eps=avg_price,                   # "EPS" = 平均价格
                )
                statements.append(stmt)

            return statements
        except Exception as e:
            print(f"  [Crypto] 历史数据失败 {coin_id}: {e}")
            return []

    def fetch_technical_indicators(self, ticker: str) -> dict:
        """从 K 线数据计算技术指标"""
        df = self.fetch_ohlcv(ticker, '1d', 252)
        if df.empty:
            return {}

        close = df['Close']
        indicators = {}

        # SMA
        for p in [20, 50, 200]:
            if len(close) >= p:
                indicators[f'SMA_{p}'] = round(float(close.rolling(p).mean().iloc[-1]), 2)

        # RSI
        if len(close) >= 14:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            indicators['RSI_14'] = round(float(rsi.iloc[-1]), 2)

        # 52W H/L
        indicators['52W_High'] = round(float(close.max()), 2)
        indicators['52W_Low'] = round(float(close.min()), 2)
        indicators['Current_Price'] = round(float(close.iloc[-1]), 2)

        return indicators
