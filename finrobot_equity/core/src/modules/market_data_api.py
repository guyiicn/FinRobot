#!/usr/bin/env python
# coding: utf-8

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

def fetch_yfinance_volume(ticker: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Fetches historical trading volume data using yfinance."""
    try:
        stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        if stock_data.empty:
            print(f"No data returned from yfinance for {ticker} between {start_date} and {end_date}")
            return None
        stock_data = stock_data[["Volume"]]
        stock_data.reset_index(inplace=True)
        stock_data["Date"] = pd.to_datetime(stock_data["Date"])
        return stock_data
    except Exception as e:
        print(f"Error fetching yfinance volume for {ticker}: {e}")
        return None

def get_yfinance_income_statement(ticker: str, period: str = "annual", limit: int = 5) -> pd.DataFrame | None:
    """Fetches income statement data from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        if period == "annual":
            df = stock.financials
        else:
            df = stock.quarterly_financials
        
        if df is None or df.empty:
            print(f"No income statement data from Yahoo Finance for {ticker}.")
            return None
        
        # Transpose to get years as rows
        df = df.T
        df.index.name = 'date'
        df = df.reset_index()
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        
        # Limit to most recent years
        df = df.sort_values('date', ascending=False).head(limit).reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error fetching Yahoo Finance income statement for {ticker}: {e}")
        return None

def get_yfinance_balance_sheet(ticker: str, period: str = "annual", limit: int = 5) -> pd.DataFrame | None:
    """Fetches balance sheet data from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        if period == "annual":
            df = stock.balance_sheet
        else:
            df = stock.quarterly_balance_sheet
        
        if df is None or df.empty:
            print(f"No balance sheet data from Yahoo Finance for {ticker}.")
            return None
        
        # Transpose to get years as rows
        df = df.T
        df.index.name = 'date'
        df = df.reset_index()
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        
        # Limit to most recent years
        df = df.sort_values('date', ascending=False).head(limit).reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error fetching Yahoo Finance balance sheet for {ticker}: {e}")
        return None

def get_yfinance_cash_flow_statement(ticker: str, period: str = "annual", limit: int = 5) -> pd.DataFrame | None:
    """Fetches cash flow statement data from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        if period == "annual":
            df = stock.cashflow
        else:
            df = stock.quarterly_cashflow
        
        if df is None or df.empty:
            print(f"No cash flow data from Yahoo Finance for {ticker}.")
            return None
        
        # Transpose to get years as rows
        df = df.T
        df.index.name = 'date'
        df = df.reset_index()
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        
        # Limit to most recent years
        df = df.sort_values('date', ascending=False).head(limit).reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error fetching Yahoo Finance cash flow for {ticker}: {e}")
        return None

def get_yfinance_ratios_and_key_metrics(ticker: str, period: str = "annual", limit: int = 5) -> Tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Fetches financial ratios and key metrics from Yahoo Finance."""
    ratios_df, key_metrics_df = None, None
    try:
        stock = yf.Ticker(ticker)
        
        # Get financial metrics from info
        info = stock.info
        if info is None:
            print(f"No info data from Yahoo Finance for {ticker}.")
            return None, None
        
        # Create ratios DataFrame (limited data available in yfinance)
        ratios_data = {
            'date': [datetime.now()],
            'year': [datetime.now().year],
            'priceEarningsRatio': [info.get('forwardPE')],
            'priceToBookRatio': [info.get('priceToBook')],
            'returnOnEquity': [info.get('returnOnEquity')],
            'debtEquityRatio': [info.get('debtToEquity')],
            'currentRatio': [info.get('currentRatio')],
            'quickRatio': [info.get('quickRatio')]
        }
        ratios_df = pd.DataFrame(ratios_data)
        
        # Create key metrics DataFrame
        key_metrics_data = {
            'date': [datetime.now()],
            'year': [datetime.now().year],
            'peRatio': [info.get('forwardPE')],
            'pbRatio': [info.get('priceToBook')],
            'enterpriseValue': [info.get('enterpriseValue')],
            'marketCap': [info.get('marketCap')],
            'revenueGrowth': [info.get('revenueGrowth')],
            'earningsGrowth': [info.get('earningsGrowth')]
        }
        key_metrics_df = pd.DataFrame(key_metrics_data)
        
    except Exception as e:
        print(f"Error fetching Yahoo Finance ratios/key metrics for {ticker}: {e}")
        
    return ratios_df, key_metrics_df

def get_comprehensive_financial_data(ticker: str, api_key: str = None, period: str = "annual", limit: int = 5) -> dict:
    """Fetches all three financial statements for a company using Yahoo Finance."""
    print(f"Fetching comprehensive financial data for {ticker}...")
    
    financial_data = {
        'income_statement': get_yfinance_income_statement(ticker, period, limit),
        'balance_sheet': get_yfinance_balance_sheet(ticker, period, limit),
        'cash_flow': get_yfinance_cash_flow_statement(ticker, period, limit),
        'ratios': None,
        'key_metrics': None
    }
    
    # Also get ratios and key metrics
    ratios_df, key_metrics_df = get_yfinance_ratios_and_key_metrics(ticker, period, limit)
    financial_data['ratios'] = ratios_df
    financial_data['key_metrics'] = key_metrics_df
    
    return financial_data

def get_yfinance_current_price(ticker: str, api_key: str = None) -> float | None:
    """Fetches the latest stock price from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if info:
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            if price:
                return float(price)
        
        # Fallback to historical data
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
            
        return None
    except Exception as e:
        print(f"Error fetching Yahoo Finance current price for {ticker}: {e}")
        return None

def get_yfinance_company_profile(ticker: str, api_key: str = None) -> dict | None:
    """Fetches comprehensive company profile data from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if info is None:
            print(f"No profile data returned for {ticker}")
            return None
        
        profile = {
            'symbol': ticker,
            'price': info.get('currentPrice'),
            'marketCap': info.get('marketCap'),
            'beta': info.get('beta'),
            'lastDiv': info.get('lastDividendValue'),
            'volAvg': info.get('averageVolume'),
            'companyName': info.get('longName') or info.get('shortName'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'website': info.get('website'),
            'description': info.get('longBusinessSummary'),
            'ceo': info.get('fullTimeEmployees'),  # yfinance doesn't have CEO directly
            'country': info.get('country'),
            'fullTimeEmployees': info.get('fullTimeEmployees'),
            'exchange': info.get('exchange'),
            '52w_range': f"{info.get('fiftyTwoWeekLow')}-{info.get('fiftyTwoWeekHigh')}" if info.get('fiftyTwoWeekLow') and info.get('fiftyTwoWeekHigh') else None,
            'sharesOutstanding': info.get('sharesOutstanding'),
            'ipoDate': info.get('ipoDate')
        }
        return profile
    except Exception as e:
        print(f"Error fetching company profile for {ticker}: {e}")
        return None

def get_analyst_insights(ticker: str, api_key: str = None) -> Tuple[str | None, float | None]:
    """
    Fetches analyst rating and target price using Yahoo Finance.
    
    Args:
        ticker: Stock ticker symbol
        api_key: Not used for Yahoo Finance (kept for compatibility)
    
    Returns:
        Tuple of (rating, target_price)
    """
    rating = None
    target_price = None
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if info:
            # Get target price
            target_price = info.get('targetMeanPrice')
            if target_price:
                target_price = float(target_price)
            
            # Get analyst recommendation (1=Strong Buy, 5=Sell)
            recommendation = info.get('recommendationKey')
            if recommendation:
                rating = str(recommendation).title()
            
            if rating:
                print(f"[INFO] For {ticker} - Rating: {rating}")
            if target_price:
                print(f"[INFO] For {ticker} - Target Price: {target_price}")
            
    except Exception as e:
        print(f"[ERROR] Error in get_analyst_insights for {ticker}: {e}")
        
    return rating, target_price

def get_yfinance_target_price(ticker: str, api_key: str = None) -> float | None:
    """Fetches the latest analyst target price from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if info:
            target_price = info.get('targetMeanPrice')
            if target_price:
                return float(target_price)
        return None
    except Exception as e:
        print(f"Error fetching Yahoo Finance target price for {ticker}: {e}")
        return None

def get_yfinance_analyst_rating(ticker: str, api_key: str = None) -> str | None:
    """Fetches the latest analyst rating from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if info:
            recommendation = info.get('recommendationKey')
            if recommendation:
                return str(recommendation).title()
        return None
    except Exception as e:
        print(f"Error fetching Yahoo Finance analyst rating for {ticker}: {e}")
        return None

def get_yfinance_market_cap(ticker: str, api_key: str = None) -> float | None:
    """Fetches current market capitalization from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if info:
            market_cap = info.get('marketCap')
            if market_cap:
                return float(market_cap)
        return None
    except Exception as e:
        print(f"Error fetching market cap for {ticker}: {e}")
        return None

def get_comprehensive_company_metrics(ticker: str, api_key: str = None) -> dict:
    """Fetches all key company metrics needed for equity report from Yahoo Finance."""
    print(f"Fetching comprehensive company metrics for {ticker}...")
    
    metrics = {
        'share_price': None,
        'target_price': None,
        'market_cap': None,
        'volume': None,
        'fwd_pe': None,
        'pb_ratio': None,
        'dividend_yield': None,
        'free_float': None,
        'roe': None,
        'net_debt_to_equity': None,
        'rating': None,
        'beta': None,
        'sector': None,
        'industry': None,
        'exchange': None,
        '52w_range': None,
        'shares_outstanding': None,
    }
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if info is None:
            print(f"No info data from Yahoo Finance for {ticker}.")
            return metrics
        
        # 1. Current price
        metrics['share_price'] = info.get('currentPrice') or info.get('regularMarketPrice')
        
        # 2. Target price and rating
        metrics['target_price'] = info.get('targetMeanPrice')
        metrics['rating'] = str(info.get('recommendationKey')).title() if info.get('recommendationKey') else None
        
        # 3. Market cap and volume
        metrics['market_cap'] = info.get('marketCap')
        metrics['volume'] = info.get('averageVolume')
        
        # 4. Ratios
        metrics['fwd_pe'] = info.get('forwardPE')
        metrics['pb_ratio'] = info.get('priceToBook')
        metrics['roe'] = info.get('returnOnEquity')
        metrics['net_debt_to_equity'] = info.get('debtToEquity')
        
        # 5. Sector and industry
        metrics['beta'] = info.get('beta')
        metrics['sector'] = info.get('sector')
        metrics['industry'] = info.get('industry')
        metrics['exchange'] = info.get('exchange')
        
        # 6. 52-week range
        low = info.get('fiftyTwoWeekLow')
        high = info.get('fiftyTwoWeekHigh')
        if low and high:
            metrics['52w_range'] = f"${low:.2f} - ${high:.2f}"
        
        # 7. Shares outstanding
        metrics['shares_outstanding'] = info.get('sharesOutstanding')
        
        # 8. Dividend yield
        if metrics['share_price'] and info.get('dividendYield'):
            metrics['dividend_yield'] = info.get('dividendYield') * 100
        
        # 9. Free float (default estimate)
        metrics['free_float'] = 95.0
        
        # Fill in defaults
        if metrics['free_float'] is None:
            metrics['free_float'] = 95.0
        if metrics['sector'] is None:
            metrics['sector'] = 'Technology'
        if metrics['rating'] is None:
            metrics['rating'] = 'N/A'
        
        print(f"Successfully fetched metrics for {ticker}")
        
    except Exception as e:
        print(f"Warning: Could not fetch company metrics: {e}")
    
    return metrics

def get_technical_indicators(ticker: str, api_key: str = None) -> dict:
    """从 Yahoo Finance 获取历史价格并计算 SMA50/200、RSI14、MACD、成交量信号。"""
    result = {
        'sma50': None, 'sma200': None, 'rsi14': None,
        'macd': None, 'macd_signal': None, 'macd_histogram': None,
        'avg_volume_20d': None, 'latest_volume': None,
        'price': None,
        'ma_signal': 'N/A', 'rsi_signal': 'N/A',
        'macd_signal_label': 'N/A', 'volume_signal': 'N/A',
        'overall_signal': 'N/A',
    }
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        
        if df is None or df.empty or len(df) < 50:
            return result

        close = df['Close'].astype(float)
        volume = df['Volume'].astype(float)

        result['price'] = close.iloc[-1]

        # SMA
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        result['sma50'] = round(sma50, 2)
        if sma200 is not None:
            result['sma200'] = round(sma200, 2)

        # MA signal
        price = close.iloc[-1]
        if sma200 is not None:
            if price > sma50 > sma200:
                result['ma_signal'] = 'Bullish'
            elif price < sma50 < sma200:
                result['ma_signal'] = 'Bearish'
            elif price > sma200:
                result['ma_signal'] = 'Neutral-Bullish'
            else:
                result['ma_signal'] = 'Neutral-Bearish'
        elif price > sma50:
            result['ma_signal'] = 'Bullish'
        else:
            result['ma_signal'] = 'Bearish'

        # RSI 14
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        result['rsi14'] = round(rsi_val, 1)
        if rsi_val > 70:
            result['rsi_signal'] = 'Overbought'
        elif rsi_val < 30:
            result['rsi_signal'] = 'Oversold'
        elif rsi_val > 55:
            result['rsi_signal'] = 'Bullish'
        elif rsi_val < 45:
            result['rsi_signal'] = 'Bearish'
        else:
            result['rsi_signal'] = 'Neutral'

        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        histogram = macd_line - signal_line
        result['macd'] = round(macd_line.iloc[-1], 2)
        result['macd_signal'] = round(signal_line.iloc[-1], 2)
        result['macd_histogram'] = round(histogram.iloc[-1], 2)
        if macd_line.iloc[-1] > signal_line.iloc[-1] and histogram.iloc[-1] > 0:
            result['macd_signal_label'] = 'Bullish'
        elif macd_line.iloc[-1] < signal_line.iloc[-1] and histogram.iloc[-1] < 0:
            result['macd_signal_label'] = 'Bearish'
        else:
            result['macd_signal_label'] = 'Neutral'

        # Volume
        avg_vol = volume.tail(20).mean()
        latest_vol = volume.iloc[-1]
        result['avg_volume_20d'] = round(avg_vol)
        result['latest_volume'] = round(latest_vol)
        vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 1
        if vol_ratio > 1.5:
            result['volume_signal'] = 'High Activity'
        elif vol_ratio < 0.5:
            result['volume_signal'] = 'Low Activity'
        else:
            result['volume_signal'] = 'Normal'

        # Overall signal
        signals = [result['ma_signal'], result['rsi_signal'],
                   result['macd_signal_label']]
        bullish = sum(1 for s in signals if 'Bullish' in s or s == 'Oversold')
        bearish = sum(1 for s in signals if 'Bearish' in s or s == 'Overbought')
        if bullish >= 2:
            result['overall_signal'] = 'Bullish'
        elif bearish >= 2:
            result['overall_signal'] = 'Bearish'
        else:
            result['overall_signal'] = 'Neutral'

        print(f"✅ Computed technical indicators for {ticker}: {result['overall_signal']}")
    except Exception as e:
        print(f"⚠️ Could not compute technical indicators: {e}")
    return result

def get_company_news(ticker: str, api_key: str = None, days_back: int = 5, limit: int = 50) -> List[dict] | None:
    """
    Fetches recent company news from Yahoo Finance.
    
    Args:
        ticker: Stock ticker symbol
        api_key: Not used for Yahoo Finance
        days_back: Number of days to look back for news (default: 5)
        limit: Maximum number of news articles to fetch (default: 50)
    
    Returns:
        List of dictionaries containing filtered news data, or None if error occurs
    """
    try:
        stock = yf.Ticker(ticker)
        news = stock.news
        
        if not news:
            print(f"No news data returned from Yahoo Finance for {ticker}.")
            return None
        
        # Filter to keep only required fields
        filtered_news = []
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        for article in news:
            # Parse publish date
            pub_date_str = article.get('providerPublishTime')
            if pub_date_str:
                pub_date = datetime.fromtimestamp(pub_date_str)
            else:
                continue
            
            # Filter by date
            if pub_date < start_date:
                continue
            
            filtered_article = {
                'symbol': ticker,
                'title': article.get('title'),
                'publishedDate': pub_date.strftime('%Y-%m-%d %H:%M:%S'),
                'text': article.get('summary', '')[:500],  # Truncate summary
                'site': article.get('publisher'),
                'url': article.get('link')
            }
            filtered_news.append(filtered_article)
            
            if len(filtered_news) >= limit:
                break
        
        print(f"Successfully fetched {len(filtered_news)} news articles for {ticker}")
        return filtered_news
        
    except Exception as e:
        print(f"Error fetching news for {ticker}: {e}")
        return None

# Compatibility aliases for FMP function names
get_fmp_income_statement = get_yfinance_income_statement
get_fmp_balance_sheet = get_yfinance_balance_sheet
get_fmp_cash_flow_statement = get_yfinance_cash_flow_statement
get_fmp_ratios_and_key_metrics = get_yfinance_ratios_and_key_metrics
get_fmp_current_price = get_yfinance_current_price
get_fmp_company_profile = get_yfinance_company_profile
get_fmp_target_price = get_yfinance_target_price
get_fmp_analyst_rating = get_yfinance_analyst_rating
get_fmp_market_cap = get_yfinance_market_cap

# Keep FMP enterprise value function but it won't work with free plan
def fetch_fmp_enterprise_value(ticker: str, api_key: str, limit: int = 2000) -> pd.DataFrame | None:
    """Placeholder for FMP enterprise value (not supported on free plan)."""
    print(f"Warning: FMP enterprise value not available on free plan for {ticker}")
    return None

def combine_peer_financial_data(tickers: List[str], api_key: str, years_limit: int = 5) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Combines EBITDA and EV/EBITDA for a list of peer tickers using Yahoo Finance."""
    all_peers_data = {}
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            # Try to get EBITDA from financials
            financials = stock.financials
            if financials is not None and not financials.empty:
                # Check if EBITDA is available
                if 'EBITDA' in financials.index:
                    ebitda_data = financials.loc['EBITDA']
                    for date, value in ebitda_data.items():
                        year = date.year
                        if ticker not in all_peers_data:
                            all_peers_data[ticker] = {}
                        if year not in all_peers_data[ticker]:
                            all_peers_data[ticker][year] = {}
                        all_peers_data[ticker][year]['EBITDA'] = value
        except Exception as e:
            print(f"Error fetching peer data for {ticker}: {e}")
            continue
    
    ebitda_records = []
    for ticker, yearly_data in all_peers_data.items():
        for year, metrics in yearly_data.items():
            if "EBITDA" in metrics and metrics["EBITDA"] is not None:
                ebitda_records.append({"ticker": ticker, "year": year, "EBITDA": metrics["EBITDA"]})
    
    df_ebitda_all = pd.DataFrame(ebitda_records)
    df_ebitda_pivot = pd.DataFrame()
    if not df_ebitda_all.empty:
        df_ebitda_pivot = df_ebitda_all.pivot(index="year", columns="ticker", values="EBITDA").sort_index()
    
    # EV/EBITDA - not easily available from Yahoo Finance
    df_ev_ebitda_pivot = pd.DataFrame()
    
    return df_ebitda_pivot, df_ev_ebitda_pivot

def project_ebitda_for_peers(df_ebitda_historical: pd.DataFrame, num_projection_years: int = 1) -> pd.DataFrame:
    """Projects EBITDA for future years based on average historical YoY growth."""
    df_projected = df_ebitda_historical.copy()
    if df_projected.empty:
        return df_projected

    last_historical_year = df_projected.index.max()
    
    for company in df_projected.columns:
        historical_values = df_projected[company].dropna()
        if len(historical_values) < 2:
            print(f"Not enough historical EBITDA data for {company} to project.")
            continue
        
        growth_rates = historical_values.pct_change().dropna()
        if growth_rates.empty or all(g == 0 for g in growth_rates):
            avg_growth_rate = 0 
        else:
            avg_growth_rate = growth_rates.mean()

        current_ebitda = historical_values.iloc[-1]
        for i in range(1, num_projection_years + 1):
            projection_year = last_historical_year + i
            current_ebitda = current_ebitda * (1 + avg_growth_rate)
            df_projected.loc[projection_year, company] = current_ebitda
            
    return df_projected.sort_index()

if __name__ == "__main__":
    print("Testing market_data_api.py with Yahoo Finance...")
    
    print("\nTesting get_comprehensive_financial_data for AAPL...")
    financial_data = get_comprehensive_financial_data("AAPL")
    for statement_type, df in financial_data.items():
        if df is not None and not df.empty:
            if isinstance(df, pd.DataFrame):
                print(f"{statement_type}: {len(df)} rows of data")
            else:
                print(f"{statement_type}: Data available")
        else:
            print(f"{statement_type}: No data")
    
    print("\nTesting get_comprehensive_company_metrics for AAPL...")
    metrics = get_comprehensive_company_metrics("AAPL")
    for key, value in metrics.items():
        if value is not None:
            print(f"  {key}: {value}")

    print("\nmarket_data_api.py tests complete.")
