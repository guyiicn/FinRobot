#!/usr/bin/env python
# coding: utf-8
"""
多Agent投资组合分析 — 基于 autogen MultiAssistantWithLeader 架构。
CIO 协调 3 个分析师团队，综合决策投资组合配置。

支持 A股（akshare）和美股（yfinance），自动选择数据源。

架构:
  CIO (首席投资官)
   ├── 市场情绪分析师组 → 新闻情绪、市场热度
   ├── 风险评估分析师组 → 风险识别与量化
   └── 基本面分析师组   → 财务数据、估值分析

用法:
  # A股白酒板块
  python generate_portfolio.py \\
    --tickers 600519 000858 002304 \\
    --names "贵州茅台" "五粮液" "洋河股份" \\
    --language zh --config-file ../config/config.ini

  # 美股科技
  python generate_portfolio.py \\
    --tickers AAPL MSFT GOOGL \\
    --names "Apple" "Microsoft" "Google" \\
    --language en --config-file ../config/config.ini
"""

import argparse
import os
import re
import sys
import json
import time
from datetime import datetime
from typing import Dict, List
from textwrap import dedent

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ═══════════════════════════════════════════════════════════════
# 数据采集（复用已有模块）
# ═══════════════════════════════════════════════════════════════

def _is_a_share(ticker: str) -> bool:
    return bool(re.match(r'^\d{6}$', ticker))


def gather_stock_data(ticker: str, name: str, language: str = 'zh') -> Dict:
    """采集单只股票的综合数据，供 Agent 使用。"""
    is_ashare = _is_a_share(ticker)
    data = {'ticker': ticker, 'name': name, 'financials': '', 'news': '', 'price': ''}

    if is_ashare:
        saved = {}
        for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
            if k in os.environ:
                saved[k] = os.environ.pop(k)
        try:
            import akshare as ak

            # 财务摘要
            try:
                abstract = ak.stock_financial_abstract_ths(symbol=ticker, indicator='按报告期')
                time.sleep(1.5)
                if abstract is not None and not abstract.empty:
                    abstract = abstract.sort_values('报告期', ascending=False)
                    row = abstract.iloc[0]
                    data['financials'] = (
                        f"报告期: {row.get('报告期','')}, "
                        f"营业总收入: {row.get('营业总收入','')}, "
                        f"净利润: {row.get('净利润','')}, "
                        f"EPS: {row.get('基本每股收益','')}, "
                        f"ROE: {row.get('净资产收益率','')}, "
                        f"毛利率: {row.get('销售毛利率','')}"
                    )
            except:
                pass

            # 新闻
            try:
                news_df = ak.stock_news_em(symbol=ticker)
                time.sleep(1.5)
                if news_df is not None and not news_df.empty:
                    lines = []
                    for _, r in news_df.head(5).iterrows():
                        lines.append(f"[{str(r.get('发布时间',''))[:10]}] {r.get('新闻标题','')}")
                    data['news'] = '\n'.join(lines)
            except:
                pass

            # 股价
            try:
                first = ticker[0]
                sym = f"{'sh' if first in ('6','9') else 'sz'}{ticker}"
                df = ak.stock_zh_a_daily(symbol=sym, adjust='qfq')
                time.sleep(1.5)
                if df is not None and not df.empty:
                    close = df['close'].astype(float)
                    latest = float(close.iloc[-1])
                    chg5 = (latest / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
                    chg20 = (latest / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0
                    data['price'] = f"最新价: ¥{latest:.2f}, 5日涨跌: {chg5:+.2f}%, 20日涨跌: {chg20:+.2f}%"
            except:
                pass
        finally:
            os.environ.update(saved)
    else:
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info or {}
            data['financials'] = (
                f"Revenue: ${info.get('totalRevenue',0)/1e9:.1f}B, "
                f"Net Income: ${info.get('netIncomeToCommon',0)/1e9:.1f}B, "
                f"EPS: {info.get('trailingEps','N/A')}, "
                f"PE: {info.get('trailingPE','N/A')}, "
                f"ROE: {info.get('returnOnEquity',0)*100:.1f}%"
            )
            news = stock.news or []
            lines = []
            for n in news[:5]:
                lines.append(f"[{datetime.fromtimestamp(n.get('providerPublishTime',0)).strftime('%Y-%m-%d')}] {n.get('title','')}")
            data['news'] = '\n'.join(lines)

            hist = stock.history(period='1mo')
            if not hist.empty:
                close = hist['Close'].values.flatten()
                latest = float(close[-1])
                chg5 = (latest / float(close[-6]) - 1) * 100 if len(close) >= 6 else 0
                data['price'] = f"Latest: ${latest:.2f}, 5d: {chg5:+.2f}%"
        except Exception as e:
            print(f"  ⚠️ yfinance error for {ticker}: {e}")

    return data


def format_all_data(stocks_data: List[Dict], language: str = 'zh') -> str:
    """将所有股票数据格式化为文本，供 Agent prompt 使用。"""
    parts = []
    for s in stocks_data:
        section = f"\n{'='*40}\n{s['name']} ({s['ticker']})\n{'='*40}\n"
        if s['financials']:
            section += f"{'财务指标' if language == 'zh' else 'Financials'}: {s['financials']}\n"
        if s['price']:
            section += f"{'股价' if language == 'zh' else 'Price'}: {s['price']}\n"
        if s['news']:
            section += f"{'近期新闻' if language == 'zh' else 'Recent News'}:\n{s['news']}\n"
        parts.append(section)
    return '\n'.join(parts)


# ═══════════════════════════════════════════════════════════════
# 多角色分析（直接用 OpenAI，不依赖 autogen）
# ═══════════════════════════════════════════════════════════════

ANALYST_ROLES = {
    'zh': {
        'sentiment': {
            'title': '市场情绪分析师',
            'prompt': '你是一位资深市场情绪分析师。请根据以下各股票的近期新闻和股价走势，分析市场情绪和投资者信心。为每只股票评分（1-10分，10分最乐观），并解释原因。200字以内。',
        },
        'risk': {
            'title': '风险评估分析师',
            'prompt': '你是一位风险评估分析师。请根据以下各股票的财务数据和市场信息，识别每只股票的主要风险。为每只股票的风险评级（低/中/高），并列出前2个关键风险。200字以内。',
        },
        'fundamental': {
            'title': '基本面分析师',
            'prompt': '你是一位基本面分析师。请根据以下各股票的财务指标（营收、利润、EPS、ROE等），对比分析各公司的基本面强弱。排出基本面从强到弱的顺序，并解释。200字以内。',
        },
        'cio': {
            'title': '首席投资官 (CIO)',
            'prompt': dedent('''你是首席投资官。以下是三位分析师的报告。请综合所有分析，做出最终投资组合决策。

请输出：
1. 投资组合配置（每只股票的建议仓位比例，总计100%）
2. 每只股票的投资评级（买入/增持/持有/减持/卖出）
3. 组合整体风险评估
4. 操作建议（150字以内）

注意：仓位分配要考虑风险分散和预期收益的平衡。'''),
        },
    },
    'en': {
        'sentiment': {
            'title': 'Market Sentiment Analyst',
            'prompt': 'You are a market sentiment analyst. Analyze market sentiment for each stock based on recent news and price trends. Score each 1-10 (10=most bullish). Under 200 words.',
        },
        'risk': {
            'title': 'Risk Assessment Analyst',
            'prompt': 'You are a risk analyst. Identify key risks for each stock. Rate risk level (Low/Medium/High) and list top 2 risks per stock. Under 200 words.',
        },
        'fundamental': {
            'title': 'Fundamental Analyst',
            'prompt': 'You are a fundamental analyst. Compare financial metrics across stocks. Rank from strongest to weakest fundamentals. Under 200 words.',
        },
        'cio': {
            'title': 'Chief Investment Officer (CIO)',
            'prompt': dedent('''You are the CIO. Below are reports from three analysts. Make the final portfolio decision.

Output:
1. Portfolio allocation (% per stock, total 100%)
2. Rating per stock (Buy/Overweight/Hold/Underweight/Sell)
3. Overall portfolio risk assessment
4. Action plan (under 150 words)

Balance risk diversification with expected returns.'''),
        },
    },
}


def run_analyst(role_key: str, data_text: str, api_key: str,
                base_url: str = None, model: str = None, language: str = 'zh') -> str:
    """运行单个分析师角色。"""
    roles = ANALYST_ROLES.get(language, ANALYST_ROLES['en'])
    role = roles[role_key]

    print(f"  🤖 {role['title']}...")

    try:
        from openai import OpenAI
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        resp = client.chat.completions.create(
            model=model or 'gpt-4o-mini',
            messages=[
                {"role": "system", "content": role['prompt']},
                {"role": "user", "content": data_text},
            ],
            temperature=0.5,
            max_tokens=600,
        )
        result = resp.choices[0].message.content.strip()
        print(f"    ✅ {len(result)} chars")
        return result
    except Exception as e:
        return f"[{role['title']} analysis failed: {e}]"


def run_cio(analyst_reports: Dict[str, str], stocks_summary: str,
            api_key: str, base_url: str = None, model: str = None,
            language: str = 'zh') -> str:
    """运行 CIO 综合决策。"""
    roles = ANALYST_ROLES.get(language, ANALYST_ROLES['en'])
    cio = roles['cio']

    print(f"  🎯 {cio['title']}...")

    # 汇总所有分析师报告
    combined = f"{'股票数据摘要' if language == 'zh' else 'Stock Data Summary'}:\n{stocks_summary}\n\n"
    for role_key, report in analyst_reports.items():
        title = roles[role_key]['title']
        combined += f"{'='*40}\n{title}的报告:\n{'='*40}\n{report}\n\n"

    try:
        from openai import OpenAI
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        resp = client.chat.completions.create(
            model=model or 'gpt-4o-mini',
            messages=[
                {"role": "system", "content": cio['prompt']},
                {"role": "user", "content": combined},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        result = resp.choices[0].message.content.strip()
        print(f"    ✅ CIO decision: {len(result)} chars")
        return result
    except Exception as e:
        return f"[CIO decision failed: {e}]"


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Portfolio Analysis")
    parser.add_argument("--tickers", type=str, nargs="+", required=True)
    parser.add_argument("--names", type=str, nargs="+", required=True)
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--config-file", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)

    args = parser.parse_args()

    if len(args.tickers) != len(args.names):
        print("❌ --tickers 和 --names 数量必须一致")
        return

    # 规范化 ticker
    tickers = [t if _is_a_share(t) else t.upper() for t in args.tickers]
    is_ashare = _is_a_share(tickers[0])

    output_dir = args.output_dir or os.path.join('.', 'output', 'portfolio')
    os.makedirs(output_dir, exist_ok=True)

    # 加载配置
    api_key = base_url = model = None
    try:
        from modules.common_utils import load_config, get_api_key
        config = load_config(args.config_file)
        api_key = get_api_key(config, "API_KEYS", "openai_api_key")
        try: base_url = get_api_key(config, "API_KEYS", "openai_base_url")
        except: pass
        try: model = get_api_key(config, "API_KEYS", "openai_model")
        except: pass
    except Exception as e:
        print(f"⚠️ Config: {e}")

    print(f"\n{'=' * 60}")
    print(f"💼 MULTI-AGENT PORTFOLIO ANALYSIS")
    print(f"{'=' * 60}")
    print(f"Stocks: {', '.join(f'{n}({t})' for n, t in zip(args.names, tickers))}")
    print(f"Market: {'A-share' if is_ashare else 'US'}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'=' * 60}\n")

    # Phase 1: 数据采集
    print("📥 Phase 1: 数据采集")
    stocks_data = []
    for ticker, name in zip(tickers, args.names):
        print(f"  📊 {name} ({ticker})...")
        sd = gather_stock_data(ticker, name, args.language)
        stocks_data.append(sd)

    data_text = format_all_data(stocks_data, args.language)
    print(f"✅ 数据采集完成\n")

    # Phase 2: 多角色分析
    print("🔍 Phase 2: 分析师团队分析")
    analyst_reports = {}
    for role in ['sentiment', 'risk', 'fundamental']:
        report = run_analyst(role, data_text, api_key, base_url, model, args.language)
        analyst_reports[role] = report

    # Phase 3: CIO 决策
    print("\n🎯 Phase 3: CIO 综合决策")
    stocks_summary = '\n'.join([f"{s['name']}({s['ticker']}): {s['price']}" for s in stocks_data])
    cio_decision = run_cio(analyst_reports, stocks_summary, api_key, base_url, model, args.language)

    # 输出结果
    roles = ANALYST_ROLES.get(args.language, ANALYST_ROLES['en'])
    print(f"\n{'=' * 60}")
    print(f"💼 {'投资组合分析报告' if args.language == 'zh' else 'PORTFOLIO ANALYSIS REPORT'}")
    print(f"{'=' * 60}")
    print(f"日期: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"标的: {', '.join(args.names)}\n")

    for role_key, report in analyst_reports.items():
        title = roles[role_key]['title']
        print(f"{'━' * 50}")
        print(f"📊 {title}")
        print(f"{'━' * 50}")
        print(report)
        print()

    print(f"{'━' * 50}")
    print(f"🎯 {roles['cio']['title']} — {'最终决策' if args.language == 'zh' else 'Final Decision'}")
    print(f"{'━' * 50}")
    print(cio_decision)

    # 保存
    report_data = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'stocks': [{'ticker': t, 'name': n} for t, n in zip(tickers, args.names)],
        'market': 'A-share' if is_ashare else 'US',
        'analyst_reports': analyst_reports,
        'cio_decision': cio_decision,
        'raw_data': stocks_data,
    }

    json_path = os.path.join(output_dir, f"portfolio_{datetime.now().strftime('%Y%m%d')}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    txt_path = os.path.join(output_dir, f"portfolio_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"投资组合分析报告 — {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"标的: {', '.join(f'{n}({t})' for n, t in zip(args.names, tickers))}\n\n")
        for role_key, report in analyst_reports.items():
            f.write(f"{'='*50}\n{roles[role_key]['title']}\n{'='*50}\n{report}\n\n")
        f.write(f"{'='*50}\n{roles['cio']['title']} — 最终决策\n{'='*50}\n{cio_decision}\n")

    print(f"\n{'=' * 60}")
    print(f"✅ {'分析完成!' if args.language == 'zh' else 'ANALYSIS COMPLETE!'}")
    print(f"{'=' * 60}")
    print(f"📄 Text: {txt_path}")
    print(f"📊 JSON: {json_path}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
