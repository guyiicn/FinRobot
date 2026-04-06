#!/usr/bin/env python
# coding: utf-8
"""
年度报告 PDF 生成器 — 支持 default/cicc 主题，中英双语。
与 professional_pdf_report.py（股票研究报告）并行，不修改后者。
"""

import os
import re
from datetime import datetime
from typing import Dict, Optional

import pandas as pd
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, KeepTogether, HRFlowable,
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from modules.style_themes import get_theme, Theme

# ── 字体注册 ──
try:
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
except:
    pass

# ── 页面参数 ──
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CW = PAGE_W - 2 * MARGIN  # content width


def _font(theme: Theme):
    return theme.fonts.regular


def _hex(val):
    return colors.HexColor(val)


# ── 双语标题 ──
TITLES = {
    'zh': {
        'annual_report': '年度报告',
        'key_highlights': '核心财务指标',
        'business_overview': '业务概况',
        'operating_results': '经营业绩',
        'financial_data': '财务数据',
        'financial_position': '财务状况',
        'cash_flow_analysis': '现金流分析',
        'risk_assessment': '风险评估',
        'competitive_analysis': '竞争分析',
        'outlook': '前景展望',
        'disclaimer': '免责声明',
        'metric': '指标',
    },
    'en': {
        'annual_report': 'Annual Report',
        'key_highlights': 'Key Financial Highlights',
        'business_overview': 'Business Overview',
        'operating_results': 'Operating Results',
        'financial_data': 'Financial Data',
        'financial_position': 'Financial Position',
        'cash_flow_analysis': 'Cash Flow Analysis',
        'risk_assessment': 'Risk Assessment',
        'competitive_analysis': 'Competitive Analysis',
        'outlook': 'Outlook',
        'disclaimer': 'Disclaimer',
        'metric': 'Metric',
    },
}


def _clean_md(text: str) -> str:
    """去除 markdown 格式符号"""
    if not text:
        return ''
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = text.replace('**', '').replace('__', '')
    return text.strip()


def generate_annual_report_pdf(
    output_path: str,
    data: dict,
    theme_name: str = 'default',
) -> str:
    """
    生成年度报告 PDF。

    Args:
        output_path: PDF 输出路径
        data: 报告数据字典
        theme_name: 'default' 或 'cicc'

    Returns:
        生成的 PDF 文件路径
    """
    theme = get_theme(theme_name)
    font = _font(theme)
    lang = data.get('language', 'zh')
    T = TITLES.get(lang, TITLES['en'])
    is_zh = lang == 'zh'
    cs = '¥' if is_zh else '$'

    company = data.get('company_name', '')
    ticker = data.get('ticker', '')
    fy = data.get('fiscal_year', '')

    primary = _hex(theme.colors.primary)
    dark = _hex(theme.colors.text_dark)
    medium = _hex(theme.colors.text_medium)
    light_bg = _hex(theme.colors.text_light)
    separator_c = _hex(theme.colors.separator)

    # ── 样式 ──
    s_title = ParagraphStyle('AR_Title', fontName=font, fontSize=theme.fonts.section_title,
                              textColor=primary, alignment=TA_LEFT, spaceBefore=14, spaceAfter=8, leading=22)
    s_h2 = ParagraphStyle('AR_H2', fontName=font, fontSize=theme.fonts.heading2,
                           textColor=primary, alignment=TA_LEFT, spaceBefore=10, spaceAfter=5, leading=16)
    s_body = ParagraphStyle('AR_Body', fontName=font, fontSize=theme.fonts.body,
                             textColor=dark, alignment=TA_JUSTIFY, spaceAfter=5, leading=14)
    s_bullet = ParagraphStyle('AR_Bullet', fontName=font, fontSize=theme.fonts.body,
                               textColor=dark, alignment=TA_LEFT, leftIndent=15, spaceAfter=4, leading=14)
    s_caption = ParagraphStyle('AR_Caption', fontName=font, fontSize=theme.fonts.caption,
                                textColor=medium, alignment=TA_LEFT, spaceAfter=3, leading=10)
    s_cover_title = ParagraphStyle('AR_CoverTitle', fontName=font, fontSize=26,
                                    textColor=primary, alignment=TA_CENTER, spaceAfter=6, leading=32)
    s_cover_sub = ParagraphStyle('AR_CoverSub', fontName=font, fontSize=14,
                                  textColor=medium, alignment=TA_CENTER, spaceAfter=4)

    def sep():
        thick = 1.0 if theme.name == 'cicc' else 0.5
        return HRFlowable(width="100%", thickness=thick, color=separator_c, spaceBefore=6, spaceAfter=6)

    # ── 文档 ──
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            topMargin=20 * mm, bottomMargin=18 * mm,
                            leftMargin=MARGIN, rightMargin=MARGIN)

    elements = []

    # ================================================================
    # 封面区域
    # ================================================================
    elements.append(Spacer(1, 15 * mm))
    # 顶部红/蓝线
    elements.append(HRFlowable(width="100%", thickness=2.5, color=primary, spaceBefore=0, spaceAfter=8))
    elements.append(Paragraph(T['annual_report'], s_cover_sub))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(company, s_cover_title))
    elements.append(Paragraph(f"{ticker} | {data.get('sector', '')} | FY{fy}", s_cover_sub))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(data.get('report_date', datetime.now().strftime('%B %Y')), s_cover_sub))
    elements.append(HRFlowable(width="100%", thickness=2.5, color=primary, spaceBefore=8, spaceAfter=10))

    # ── 核心指标卡片 ──
    highlights = data.get('key_highlights', {})
    if highlights:
        elements.append(Paragraph(T['key_highlights'], s_h2))
        kv_data = [[k, str(v)] for k, v in highlights.items()]
        # 两列显示
        left = kv_data[:len(kv_data) // 2 + 1]
        right = kv_data[len(kv_data) // 2 + 1:]
        while len(right) < len(left):
            right.append(['', ''])

        col_w = [50 * mm, 35 * mm]
        lt = Table(left, colWidths=col_w)
        rt = Table(right, colWidths=col_w)
        metric_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), light_bg),
            ('FONTNAME', (0, 0), (0, -1), font),
            ('FONTNAME', (1, 0), (1, -1), font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), medium),
            ('TEXTCOLOR', (1, 0), (1, -1), primary),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, _hex(theme.colors.table_border)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
        lt.setStyle(metric_style)
        rt.setStyle(metric_style)
        layout = Table([[lt, rt]], colWidths=[CW / 2, CW / 2])
        layout.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        elements.append(layout)
        elements.append(Spacer(1, 6 * mm))

    # ================================================================
    # 业务概况
    # ================================================================
    elements.append(Paragraph(T['business_overview'], s_title))
    elements.append(sep())
    for para in _clean_md(data.get('business_overview', '')).split('\n'):
        para = para.strip()
        if para:
            elements.append(Paragraph(para, s_body))

    # 股价走势图
    chart_path = data.get('share_performance_chart', '')
    if chart_path and os.path.exists(chart_path):
        elements.append(Spacer(1, 4 * mm))
        try:
            img = Image(chart_path, width=CW * 0.7, height=CW * 0.35)
            elements.append(img)
            elements.append(Paragraph("数据来源：公司财报" if is_zh else "Source: Company Filings", s_caption))
        except:
            pass

    # ================================================================
    # 经营业绩
    # ================================================================
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(T['operating_results'], s_title))
    elements.append(sep())
    for para in _clean_md(data.get('operating_results', '')).split('\n'):
        para = para.strip()
        if para:
            elements.append(Paragraph(para, s_body))

    # ── 财务数据表 ──
    fin_df = data.get('financial_summary_df')
    if fin_df is not None and not fin_df.empty:
        elements.append(Spacer(1, 5 * mm))
        elements.append(Paragraph(T['financial_data'], s_h2))

        # 构建表格数据
        headers = [T['metric']] + list(fin_df.columns)
        rows = [headers]
        for idx, row in fin_df.iterrows():
            r = [str(idx)]
            for v in row:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    r.append('N/A')
                elif isinstance(v, (int, float)):
                    absv = abs(v)
                    if absv >= 1e9:
                        r.append(f"{cs}{v / 1e9:,.1f}B")
                    elif absv >= 1e6:
                        r.append(f"{cs}{v / 1e6:,.1f}M")
                    else:
                        r.append(str(v))
                else:
                    r.append(str(v))
            rows.append(r)

        n_cols = len(rows[0])
        first_w = 38 * mm
        other_w = (CW - first_w) / (n_cols - 1) if n_cols > 1 else CW
        col_widths = [first_w] + [other_w] * (n_cols - 1)
        table = Table(rows, colWidths=col_widths)

        # 根据主题选择表格样式
        if theme.table.style == 'three_line':
            border_c = primary
            tbl_style = TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), font), ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 0), (-1, 0), light_bg),
                ('TEXTCOLOR', (0, 0), (-1, 0), dark),
                ('FONTNAME', (0, 1), (-1, -1), font), ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TEXTCOLOR', (0, 1), (-1, -1), dark),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('LINEABOVE', (0, 0), (-1, 0), 1.5, border_c),
                ('LINEBELOW', (0, 0), (-1, 0), 1.5, border_c),
                ('LINEBELOW', (0, -1), (-1, -1), 1.5, border_c),
                ('LINEBELOW', (0, 1), (-1, -2), 0.3, _hex(theme.colors.table_border)),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        else:
            tbl_style = TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), font), ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 0), (-1, 0), primary),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 1), (-1, -1), font), ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TEXTCOLOR', (0, 1), (-1, -1), dark),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _hex('#f8f9fa')]),
                ('LINEBELOW', (0, 0), (-1, 0), 1.5, primary),
                ('LINEBELOW', (0, 1), (-1, -2), 0.5, _hex('#dee2e6')),
                ('LINEBELOW', (0, -1), (-1, -1), 1, primary),
                ('BOX', (0, 0), (-1, -1), 0.5, _hex('#dee2e6')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        table.setStyle(tbl_style)
        elements.append(table)

    # ================================================================
    # 财务状况
    # ================================================================
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(T['financial_position'], s_title))
    elements.append(sep())
    for para in _clean_md(data.get('financial_position', '')).split('\n'):
        para = para.strip()
        if para:
            elements.append(Paragraph(para, s_body))

    # ================================================================
    # 现金流分析
    # ================================================================
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(T['cash_flow_analysis'], s_h2))
    for para in _clean_md(data.get('cash_flow_analysis', '')).split('\n'):
        para = para.strip()
        if para:
            elements.append(Paragraph(para, s_body))

    # ================================================================
    # 风险评估
    # ================================================================
    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph(T['risk_assessment'], s_title))
    elements.append(sep())
    risks = _clean_md(data.get('risk_assessment', ''))
    for line in risks.split('\n'):
        line = line.strip()
        if line:
            line = line.lstrip('•-▪▫◆◇0123456789.）)').strip()
            if line:
                elements.append(Paragraph(f"▪ {line}", s_bullet))

    # ================================================================
    # 竞争分析
    # ================================================================
    comp = data.get('competitive_analysis', '')
    if comp:
        elements.append(Spacer(1, 6 * mm))
        elements.append(Paragraph(T['competitive_analysis'], s_title))
        elements.append(sep())
        for para in _clean_md(comp).split('\n'):
            para = para.strip()
            if para:
                elements.append(Paragraph(para, s_body))

    # ================================================================
    # 前景展望
    # ================================================================
    outlook = data.get('outlook', '')
    if outlook:
        elements.append(Spacer(1, 6 * mm))
        elements.append(Paragraph(T['outlook'], s_h2))
        for para in _clean_md(outlook).split('\n'):
            para = para.strip()
            if para:
                elements.append(Paragraph(para, s_body))

    # ================================================================
    # 免责声明
    # ================================================================
    elements.append(Spacer(1, 10 * mm))
    elements.append(sep())
    elements.append(Paragraph(T['disclaimer'], ParagraphStyle(
        'AR_Disc_Title', fontName=font, fontSize=9, textColor=dark, alignment=TA_LEFT, spaceBefore=4, spaceAfter=3)))
    disc = data.get('disclaimer_text', '')
    if not disc:
        disc = ("本报告仅供参考，不构成任何投资建议。报告中所含信息仅供收件人使用，"
                "未经书面同意不得向第三方传播或分发。过往业绩不代表未来表现。") if is_zh else (
                "This report is for informational purposes only and does not constitute investment advice. "
                "Past performance is not indicative of future results.")
    elements.append(Paragraph(disc, ParagraphStyle(
        'AR_Disc', fontName=font, fontSize=7, textColor=medium, alignment=TA_JUSTIFY, leading=9)))

    src = data.get('data_source_text', '公司财报, AKShare' if is_zh else 'Company Filings')
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph(
        f"{'数据来源' if is_zh else 'Data Source'}: {src}", s_caption))
    elements.append(Paragraph(
        f"{'报告生成时间' if is_zh else 'Generated'}: {datetime.now().strftime('%Y-%m-%d %H:%M')} | FinRobot Annual Report",
        s_caption))

    # ── 页眉页脚 ──
    header_line_c = _hex(theme.colors.header_line)
    header_line_w = 1.0 if theme.name == 'cicc' else 0.5

    def _header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont(font, 8)
        canvas_obj.setFillColor(medium)
        canvas_obj.drawString(MARGIN, PAGE_H - 12 * mm, f"{company} ({ticker})")
        label = '年度报告' if is_zh else 'Annual Report'
        canvas_obj.drawRightString(PAGE_W - MARGIN, PAGE_H - 12 * mm, label)
        canvas_obj.setStrokeColor(header_line_c)
        canvas_obj.setLineWidth(header_line_w)
        canvas_obj.line(MARGIN, PAGE_H - 14 * mm, PAGE_W - MARGIN, PAGE_H - 14 * mm)
        canvas_obj.drawCentredString(PAGE_W / 2, 10 * mm, f"Page {doc_obj.page}")
        canvas_obj.restoreState()

    # ── 构建 ──
    doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)
    print(f"✅ Annual report PDF: {output_path}")
    return output_path
