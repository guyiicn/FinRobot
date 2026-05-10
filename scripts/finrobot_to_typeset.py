#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinRobot 输出 → typeset-engine 格式转换器 v2

对照 CICC 报告章节结构，完整提取 FinRobot 数据：
  一  投资摘要（核心观点 + KPI 卡片 + 评级）
  二  公司概况
  三  行业分析
  四  财务分析（含图表）
  五  同行可比公司对比（3张表 + 雷达图 + PE/PB图）
  六  估值分析
  七  风险提示
  八  投资建议

用法：
  python finrobot_to_typeset.py <analysis_dir> <company_name> <ticker> [theme]
"""

import json, csv, os, sys, re
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────

def read(path, default='', strip_markdown=True):
    """读取文本文件，默认去掉 Markdown 标题符号（#/##/###）"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read().strip()
        if strip_markdown:
            text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        return text
    return default


def read_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return default or {}


def _fmt(val, pattern, default='N/A'):
    if val is None:
        return default
    try:
        return pattern.format(val)
    except:
        return default


def parse_cn_num(s):
    """'3.5亿' → 3.5e8  '200万' → 2e6"""
    if s is None:
        return None
    s = str(s).strip()
    try:
        if '亿' in s:
            return float(s.replace('亿', '')) * 1e8
        if '万' in s:
            return float(s.replace('万', '')) * 1e4
        return float(s.replace(',', ''))
    except:
        return None


# ─────────────────────────────────────────────────────────────
# 一  投资摘要
# ─────────────────────────────────────────────────────────────

def build_investment_summary(d, company_name, ticker):
    """
    一 投资摘要
    - 核心观点（callout）
    - KPI 卡片（最新价/PE/PB/市值/净利率/ROE）
    - 评级 callout
    """
    children = []

    # 核心观点（tagline）
    tagline = read(d / 'tagline.txt')
    if tagline:
        children.append({'type': 'quote', 'content': tagline})

    # KPI 卡片
    profile = read_json(d / 'company_profile.json')
    comps   = read_json(d / 'comparables.json', [])
    main    = comps[0] if comps else {}

    kpi_items = []
    price = profile.get('price') or main.get('price')
    if price:
        kpi_items.append({'label': '最新价(元)', 'value': f'¥{price:.2f}'})
    pe = profile.get('pe_ratio') or main.get('pe_ratio')
    if pe:
        kpi_items.append({'label': 'PE(TTM)', 'value': f'{pe:.1f}x'})
    pb = profile.get('pb_ratio') or main.get('pb_ratio')
    if pb:
        kpi_items.append({'label': 'PB', 'value': f'{pb:.2f}x'})
    mc = profile.get('market_cap') or main.get('market_cap')
    if mc:
        kpi_items.append({'label': '市值(亿)', 'value': f'{mc/1e8:.1f}'})
    nm = main.get('net_margin')
    if nm:
        kpi_items.append({'label': '净利率', 'value': f'{nm:.1f}%'})
    roe = main.get('roe')
    if roe:
        kpi_items.append({'label': 'ROE', 'value': f'{roe:.1f}%'})

    if kpi_items:
        children.append({'type': 'kpi', 'columns': min(len(kpi_items), 6), 'metrics': kpi_items})

    # 评级（从 major_takeaways 中推断）
    takeaways = read(d / 'major_takeaways.txt').lower()
    if '买入' in takeaways or '增持' in takeaways:
        rating, kind = '综合评级：买入（Buy）', 'success'
    elif '卖出' in takeaways or '减持' in takeaways:
        rating, kind = '综合评级：卖出（Sell）', 'warn'
    else:
        rating, kind = '综合评级：谨慎观望（Hold）', 'info'
    children.append({'type': 'callout', 'content': rating, 'kind': kind})

    return {'type': 'heading', 'title': '一  投资摘要', 'level': 1, 'children': children}


# ─────────────────────────────────────────────────────────────
# 二  公司概况
# ─────────────────────────────────────────────────────────────

def build_company_overview(d):
    overview   = read(d / 'company_overview.txt')
    investment = read(d / 'investment_overview.txt')
    children = []
    if overview:
        children.append({'type': 'paragraph', 'content': overview})
    if investment:
        children.append({'type': 'heading', 'title': '投资亮点', 'level': 2,
                         'children': [{'type': 'paragraph', 'content': investment}]})
    return {'type': 'heading', 'title': '二  公司概况', 'level': 1, 'children': children}


# ─────────────────────────────────────────────────────────────
# 三  行业分析
# ─────────────────────────────────────────────────────────────

def build_industry_analysis(d):
    competitor = read(d / 'competitor_analysis.txt')
    news       = read(d / 'news_summary.txt')
    children   = []
    if competitor:
        children.append({'type': 'paragraph', 'content': competitor})
    if news:
        children.append({'type': 'heading', 'title': '近期资讯', 'level': 2,
                         'children': [{'type': 'paragraph', 'content': news}]})
    return {'type': 'heading', 'title': '三  行业分析', 'level': 1, 'children': children}


# ─────────────────────────────────────────────────────────────
# 四  财务分析
# ─────────────────────────────────────────────────────────────

def build_financial_analysis(d, charts_reg):
    """财务分析：财务摘要表 + 营收图 + EBITDA Margin 图"""
    children = []
    csv_path = d / 'financial_metrics_and_forecasts.csv'

    if not csv_path.exists():
        children.append({'type': 'paragraph', 'content': '财务数据暂不可用。'})
        return {'type': 'heading', 'title': '四  财务分析', 'level': 1, 'children': children}

    with open(csv_path, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    # 找可用年份列（实际年份 = 列名含 'A'，如 2022A 2023A）
    all_cols = rows[0].keys() if rows else []
    year_cols = [c for c in all_cols if c.endswith('A') and c != 'metrics']
    year_cols_recent = year_cols[-4:] if len(year_cols) > 4 else year_cols

    def row_for(metric_name):
        return next((r for r in rows if r.get('metrics','').strip() == metric_name), None)

    # 财务摘要表
    key_metrics = [
        ('营收', 'Revenue', lambda v: f'{float(v)/1e8:.1f}亿' if v and v not in ('None','N/A') else '—'),
        ('营收增速', 'Revenue Growth', lambda v: v if v and v not in ('None','N/A') else '—'),
        ('EBITDA', 'EBITDA', lambda v: f'{float(v)/1e8:.1f}亿' if v and v not in ('None','N/A') else '—'),
        ('EBITDA Margin', 'EBITDA Margin', lambda v: v if v and v not in ('None','N/A') else '—'),
        ('SG&A费率', 'SG&A Margin', lambda v: v if v and v not in ('None','N/A') else '—'),
        ('EPS(元)', 'EPS', lambda v: f'¥{float(v):.2f}' if v and v not in ('None','N/A','nan') else '—'),
    ]
    table_headers = ['指标'] + year_cols_recent
    table_rows = []
    for label, key, fmt in key_metrics:
        r = row_for(key)
        if r:
            row = [label] + [fmt(r.get(yr, '—')) for yr in year_cols_recent]
            table_rows.append(row)

    if table_rows:
        children.append({
            'type': 'table',
            'caption': '财务数据摘要',
            'headers': table_headers,
            'rows': table_rows
        })

    # 营收趋势图
    rev_row = row_for('Revenue')
    if rev_row:
        vals = []
        for yr in year_cols_recent:
            v = rev_row.get(yr)
            try:
                vals.append(round(float(v)/1e8, 1) if v and v not in ('None','N/A') else 0)
            except:
                vals.append(0)
        chart_id = 'revenue_trend'
        charts_reg.append({'id': chart_id, 'type': 'bar', 'data': {
            'title': '营收趋势（亿元）',
            'categories': year_cols_recent,
            'series': [{'name': '营收', 'values': vals}]
        }})
        children.append({'type': 'chart', 'chart_id': chart_id, 'caption': '营收趋势（亿元）'})

    # EBITDA Margin 趋势图
    ebitda_row = row_for('EBITDA Margin')
    if ebitda_row:
        vals = []
        for yr in year_cols_recent:
            v = ebitda_row.get(yr, '0')
            try:
                vals.append(float(str(v).replace('%', '')))
            except:
                vals.append(0)
        chart_id = 'ebitda_margin_trend'
        charts_reg.append({'id': chart_id, 'type': 'line', 'data': {
            'title': 'EBITDA Margin 趋势（%）',
            'categories': year_cols_recent,
            'series': [{'name': 'EBITDA Margin', 'values': vals}]
        }})
        children.append({'type': 'chart', 'chart_id': chart_id, 'caption': 'EBITDA Margin 趋势（%）'})

    return {'type': 'heading', 'title': '四  财务分析', 'level': 1, 'children': children}


# ─────────────────────────────────────────────────────────────
# 五  同行可比公司对比
# ─────────────────────────────────────────────────────────────

def build_peer_comparison(d, charts_reg):
    comp_path = d / 'comparables.json'
    if not comp_path.exists():
        return None

    with open(comp_path, 'r', encoding='utf-8') as f:
        comps = json.load(f)
    if not comps:
        return None

    names = [c.get('name') or c.get('ticker', '') for c in comps]
    hdrs  = ['指标'] + names

    def make_row(label, fn):
        row = [label]
        for c in comps:
            try:
                row.append(fn(c))
            except:
                row.append('N/A')
        return row

    # 表1：估值对比
    def ps(c):
        rev, mc = c.get('revenue'), c.get('market_cap')
        return f'{mc/rev:.2f}x' if rev and mc and rev > 0 else 'N/A'

    t1 = {
        'type': 'table',
        'caption': '① 估值对比（最新）',
        'headers': hdrs,
        'rows': [
            make_row('价格(元)',  lambda c: _fmt(c.get('price'),      '¥{:.2f}')),
            make_row('市值(亿)',  lambda c: _fmt(c.get('market_cap'), '{:.1f}') if c.get('market_cap') else 'N/A'),
            make_row('PE(TTM)',   lambda c: f"{c['pe_ratio']:.1f}x"  if c.get('pe_ratio') else '亏损/N/A'),
            make_row('PB',        lambda c: _fmt(c.get('pb_ratio'),   '{:.2f}x')),
            make_row('PS(市销率)',ps),
            make_row('EPS(元)',   lambda c: _fmt(c.get('eps'),        '{:.2f}')),
        ]
    }
    # 市值 /1e8
    for row in t1['rows']:
        if row[0] == '市值(亿)':
            row[1:] = [f'{c.get("market_cap")/1e8:.1f}' if c.get('market_cap') else 'N/A' for c in comps]

    # 表2：盈利能力
    def rev_fmt(c):
        v = c.get('revenue')
        return f'{v/1e8:.1f}' if v else 'N/A'
    def ni_fmt(c):
        v = c.get('net_income')
        return f'{v/1e8:.2f}' if v else 'N/A'

    t2 = {
        'type': 'table',
        'caption': '② 盈利能力（最新年度）',
        'headers': hdrs,
        'rows': [
            make_row('毛利率(%)',     lambda c: _fmt(c.get('gross_margin'),     '{:.1f}%')),
            make_row('净利率(%)',     lambda c: _fmt(c.get('net_margin'),       '{:.1f}%')),
            make_row('ROE(%)',        lambda c: _fmt(c.get('roe'),              '{:.1f}%')),
            make_row('营收增速(%)',   lambda c: _fmt(c.get('revenue_growth'),   '{:.1f}%')),
            make_row('净利润增速(%)', lambda c: _fmt(c.get('net_income_growth'),'{:.1f}%')),
            make_row('营收(亿)',      rev_fmt),
            make_row('净利润(亿)',    ni_fmt),
        ]
    }

    # 表3：财务健康 & 历史趋势
    all_years = set()
    for c in comps:
        for h in c.get('history', []):
            all_years.add(h.get('year', ''))
    years3 = sorted(all_years, reverse=True)[:3]

    t3_rows = [
        make_row('资产负债率(%)',   lambda c: _fmt(c.get('asset_liability_ratio'), '{:.1f}%')),
        make_row('每股经营现金流', lambda c: _fmt(c.get('eps_cfs'), '{:.2f}')),
    ]
    for yr in years3:
        t3_rows.append(make_row(f'ROE {yr}(%)',
            lambda c, y=yr: _fmt(next((h.get('roe') for h in c.get('history',[]) if h.get('year')==y), None), '{:.1f}%')))
    for yr in years3:
        t3_rows.append(make_row(f'毛利率 {yr}(%)',
            lambda c, y=yr: _fmt(next((h.get('gross_margin') for h in c.get('history',[]) if h.get('year')==y), None), '{:.1f}%')))

    t3 = {'type': 'table', 'caption': '③ 财务健康 & 历史趋势', 'headers': hdrs, 'rows': t3_rows}

    # 雷达图
    radar_id = 'comp_radar'
    charts_reg.append({
        'id': radar_id, 'type': 'radar',
        'data': {
            'title': '盈利能力雷达图',
            'categories': ['毛利率', '净利率', 'ROE', '营收增速', '净利润增速'],
            'series': [{
                'name': c.get('name') or c.get('ticker', ''),
                'values': [c.get('gross_margin') or 0, c.get('net_margin') or 0,
                           c.get('roe') or 0, c.get('revenue_growth') or 0,
                           c.get('net_income_growth') or 0]
            } for c in comps]
        }
    })

    # PE/PB 对比图
    pe_id = 'comp_pe'
    charts_reg.append({
        'id': pe_id, 'type': 'bar',
        'data': {
            'title': 'PE / PB 同行对比',
            'categories': names,
            'series': [
                {'name': 'PE(TTM)', 'values': [c.get('pe_ratio') or 0 for c in comps]},
                {'name': 'PB',      'values': [c.get('pb_ratio') or 0 for c in comps]},
            ]
        }
    })

    return {
        'type': 'heading',
        'title': '五  同行可比公司对比',
        'level': 1,
        'children': [
            t1,
            {'type': 'pagebreak'},
            t2, t3,
            {'type': 'chart', 'chart_id': radar_id, 'caption': '盈利能力雷达图（同行横向）'},
            {'type': 'chart', 'chart_id': pe_id,    'caption': 'PE/PB 同行估值对比'},
        ]
    }


# ─────────────────────────────────────────────────────────────
# 六  估值分析
# ─────────────────────────────────────────────────────────────

def build_valuation(d):
    text = read(d / 'valuation_overview.txt')
    children = []
    if text:
        children.append({'type': 'paragraph', 'content': text})

    # 从 sensitivity_analysis.json 补充置信区间
    sens = read_json(d / 'sensitivity_analysis.json')
    sens_md = read(d / 'sensitivity_summary.md', strip_markdown=True)
    if sens_md:
        children.append({'type': 'heading', 'title': '敏感性分析', 'level': 2,
                         'children': [{'type': 'paragraph', 'content': sens_md}]})

    # 催化剂分析
    cat_md = read(d / 'catalyst_summary.md', strip_markdown=True)
    if cat_md:
        children.append({'type': 'heading', 'title': '关键催化剂', 'level': 2,
                         'children': [{'type': 'paragraph', 'content': cat_md}]})

    return {'type': 'heading', 'title': '六  估值分析', 'level': 1, 'children': children}


# ─────────────────────────────────────────────────────────────
# 七  风险提示
# ─────────────────────────────────────────────────────────────

def build_risks(d):
    text = read(d / 'risks.txt')
    if not text:
        return None
    return {
        'type': 'heading', 'title': '七  风险提示', 'level': 1,
        'children': [
            {'type': 'callout', 'content': '以下风险因素可能对公司股价及基本面产生不利影响，投资者应予以关注。', 'kind': 'warn'},
            {'type': 'paragraph', 'content': text}
        ]
    }


# ─────────────────────────────────────────────────────────────
# 八  投资建议
# ─────────────────────────────────────────────────────────────

def build_recommendation(d):
    text = read(d / 'major_takeaways.txt')
    if not text:
        return None
    return {
        'type': 'heading', 'title': '八  投资建议', 'level': 1,
        'children': [{'type': 'paragraph', 'content': text}]
    }


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────

def convert(analysis_dir, company_name, ticker, theme='ms'):
    d = Path(analysis_dir)
    charts = []

    sections = []

    # 一  投资摘要
    sections.append(build_investment_summary(d, company_name, ticker))

    # 二  公司概况
    sec = build_company_overview(d)
    if sec['children']:
        sections.append(sec)

    # 三  行业分析
    sec = build_industry_analysis(d)
    if sec['children']:
        sections.append(sec)

    # 四  财务分析
    sections.append(build_financial_analysis(d, charts))

    # 五  同行可比公司对比
    sec = build_peer_comparison(d, charts)
    if sec:
        sections.append(sec)

    # 六  估值分析
    sec = build_valuation(d)
    if sec['children']:
        sections.append(sec)

    # 七  风险提示
    sec = build_risks(d)
    if sec:
        sections.append(sec)

    # 八  投资建议
    sec = build_recommendation(d)
    if sec:
        sections.append(sec)

    report = {
        'title':    f'{company_name}（{ticker}）股票研究报告',
        'title_en': f'{company_name} Equity Research Report',
        'author':   'FinRobot + typeset-engine',
        'date':     datetime.now().strftime('%Y-%m-%d'),
        'theme':    theme,
        'toc':      True,
        'charts':   charts,
        'sections': sections,
        'disclaimer': (
            '本报告由 FinRobot AI 财务分析平台生成，数据来源：同花顺（财务数据）、'
            '新浪财经（实时行情）、公司公告。仅供研究参考，不构成任何形式的投资建议。'
        )
    }

    return report


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python finrobot_to_typeset.py <analysis_dir> <company_name> <ticker> [theme]")
        sys.exit(1)

    analysis_dir = sys.argv[1]
    company_name = sys.argv[2]
    ticker       = sys.argv[3]
    theme        = sys.argv[4] if len(sys.argv) > 4 else 'ms'

    report = convert(analysis_dir, company_name, ticker, theme)

    output_path = f"/tmp/typeset_{ticker.replace('.', '_')}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"✅ 转换完成: {output_path}")
    print(f"📊 {len(report['sections'])} 个章节, {len(report['charts'])} 个图表")
    print(f"OUTPUT_PATH={output_path}")
