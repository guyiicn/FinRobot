#!/usr/bin/env python
# coding: utf-8
"""
年度报告生成器 — 支持 A 股和美股，自动选择数据源。

用法:
  # A股 (中金风格)
  python3 generate_annual_report.py --company-ticker 600519 --company-name "贵州茅台" \\
      --fyear 2024 --language zh --style cicc --config-file ../config/config.ini

  # 美股
  python3 generate_annual_report.py --company-ticker AAPL --company-name "Apple Inc." \\
      --fyear 2024 --language en --config-file ../config/config.ini
"""

import argparse
import os
import re
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import pandas as pd
import numpy as np

# 模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.common_utils import load_config, get_api_key
from modules.chart_fonts import setup_chart_fonts
setup_chart_fonts()
from modules.text_generator_agents import generate_text_section
from modules.annual_report_pdf import generate_annual_report_pdf
from data_sources import get_adapter


# ═══════════════════════════════════════════════════════════════
# 年报专用 prompt
# ═══════════════════════════════════════════════════════════════
ANNUAL_PROMPTS = {
    "zh": {
        "business_overview": "你是一位资深券商分析师。请根据提供的财务数据撰写业务概况（250-350字），涵盖公司主营业务、商业模式、市场地位、核心竞争力和近年发展。使用中文纯文本，不使用markdown。",
        "operating_results": "你是一位财务分析师。请根据提供的财务数据撰写经营业绩分析（300-400字），涵盖营收增长、毛利率、EBITDA、净利润、EPS等关键指标的趋势分析，以及驱动因素。使用中文纯文本，不使用markdown。",
        "financial_position": "你是一位财务分析师。请根据资产负债表数据撰写财务状况分析（200-250字），涵盖资产负债率、流动性、负债结构、股东权益变动。使用中文纯文本，不使用markdown。",
        "cash_flow_analysis": "你是一位财务分析师。请撰写现金流分析（150-200字），涵盖经营现金流、投资活动、融资活动，评估现金创造能力和资本配置。使用中文纯文本，不使用markdown。",
        "risk_assessment": "你是一位风险分析师。请列出该公司面临的5个主要风险，每个风险用1-2句话描述，包括风险类别（市场/运营/财务/政策/竞争）和具体影响。使用中文。",
        "competitive_analysis": "你是一位行业分析师。请撰写竞争分析（200-250字），对比公司与主要竞争对手在营收规模、利润率、增速、市场份额等方面的差异。使用中文纯文本，不使用markdown。",
        "outlook": "你是一位投资策略师。请撰写公司前景展望（150-200字），涵盖未来1-2年的增长预期、关键催化剂、行业趋势和投资建议。使用中文纯文本，不使用markdown。",
    },
    "en": {
        "business_overview": "You are an equity analyst. Write a business overview (250-350 words) covering the company's main business, model, market position, competitive advantages, and recent developments. Plain text, no markdown.",
        "operating_results": "You are a financial analyst. Write an operating results analysis (300-400 words) covering revenue growth, gross margin, EBITDA, net income, EPS trends and drivers. Plain text, no markdown.",
        "financial_position": "You are a financial analyst. Write a financial position analysis (200-250 words) covering leverage, liquidity, debt structure, and equity changes. Plain text, no markdown.",
        "cash_flow_analysis": "You are a financial analyst. Write a cash flow analysis (150-200 words) covering operating, investing, and financing cash flows. Plain text, no markdown.",
        "risk_assessment": "You are a risk analyst. List 5 key risks with 1-2 sentences each, categorized as market/operational/financial/regulatory/competitive.",
        "competitive_analysis": "You are an industry analyst. Write competitive analysis (200-250 words) comparing the company vs key peers on revenue, margins, growth, market share. Plain text, no markdown.",
        "outlook": "You are a strategist. Write a forward outlook (150-200 words) covering 1-2 year growth expectations, catalysts, industry trends, and investment recommendation. Plain text, no markdown.",
    },
}

ANNUAL_SECTIONS = [
    'business_overview', 'operating_results', 'financial_position',
    'cash_flow_analysis', 'risk_assessment', 'competitive_analysis', 'outlook',
]


def _is_a_share(ticker: str) -> bool:
    return bool(re.match(r'^\d{6}$', ticker))


def _generate_section(section: str, data: dict, api_key: str, company_name: str,
                       ticker: str, base_url: str = None, model: str = None,
                       language: str = 'zh') -> str:
    """用 OpenAI 生成年报某个章节的文本。"""
    from openai import OpenAI

    lang = language
    sys_prompt = ANNUAL_PROMPTS.get(lang, ANNUAL_PROMPTS['en']).get(section, '')
    if not sys_prompt:
        return ''

    # 构建 user prompt
    financial_df = data.get('financial_metrics')
    prompt = f"Company: {company_name} ({ticker})\nFiscal Year: {data.get('fiscal_year', '')}\n\n"

    if financial_df is not None and not financial_df.empty:
        try:
            prompt += f"Financial Data:\n{financial_df.to_markdown()}\n\n"
        except:
            prompt += f"Financial Data:\n{financial_df.to_string()}\n\n"

    if section == 'competitive_analysis' and data.get('peer_names'):
        prompt += f"Key Peers: {', '.join(data['peer_names'])}\n"

    prompt += f"\nPlease provide the {section.replace('_', ' ')} analysis."

    print(f"🤖 Generating '{section}'... (lang={lang})")

    if not api_key:
        return f"[{section} text placeholder]"

    try:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
        resp = client.chat.completions.create(
            model=model or 'gpt-4o-mini',
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=800,
        )
        text = resp.choices[0].message.content.strip()
        print(f"✅ Generated '{section}' ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"⚠️ Failed to generate '{section}': {e}")
        return f"[{section} generation failed]"


def _fetch_share_performance_chart(ticker: str, output_dir: str, is_ashare: bool) -> str:
    """生成股价走势图，返回图片路径。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    chart_path = os.path.join(output_dir, f"{ticker}_share_performance.png")

    try:
        if is_ashare:
            # 用新浪日K (不走代理)
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
                    return ''
                df = df.tail(252)  # 最近一年
                dates = pd.to_datetime(df['date'])
                close = df['close'].astype(float)
            finally:
                os.environ.update(saved)
        else:
            import yfinance as yf
            end = datetime.now()
            start = end - timedelta(days=365)
            hist = yf.download(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'), progress=False)
            if hist.empty:
                return ''
            dates = hist.index
            close = hist['Close'].values.flatten()

        import matplotlib.font_manager as _fm
        _cjk = None
        for _c in ['Noto Sans CJK JP', 'FZFangSong-Z02', 'SimHei']:
            if _c in {f.name for f in _fm.fontManager.ttflist}:
                _cjk = _c; break
        _fp = _fm.FontProperties(family=_cjk) if _cjk else None

        fig, ax = plt.subplots(figsize=(7, 3))
        ax.plot(dates, close, color='#1a365d', linewidth=1.5)
        ax.fill_between(dates, close, alpha=0.1, color='#1a365d')
        title = f"{ticker} — {'近一年股价走势' if is_ashare else '1-Year Price Performance'}"
        ax.set_title(title, fontsize=10, fontproperties=_fp)
        ax.set_ylabel('¥' if is_ashare else '$', fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)
        fig.tight_layout()
        fig.savefig(chart_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"✅ Share performance chart: {chart_path}")
        return chart_path
    except Exception as e:
        print(f"⚠️ Chart generation failed: {e}")
        return ''


def main():
    parser = argparse.ArgumentParser(description="Generate Annual Report")
    parser.add_argument("--company-ticker", type=str, required=True)
    parser.add_argument("--company-name", type=str, required=True)
    parser.add_argument("--fyear", type=str, default="2024", help="Fiscal year (e.g. 2024)")
    parser.add_argument("--data-source", type=str, default="auto",
                        choices=["auto", "yahoo", "akshare", "ths"])
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--style", type=str, default="default", choices=["default", "cicc"])
    parser.add_argument("--peers", type=str, nargs="*", default=[])
    parser.add_argument("--config-file", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--years-limit", type=int, default=5)

    args = parser.parse_args()
    ticker = args.company_ticker.upper() if not _is_a_share(args.company_ticker) else args.company_ticker
    is_ashare = _is_a_share(ticker)

    # 输出目录
    output_dir = args.output_dir or os.path.join('.', 'output', ticker, 'annual_report')
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"📋 ANNUAL REPORT GENERATOR")
    print(f"{'=' * 60}")
    print(f"Company: {args.company_name} ({ticker})")
    print(f"Fiscal Year: {args.fyear}")
    print(f"Data Source: {args.data_source} ({'A-share' if is_ashare else 'US'})")
    print(f"Language: {args.language} | Style: {args.style}")
    print(f"Output: {output_dir}")
    print(f"{'=' * 60}\n")

    # ── 1. 加载配置 ──
    openai_api_key = None
    openai_base_url = None
    openai_model = None
    try:
        config = load_config(args.config_file)
        openai_api_key = get_api_key(config, "API_KEYS", "openai_api_key")
        try:
            openai_base_url = get_api_key(config, "API_KEYS", "openai_base_url")
        except:
            pass
        try:
            openai_model = get_api_key(config, "API_KEYS", "openai_model")
        except:
            pass
    except Exception as e:
        print(f"⚠️ Config error: {e}")

    # ── 2. 获取财务数据 ──
    print("📥 Fetching financial data...")

    # 自动选择数据源
    if args.data_source == 'auto':
        source = 'akshare' if is_ashare else 'yahoo'
    else:
        source = args.data_source

    adapter = get_adapter(source)
    print(f"  Using adapter: {adapter.name}")

    company_data = adapter.fetch_all(ticker=ticker, period='annual', limit=args.years_limit)
    metrics_df = None
    if company_data:
        metrics_df = company_data.to_metrics_dataframe()
        if metrics_df is not None:
            print(f"✅ Financial data: {metrics_df.shape[0]} metrics x {metrics_df.shape[1] - 1} years")
        else:
            print("⚠️ No metrics dataframe generated")
    else:
        print("⚠️ No data from adapter")

    # ── 2.5 获取核心指标 ──
    key_highlights = {}
    cs = '¥' if is_ashare else '$'

    if metrics_df is not None and not metrics_df.empty:
        # 找最新年份列
        year_cols = [c for c in metrics_df.columns if c != 'metrics' and c.endswith('A')]
        if year_cols:
            latest = year_cols[-1]
            for metric in ['Revenue', 'EBITDA', 'EPS']:
                row = metrics_df[metrics_df['metrics'] == metric]
                if not row.empty:
                    val = row[latest].values[0]
                    if val is not None and str(val) != 'None':
                        try:
                            fval = float(val)
                            if metric in ('Revenue', 'EBITDA'):
                                key_highlights[metric] = f"{cs}{fval / 1e9:.1f}B"
                            else:
                                key_highlights[metric] = f"{fval:.2f}"
                        except:
                            key_highlights[metric] = str(val)

            # 毛利率 / EBITDA Margin
            for margin in ['Contribution Margin', 'EBITDA Margin']:
                row = metrics_df[metrics_df['metrics'] == margin]
                if not row.empty:
                    val = row[latest].values[0]
                    if val and str(val) != 'None':
                        key_highlights[margin] = str(val)

            # Revenue Growth
            row = metrics_df[metrics_df['metrics'] == 'Revenue Growth']
            if not row.empty:
                val = row[latest].values[0]
                if val and str(val) != 'None':
                    key_highlights['Revenue Growth' if args.language == 'en' else '营收增速'] = str(val)

    # A股补充数据：PE/PB/ROE
    if is_ashare:
        print("📊 Fetching A-share market data...")
        saved = {}
        for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
            if k in os.environ:
                saved[k] = os.environ.pop(k)
        try:
            import akshare as ak
            abstract = ak.stock_financial_abstract_ths(symbol=ticker, indicator='按报告期')
            time.sleep(1.5)
            if abstract is not None and not abstract.empty:
                abstract = abstract.sort_values('报告期', ascending=False)
                annual = abstract[abstract['报告期'].astype(str).str.endswith('12-31')]
                row = annual.iloc[0] if not annual.empty else abstract.iloc[0]
                roe = str(row.get('净资产收益率', ''))
                if roe and roe not in ('False', 'nan', '--'):
                    key_highlights['ROE'] = roe
                gm = str(row.get('销售毛利率', ''))
                if gm and gm not in ('False', 'nan', '--'):
                    key_highlights['毛利率' if args.language == 'zh' else 'Gross Margin'] = gm
                print(f"✅ THS data OK")
        except Exception as e:
            print(f"⚠️ THS data failed: {e}")
        finally:
            os.environ.update(saved)

    print(f"📊 Key highlights: {key_highlights}")

    # ── 3. 生成股价图 ──
    print("\n📊 Generating charts...")
    chart_path = _fetch_share_performance_chart(ticker, output_dir, is_ashare)

    # ── 4. AI 生成各章节文本 ──
    print("\n📝 Generating AI text sections...")
    gen_data = {
        'financial_metrics': metrics_df,
        'fiscal_year': args.fyear,
        'peer_names': args.peers,
    }

    sections_text = {}
    for section in ANNUAL_SECTIONS:
        sections_text[section] = _generate_section(
            section, gen_data, openai_api_key, args.company_name, ticker,
            base_url=openai_base_url, model=openai_model, language=args.language,
        )

    # 保存文本到文件
    for section, text in sections_text.items():
        path = os.path.join(output_dir, f"{section}.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
    print(f"✅ Text sections saved to {output_dir}")

    # ── 5. 构建财务摘要 DataFrame ──
    fin_summary_df = None
    if metrics_df is not None and not metrics_df.empty:
        year_cols = [c for c in metrics_df.columns if c != 'metrics' and (c.endswith('A'))]
        if year_cols:
            fin_summary_df = metrics_df[['metrics'] + year_cols].set_index('metrics')

    # ── 6. 组装报告数据 ──
    report_data = {
        'company_name': args.company_name,
        'ticker': ticker,
        'fiscal_year': args.fyear,
        'sector': '',
        'report_date': datetime.now().strftime('%Y年%m月' if args.language == 'zh' else '%B %Y'),
        'language': args.language,

        # 文本
        'business_overview': sections_text.get('business_overview', ''),
        'operating_results': sections_text.get('operating_results', ''),
        'financial_position': sections_text.get('financial_position', ''),
        'cash_flow_analysis': sections_text.get('cash_flow_analysis', ''),
        'risk_assessment': sections_text.get('risk_assessment', ''),
        'competitive_analysis': sections_text.get('competitive_analysis', ''),
        'outlook': sections_text.get('outlook', ''),

        # 数据
        'financial_summary_df': fin_summary_df,
        'key_highlights': key_highlights,

        # 图表
        'share_performance_chart': chart_path,

        # 元数据
        'data_source_text': '公司财报, AKShare, 同花顺' if is_ashare else 'Company Filings, Yahoo Finance',
        'disclaimer_text': '',
    }

    # ── 7. 生成 PDF ──
    print("\n📄 Generating PDF...")
    pdf_path = os.path.join(output_dir, f"{ticker}_Annual_Report_FY{args.fyear}.pdf")
    generate_annual_report_pdf(pdf_path, report_data, theme_name=args.style)

    print(f"\n{'=' * 60}")
    print(f"✅ ANNUAL REPORT GENERATED!")
    print(f"{'=' * 60}")
    print(f"📁 Output: {pdf_path}")
    print(f"📝 Text sections: {output_dir}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
