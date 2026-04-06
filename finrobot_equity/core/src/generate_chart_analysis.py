#!/usr/bin/env python
# coding: utf-8
"""
多模态K线分析 — 生成专业K线图 → GPT-4o 视觉分析趋势。
支持 A 股（akshare）和美股（yfinance）。

用法:
  # A股
  python3 generate_chart_analysis.py --company-ticker 600519 --company-name "贵州茅台" \\
      --language zh --config-file ../config/config.ini

  # 美股
  python3 generate_chart_analysis.py --company-ticker TSLA --company-name "Tesla" \\
      --days 90 --language en --config-file ../config/config.ini
"""

import argparse
import os
import re
import sys
import json
import time
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.common_utils import load_config, get_api_key
from modules.chart_fonts import setup_chart_fonts
setup_chart_fonts()


def _is_a_share(ticker: str) -> bool:
    return bool(re.match(r'^\d{6}$', ticker))


# ═══════════════════════════════════════════════════════════════
# K线图生成
# ═══════════════════════════════════════════════════════════════

def generate_candlestick_chart(ticker: str, company_name: str, days: int = 60,
                                output_dir: str = '.') -> str:
    """生成 mplfinance K线图，返回图片路径。"""
    import matplotlib
    matplotlib.use('Agg')
    import mplfinance as mpf

    is_ashare = _is_a_share(ticker)
    chart_path = os.path.join(output_dir, f"{ticker}_candlestick.png")

    try:
        if is_ashare:
            # akshare 新浪日K
            saved = {}
            for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
                if k in os.environ:
                    saved[k] = os.environ.pop(k)
            try:
                import akshare as ak
                first = ticker[0]
                sym = f"{'sh' if first in ('6', '9') else 'sz'}{ticker}"
                df = ak.stock_zh_a_daily(symbol=sym, adjust='qfq')
                time.sleep(1.5)
                if df is None or df.empty:
                    print("  ⚠️ No data from akshare")
                    return ''
                df = df.tail(days).copy()
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                df.rename(columns={
                    'open': 'Open', 'high': 'High', 'low': 'Low',
                    'close': 'Close', 'volume': 'Volume',
                }, inplace=True)
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
            finally:
                os.environ.update(saved)
        else:
            # yfinance
            import yfinance as yf
            end = datetime.now()
            start = end - timedelta(days=days + 30)  # 多取一点保证有足够交易日
            df = yf.download(ticker, start=start.strftime('%Y-%m-%d'),
                             end=end.strftime('%Y-%m-%d'), progress=False)
            if df.empty:
                print("  ⚠️ No data from yfinance")
                return ''
            df = df.tail(days)
            # 确保列名正确
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

        # 获取可用中文字体
        import matplotlib.font_manager as _fm
        _cjk_font = None
        for _cand in ['Noto Sans CJK JP', 'Noto Sans CJK SC', 'FZFangSong-Z02', 'SimHei']:
            if _cand in {f.name for f in _fm.fontManager.ttflist}:
                _cjk_font = _cand
                break
        _font_prop = _fm.FontProperties(family=_cjk_font) if _cjk_font else None

        # 绘制 K 线图
        mc = mpf.make_marketcolors(
            up='#CC0000' if is_ashare else '#26a69a',    # A股红涨
            down='#00CC00' if is_ashare else '#ef5350',   # A股绿跌
            edge='inherit', wick='inherit', volume='in',
        )
        style = mpf.make_mpf_style(
            marketcolors=mc, gridstyle=':', y_on_right=True,
            figcolor='white', facecolor='white',
        )

        # 添加均线
        title = f"{company_name} ({ticker}) — {'K线分析' if is_ashare else 'Candlestick Analysis'}"

        fig, axes = mpf.plot(
            df, type='candle', style=style, volume=True,
            mav=(5, 20, 60), title='\n',  # mplfinance title 不支持自定义字体，留空
            figsize=(12, 7), returnfig=True,
            ylabel='Price', ylabel_lower='Volume',
        )
        # 手动设置标题（用中文字体）
        if _font_prop:
            fig.suptitle(title, fontproperties=_font_prop, fontsize=13, y=0.98)
        else:
            fig.suptitle(title, fontsize=13, y=0.98)
        fig.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"  ✅ K线图: {chart_path}")
        return chart_path

    except Exception as e:
        print(f"  ⚠️ K线图生成失败: {e}")
        import traceback; traceback.print_exc()
        return ''


# ═══════════════════════════════════════════════════════════════
# 新闻采集（复用市场预测的逻辑）
# ═══════════════════════════════════════════════════════════════

def _fetch_news(ticker: str, is_ashare: bool) -> str:
    """获取近期新闻摘要文本"""
    news_text = ""
    try:
        if is_ashare:
            saved = {}
            for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
                if k in os.environ:
                    saved[k] = os.environ.pop(k)
            try:
                import akshare as ak
                news_df = ak.stock_news_em(symbol=ticker)
                time.sleep(1.5)
                if news_df is not None and not news_df.empty:
                    lines = []
                    for _, row in news_df.head(8).iterrows():
                        title = str(row.get('新闻标题', row.get('title', '')))
                        date = str(row.get('发布时间', row.get('datetime', '')))[:10]
                        lines.append(f"[{date}] {title}")
                    news_text = '\n'.join(lines)
            finally:
                os.environ.update(saved)
        else:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            news = stock.news or []
            lines = []
            for n in news[:8]:
                date = datetime.fromtimestamp(n.get('providerPublishTime', 0)).strftime('%Y-%m-%d')
                lines.append(f"[{date}] {n.get('title', '')}")
            news_text = '\n'.join(lines)
    except Exception as e:
        print(f"  ⚠️ 新闻获取失败: {e}")

    return news_text


# ═══════════════════════════════════════════════════════════════
# GPT-4o 视觉分析
# ═══════════════════════════════════════════════════════════════

VISION_PROMPTS = {
    'zh': (
        "你是一位资深的技术分析师。请仔细观察这张K线图（包含价格走势、成交量、5日/20日/60日均线），"
        "结合提供的近期新闻，完成以下分析：\n\n"
        "1. 趋势判断：当前处于上升趋势、下降趋势还是震荡整理？\n"
        "2. 关键价位：支撑位和阻力位在哪里？\n"
        "3. 均线分析：均线排列状态（多头/空头/缠绕），金叉/死叉信号\n"
        "4. 成交量分析：量价配合情况，是否有异常放量/缩量\n"
        "5. 形态识别：是否存在头肩顶/底、双底、三角形等经典形态？\n"
        "6. 预测：未来一周的走势预测和操作建议\n\n"
        "请用中文回答，直接输出分析结果。"
    ),
    'en': (
        "You are a senior technical analyst. Analyze this candlestick chart carefully "
        "(price action, volume, 5/20/60-day moving averages) along with the recent news provided.\n\n"
        "Please provide:\n"
        "1. Trend: Uptrend, downtrend, or consolidation?\n"
        "2. Key levels: Support and resistance levels\n"
        "3. Moving averages: Alignment (bullish/bearish/tangled), golden/death cross signals\n"
        "4. Volume: Price-volume correlation, any unusual volume spikes\n"
        "5. Pattern recognition: Head & shoulders, double bottom, triangles, etc.\n"
        "6. Prediction: Next week forecast and trading recommendation\n\n"
        "Reply in plain text."
    ),
}


def analyze_chart_with_vision(chart_path: str, company_name: str, ticker: str,
                               news_text: str, api_key: str, base_url: str = None,
                               model: str = None, language: str = 'zh') -> str:
    """用 GPT-4o 视觉分析 K 线图"""
    if not api_key:
        return "[No API key — vision analysis unavailable]"

    # 读取图片并转 base64
    with open(chart_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')

    system_prompt = VISION_PROMPTS.get(language, VISION_PROMPTS['en'])

    user_content = [
        {"type": "text", "text": f"公司: {company_name} ({ticker})\n日期: {datetime.now().strftime('%Y-%m-%d')}\n\n"
                                  f"近期新闻:\n{news_text}\n\n请根据K线图和新闻进行技术分析。"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"}},
    ]

    try:
        from openai import OpenAI
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        # GPT-4o 支持视觉
        vision_model = model or 'gpt-4o-mini'
        # gpt-4o-mini 也支持视觉输入
        print(f"  🔍 Using vision model: {vision_model}")

        resp = client.chat.completions.create(
            model=vision_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,
            max_tokens=1200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Vision analysis failed: {e}]"


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Multimodal Chart Analysis (GPT-4o Vision)")
    parser.add_argument("--company-ticker", type=str, required=True)
    parser.add_argument("--company-name", type=str, required=True)
    parser.add_argument("--days", type=int, default=60, help="Trading days to display")
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--config-file", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)

    args = parser.parse_args()
    ticker = args.company_ticker if _is_a_share(args.company_ticker) else args.company_ticker.upper()
    is_ashare = _is_a_share(ticker)

    output_dir = args.output_dir or os.path.join('.', 'output', ticker, 'chart_analysis')
    os.makedirs(output_dir, exist_ok=True)

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
        print(f"⚠️ Config: {e}")

    print(f"\n{'=' * 60}")
    print(f"📊 MULTIMODAL CHART ANALYSIS (GPT-4o Vision)")
    print(f"{'=' * 60}")
    print(f"Company: {args.company_name} ({ticker})")
    print(f"Period: {args.days} trading days")
    print(f"Market: {'A-share' if is_ashare else 'US'}")
    print(f"{'=' * 60}\n")

    # 1. 生成K线图
    print("📈 Generating candlestick chart...")
    chart_path = generate_candlestick_chart(ticker, args.company_name, args.days, output_dir)
    if not chart_path:
        print("❌ Chart generation failed. Exiting.")
        return

    # 2. 获取新闻
    print("📰 Fetching recent news...")
    news_text = _fetch_news(ticker, is_ashare)
    if news_text:
        print(f"  ✅ {news_text.count(chr(10)) + 1} news items")
    else:
        news_text = "暂无近期新闻" if args.language == 'zh' else "No recent news available"
        print(f"  ⚠️ No news available")

    # 3. GPT-4o 视觉分析
    print("\n🤖 Analyzing chart with GPT-4o Vision...")
    analysis = analyze_chart_with_vision(
        chart_path, args.company_name, ticker, news_text,
        api_key, base_url, model, args.language,
    )

    # 4. 输出结果
    print(f"\n{'━' * 60}")
    print(f"📊 {args.company_name} ({ticker}) — {'技术分析报告' if args.language == 'zh' else 'Technical Analysis'}")
    print(f"{'━' * 60}\n")
    print(analysis)

    # 5. 保存
    report_path = os.path.join(output_dir, f"{ticker}_chart_analysis.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"{args.company_name} ({ticker}) — Technical Chart Analysis\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"Period: {args.days} trading days\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(f"Recent News:\n{news_text}\n\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(f"Analysis:\n{analysis}\n")

    result_json = {
        'ticker': ticker,
        'company': args.company_name,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'chart_path': chart_path,
        'news': news_text,
        'analysis': analysis,
    }
    json_path = os.path.join(output_dir, f"{ticker}_chart_analysis.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result_json, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"✅ CHART ANALYSIS COMPLETE!")
    print(f"{'=' * 60}")
    print(f"📈 Chart: {chart_path}")
    print(f"📄 Report: {report_path}")
    print(f"📊 JSON: {json_path}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
