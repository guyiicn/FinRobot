#!/usr/bin/env python
# coding: utf-8
"""
市场预测报告生成器 — 基于 FinGPT Forecaster 思路。
收集近期新闻 + 财务数据 + 股价走势 → LLM 综合预测未来一周涨跌。

支持 A 股（akshare/同花顺）和美股（yfinance/FinnHub）。

用法:
  # A股
  python3 generate_market_forecast.py --company-ticker 600519 --company-name "贵州茅台" \\
      --language zh --config-file ../config/config.ini

  # 美股
  python3 generate_market_forecast.py --company-ticker AAPL --company-name "Apple Inc." \\
      --language en --config-file ../config/config.ini

  # 多只股票批量预测
  python3 generate_market_forecast.py --company-ticker 600519 000858 002304 \\
      --company-name "贵州茅台" "五粮液" "洋河股份" --language zh --config-file ../config/config.ini
"""

import argparse
import os
import re
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.common_utils import load_config, get_api_key


def _is_a_share(ticker: str) -> bool:
    return bool(re.match(r'^\d{6}$', ticker))


# ═══════════════════════════════════════════════════════════════
# 数据采集
# ═══════════════════════════════════════════════════════════════

def _fetch_ashare_data(ticker: str) -> Dict:
    """A股数据采集：新闻 + 财务摘要 + 近期股价"""
    saved = {}
    for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    try:
        import akshare as ak
        result = {'news': [], 'financials': {}, 'price_history': '', 'profile': ''}

        # 1. 近期新闻
        try:
            news_df = ak.stock_news_em(symbol=ticker)
            time.sleep(1.5)
            if news_df is not None and not news_df.empty:
                for _, row in news_df.head(10).iterrows():
                    title = str(row.get('新闻标题', row.get('title', '')))
                    date = str(row.get('发布时间', row.get('datetime', '')))[:10]
                    content = str(row.get('新闻内容', row.get('content', '')))[:200]
                    result['news'].append({'title': title, 'date': date, 'content': content})
                print(f"  ✅ 新闻: {len(result['news'])} 条")
        except Exception as e:
            print(f"  ⚠️ 新闻获取失败: {e}")

        # 2. 财务摘要（同花顺）
        try:
            abstract = ak.stock_financial_abstract_ths(symbol=ticker, indicator='按报告期')
            time.sleep(1.5)
            if abstract is not None and not abstract.empty:
                abstract = abstract.sort_values('报告期', ascending=False)
                latest = abstract.iloc[0]
                result['financials'] = {
                    '报告期': str(latest.get('报告期', '')),
                    '营业总收入': str(latest.get('营业总收入', '')),
                    '净利润': str(latest.get('净利润', '')),
                    '基本每股收益': str(latest.get('基本每股收益', '')),
                    '净资产收益率': str(latest.get('净资产收益率', '')),
                    '销售毛利率': str(latest.get('销售毛利率', '')),
                    '资产负债率': str(latest.get('资产负债率', '')),
                }
                print(f"  ✅ 财务摘要: {latest.get('报告期', 'N/A')}")
        except Exception as e:
            print(f"  ⚠️ 同花顺摘要失败: {e}")

        # 3. 近期股价（新浪日K）
        try:
            first = ticker[0]
            sym = f"{'sh' if first in ('6', '9') else 'sz'}{ticker}"
            df = ak.stock_zh_a_daily(symbol=sym, adjust='qfq')
            time.sleep(1.5)
            if df is not None and not df.empty:
                recent = df.tail(20)
                lines = []
                for _, r in recent.iterrows():
                    lines.append(f"{r['date']}: 开{r['open']:.2f} 高{r['high']:.2f} "
                                 f"低{r['low']:.2f} 收{r['close']:.2f} 量{int(r['volume'])}")
                result['price_history'] = '\n'.join(lines)

                close = df['close'].astype(float)
                latest_p = float(close.iloc[-1])
                chg_5d = (latest_p / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
                chg_20d = (latest_p / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0
                result['price_summary'] = (
                    f"最新价: ¥{latest_p:.2f}, "
                    f"近5日涨跌: {chg_5d:+.2f}%, "
                    f"近20日涨跌: {chg_20d:+.2f}%"
                )
                print(f"  ✅ 股价: ¥{latest_p:.2f}")
        except Exception as e:
            print(f"  ⚠️ 股价获取失败: {e}")

        return result
    finally:
        os.environ.update(saved)


def _fetch_us_data(ticker: str) -> Dict:
    """美股数据采集：yfinance 股价 + 基本面"""
    result = {'news': [], 'financials': {}, 'price_history': '', 'profile': ''}

    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)

        # 1. 基本信息
        try:
            info = stock.info or {}
            result['profile'] = (
                f"Sector: {info.get('sector', 'N/A')}, Industry: {info.get('industry', 'N/A')}, "
                f"Market Cap: ${info.get('marketCap', 0) / 1e9:.1f}B, "
                f"PE: {info.get('forwardPE', 'N/A')}, "
                f"52W Range: ${info.get('fiftyTwoWeekLow', 0):.2f}-${info.get('fiftyTwoWeekHigh', 0):.2f}"
            )
            result['financials'] = {
                'Revenue': f"${info.get('totalRevenue', 0) / 1e9:.1f}B",
                'Net Income': f"${info.get('netIncomeToCommon', 0) / 1e9:.1f}B",
                'EPS': str(info.get('trailingEps', 'N/A')),
                'PE Ratio': str(info.get('trailingPE', 'N/A')),
                'Profit Margin': f"{info.get('profitMargins', 0) * 100:.1f}%",
                'ROE': f"{info.get('returnOnEquity', 0) * 100:.1f}%",
            }
            print(f"  ✅ Profile & financials loaded")
        except Exception as e:
            print(f"  ⚠️ Profile failed: {e}")

        # 2. 近期新闻
        try:
            news = stock.news or []
            for n in news[:10]:
                result['news'].append({
                    'title': n.get('title', ''),
                    'date': datetime.fromtimestamp(n.get('providerPublishTime', 0)).strftime('%Y-%m-%d'),
                    'content': n.get('title', ''),  # yfinance news only has title
                })
            print(f"  ✅ News: {len(result['news'])} items")
        except Exception as e:
            print(f"  ⚠️ News failed: {e}")

        # 3. 近期股价
        try:
            end = datetime.now()
            start = end - timedelta(days=30)
            hist = stock.history(start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
            if not hist.empty:
                lines = []
                for date, r in hist.tail(20).iterrows():
                    lines.append(f"{date.strftime('%Y-%m-%d')}: O{r['Open']:.2f} H{r['High']:.2f} "
                                 f"L{r['Low']:.2f} C{r['Close']:.2f} V{int(r['Volume'])}")
                result['price_history'] = '\n'.join(lines)

                close = hist['Close'].values.flatten()
                latest_p = float(close[-1])
                chg_5d = (latest_p / float(close[-6]) - 1) * 100 if len(close) >= 6 else 0
                chg_20d = (latest_p / float(close[-21]) - 1) * 100 if len(close) >= 21 else 0
                result['price_summary'] = (
                    f"Latest: ${latest_p:.2f}, "
                    f"5d change: {chg_5d:+.2f}%, "
                    f"20d change: {chg_20d:+.2f}%"
                )
                print(f"  ✅ Price: ${latest_p:.2f}")
        except Exception as e:
            print(f"  ⚠️ Price failed: {e}")

    except Exception as e:
        print(f"  ⚠️ yfinance error: {e}")

    return result


# ═══════════════════════════════════════════════════════════════
# LLM 预测
# ═══════════════════════════════════════════════════════════════

FORECAST_PROMPTS = {
    'zh': (
        "你是一位资深的量化分析师和市场预测专家。请根据以下信息对该股票进行分析和预测：\n\n"
        "请完成以下分析：\n"
        "1. **正面因素**：列出2-4个最重要的利好因素（主要从新闻推断）\n"
        "2. **潜在风险**：列出2-4个最重要的风险因素\n"
        "3. **技术面分析**：根据近期股价走势判断趋势\n"
        "4. **预测**：给出未来一周的股价涨跌预测（如：上涨/下跌 X%）\n"
        "5. **总结**：用2-3句话总结你的分析逻辑\n\n"
        "请用中文回答，直接输出分析结果，不要使用markdown格式。"
    ),
    'en': (
        "You are a senior quantitative analyst and market forecaster. Analyze the following data:\n\n"
        "Please provide:\n"
        "1. **Positive Developments**: 2-4 most important positive factors (mainly from news)\n"
        "2. **Potential Concerns**: 2-4 most important risk factors\n"
        "3. **Technical Analysis**: Trend assessment from recent price action\n"
        "4. **Prediction**: Stock price movement for next week (e.g. up/down by X%)\n"
        "5. **Summary**: 2-3 sentence summary supporting your prediction\n\n"
        "Reply in plain text, no markdown."
    ),
}


def _build_forecast_prompt(company_name: str, ticker: str, data: Dict, language: str) -> str:
    """构建预测 prompt"""
    parts = [f"公司: {company_name} ({ticker})\n日期: {datetime.now().strftime('%Y-%m-%d')}\n"]

    if data.get('profile'):
        parts.append(f"公司概况: {data['profile']}\n")

    if data.get('financials'):
        parts.append("财务指标:\n" if language == 'zh' else "Financials:\n")
        for k, v in data['financials'].items():
            if v and v not in ('False', 'nan', '--', 'None'):
                parts.append(f"  {k}: {v}")
        parts.append("")

    if data.get('price_summary'):
        parts.append(f"{'股价概要' if language == 'zh' else 'Price Summary'}: {data['price_summary']}\n")

    if data.get('price_history'):
        parts.append(f"{'近期股价' if language == 'zh' else 'Recent Prices'}:\n{data['price_history']}\n")

    if data.get('news'):
        parts.append(f"{'近期新闻' if language == 'zh' else 'Recent News'}:")
        for i, n in enumerate(data['news'], 1):
            parts.append(f"  {i}. [{n.get('date', '')}] {n.get('title', '')}")
            if n.get('content') and n['content'] != n.get('title', ''):
                parts.append(f"     {n['content'][:150]}")
        parts.append("")

    return '\n'.join(parts)


def generate_forecast(
    company_name: str,
    ticker: str,
    api_key: str,
    base_url: str = None,
    model: str = None,
    language: str = 'zh',
) -> Dict:
    """
    生成单只股票的市场预测。

    Returns:
        {'ticker': str, 'company': str, 'forecast': str, 'data_summary': str}
    """
    is_ashare = _is_a_share(ticker)
    print(f"\n📊 Fetching data for {company_name} ({ticker})...")

    # 采集数据
    if is_ashare:
        data = _fetch_ashare_data(ticker)
    else:
        data = _fetch_us_data(ticker)

    # 构建 prompt
    user_prompt = _build_forecast_prompt(company_name, ticker, data, language)
    system_prompt = FORECAST_PROMPTS.get(language, FORECAST_PROMPTS['en'])

    print(f"🤖 Generating forecast...")

    if not api_key:
        return {'ticker': ticker, 'company': company_name,
                'forecast': '[No API key — forecast unavailable]',
                'data_summary': user_prompt}

    try:
        from openai import OpenAI
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        resp = client.chat.completions.create(
            model=model or 'gpt-4o-mini',
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        forecast = resp.choices[0].message.content.strip()
        print(f"✅ Forecast generated ({len(forecast)} chars)")
    except Exception as e:
        print(f"⚠️ Forecast failed: {e}")
        forecast = f"[Forecast generation failed: {e}]"

    return {
        'ticker': ticker,
        'company': company_name,
        'forecast': forecast,
        'data_summary': data.get('price_summary', ''),
    }


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Market Forecast Generator (FinGPT-style)")
    parser.add_argument("--company-ticker", type=str, nargs="+", required=True)
    parser.add_argument("--company-name", type=str, nargs="+", required=True)
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--config-file", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)

    args = parser.parse_args()

    if len(args.company_ticker) != len(args.company_name):
        print("❌ Error: --company-ticker and --company-name must have same number of arguments")
        return

    # 加载配置
    api_key = base_url = model = None
    try:
        config = load_config(args.config_file)
        api_key = get_api_key(config, "API_KEYS", "openai_api_key")
        try: base_url = get_api_key(config, "API_KEYS", "openai_base_url")
        except: pass
        try: model = get_api_key(config, "API_KEYS", "openai_model")
        except: pass
    except Exception as e:
        print(f"⚠️ Config error: {e}")

    output_dir = args.output_dir or os.path.join('.', 'output', 'forecasts')
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"📈 MARKET FORECAST GENERATOR")
    print(f"{'=' * 60}")
    print(f"Stocks: {len(args.company_ticker)}")
    print(f"Language: {args.language}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'=' * 60}")

    results = []
    for ticker, name in zip(args.company_ticker, args.company_name):
        t = ticker.upper() if not _is_a_share(ticker) else ticker
        result = generate_forecast(name, t, api_key, base_url, model, args.language)
        results.append(result)

    # 输出报告
    print(f"\n{'=' * 60}")
    print(f"📈 FORECAST RESULTS — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'=' * 60}")

    report_lines = [
        f"市场预测报告 — {datetime.now().strftime('%Y-%m-%d')}" if args.language == 'zh'
        else f"Market Forecast Report — {datetime.now().strftime('%Y-%m-%d')}",
        "=" * 60, "",
    ]

    for r in results:
        header = f"{'━' * 50}\n{r['company']} ({r['ticker']})\n{'━' * 50}"
        print(f"\n{header}")
        print(r['forecast'])
        report_lines.extend([header, "", r.get('data_summary', ''), "", r['forecast'], "", ""])

    # 保存到文件
    report_text = '\n'.join(report_lines)
    date_str = datetime.now().strftime('%Y%m%d')
    txt_path = os.path.join(output_dir, f"forecast_{date_str}.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    json_path = os.path.join(output_dir, f"forecast_{date_str}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"✅ FORECASTS COMPLETE!")
    print(f"{'=' * 60}")
    print(f"📄 Text: {txt_path}")
    print(f"📊 JSON: {json_path}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
