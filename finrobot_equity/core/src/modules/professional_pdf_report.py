#!/usr/bin/env python
# coding: utf-8
"""
专业股票研究报告PDF生成器 - 投行风格
特点：
1. 分析文本与相关图表并排展示
2. 根据数据量动态生成页面
3. 专业的排版和视觉设计
"""

import os
import io
import base64
from datetime import datetime
import pytz
from typing import Dict, List, Optional, Any, Tuple

EASTERN_TZ = pytz.timezone('America/New_York')

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm, inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether, HRFlowable, ListFlowable, ListItem
)
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Line, Rect
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ── 主题系统 ──
from modules.style_themes import get_theme, Theme, AVAILABLE_THEMES

# ── 注册默认中文字体 (CID方式) ──
try:
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    _CJK_FONT = 'STSong-Light'
    _CJK_FONT_BOLD = 'STSong-Light'
    print(f"  📝 [professional] 中文字体: STSong-Light (CID)")
except Exception as e:
    print(f"  ⚠️ CID 字体注册失败: {e}，回退 Helvetica")
    _CJK_FONT = 'Helvetica'
    _CJK_FONT_BOLD = 'Helvetica-Bold'

# ── 当前活动主题（模块级别，由 apply_theme() 设置）──
_active_theme: Optional[Theme] = None

def apply_theme(theme_name: str = 'default'):
    """应用主题：更新模块级字体和颜色。"""
    global _active_theme, _CJK_FONT, _CJK_FONT_BOLD
    _active_theme = get_theme(theme_name)
    _CJK_FONT = _active_theme.fonts.regular
    _CJK_FONT_BOLD = _active_theme.fonts.bold
    # 更新 Colors 类
    Colors.NAVY = colors.HexColor(_active_theme.colors.primary)
    Colors.GOLD = colors.HexColor(_active_theme.colors.secondary)
    Colors.DARK_GRAY = colors.HexColor(_active_theme.colors.text_dark)
    Colors.MEDIUM_GRAY = colors.HexColor(_active_theme.colors.text_medium)
    Colors.LIGHT_GRAY = colors.HexColor(_active_theme.colors.text_light)
    Colors.POSITIVE = colors.HexColor(_active_theme.colors.positive)
    Colors.NEGATIVE = colors.HexColor(_active_theme.colors.negative)
    Colors.NEUTRAL = colors.HexColor(_active_theme.colors.neutral)
    print(f"  📝 [professional] 主题: {_active_theme.display_name}, 字体: {_CJK_FONT}")

import pandas as pd
import numpy as np


# =============================================================================
# 专业配色方案 (Investment Bank Style)
# =============================================================================
class Colors:
    """投行风格配色"""
    # 主题色
    NAVY = colors.HexColor('#1a365d')      # 深海军蓝 - 主标题、重点
    GOLD = colors.HexColor('#c9a227')      # 金色 - 强调、图表
    DARK_GRAY = colors.HexColor('#2d3748') # 深灰 - 正文
    MEDIUM_GRAY = colors.HexColor('#718096') # 中灰 - 次要文本
    LIGHT_GRAY = colors.HexColor('#e2e8f0') # 浅灰 - 背景、分隔线
    WHITE = colors.white
    
    # 图表配色
    CHART_PRIMARY = '#1a365d'
    CHART_SECONDARY = '#c9a227'
    CHART_TERTIARY = '#4a5568'
    CHART_GRID = '#e2e8f0'
    
    # 状态色
    POSITIVE = colors.HexColor('#38a169')  # 绿色 - 正面
    NEGATIVE = colors.HexColor('#e53e3e')  # 红色 - 负面
    NEUTRAL = colors.HexColor('#718096')   # 灰色 - 中性


class Layout:
    """页面布局参数"""
    PAGE_WIDTH, PAGE_HEIGHT = A4
    MARGIN_TOP = 20 * mm
    MARGIN_BOTTOM = 18 * mm
    MARGIN_LEFT = 18 * mm
    MARGIN_RIGHT = 18 * mm
    
    CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    CONTENT_HEIGHT = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    
    # 两栏布局 - 确保左右宽度完全相等
    COL_GAP = 8 * mm
    COL_WIDTH = (CONTENT_WIDTH - COL_GAP) / 2  # 严格平分


# =============================================================================
# 样式定义
# =============================================================================
def create_styles() -> Dict[str, ParagraphStyle]:
    """创建所有段落样式"""
    styles = {}
    
    # 封面主标题
    styles['CoverTitle'] = ParagraphStyle(
        'CoverTitle',
        fontName=_CJK_FONT_BOLD,
        fontSize=32,
        textColor=Colors.WHITE,
        alignment=TA_CENTER,
        spaceAfter=8,
        leading=38,
    )
    
    # 封面副标题
    styles['CoverSubtitle'] = ParagraphStyle(
        'CoverSubtitle',
        fontName=_CJK_FONT,
        fontSize=16,
        textColor=Colors.GOLD,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    
    # 章节标题 (大)
    styles['SectionTitle'] = ParagraphStyle(
        'SectionTitle',
        fontName=_CJK_FONT_BOLD,
        fontSize=18,
        textColor=Colors.NAVY,
        alignment=TA_LEFT,
        spaceBefore=16,
        spaceAfter=10,
        leading=22,
    )
    
    # 子标题
    styles['Heading2'] = ParagraphStyle(
        'Heading2',
        fontName=_CJK_FONT_BOLD,
        fontSize=13,
        textColor=Colors.NAVY,
        alignment=TA_LEFT,
        spaceBefore=12,
        spaceAfter=6,
        leading=16,
    )
    
    # 小标题
    styles['Heading3'] = ParagraphStyle(
        'Heading3',
        fontName=_CJK_FONT_BOLD,
        fontSize=11,
        textColor=Colors.DARK_GRAY,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=4,
        leading=14,
    )
    
    # 正文
    styles['Body'] = ParagraphStyle(
        'Body',
        fontName=_CJK_FONT,
        fontSize=9.5,
        textColor=Colors.DARK_GRAY,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        leading=13,
    )
    
    # 正文加粗
    styles['BodyBold'] = ParagraphStyle(
        'BodyBold',
        fontName=_CJK_FONT_BOLD,
        fontSize=9.5,
        textColor=Colors.DARK_GRAY,
        alignment=TA_LEFT,
        spaceAfter=6,
        leading=13,
    )
    
    # 要点列表
    styles['BulletPoint'] = ParagraphStyle(
        'BulletPoint',
        fontName=_CJK_FONT,
        fontSize=9.5,
        textColor=Colors.DARK_GRAY,
        alignment=TA_LEFT,
        leftIndent=15,
        spaceAfter=4,
        leading=13,
    )
    
    # 高亮文本框
    styles['Highlight'] = ParagraphStyle(
        'Highlight',
        fontName=_CJK_FONT,
        fontSize=10,
        textColor=Colors.NAVY,
        alignment=TA_LEFT,
        spaceAfter=4,
        leading=14,
    )
    
    # 小字说明
    styles['Caption'] = ParagraphStyle(
        'Caption',
        fontName=_CJK_FONT,
        fontSize=8,
        textColor=Colors.MEDIUM_GRAY,
        alignment=TA_LEFT,
        spaceAfter=3,
        leading=10,
    )
    
    # 页眉
    styles['Header'] = ParagraphStyle(
        'Header',
        fontName=_CJK_FONT,
        fontSize=8,
        textColor=Colors.MEDIUM_GRAY,
        alignment=TA_RIGHT,
    )
    
    # 页脚
    styles['Footer'] = ParagraphStyle(
        'Footer',
        fontName=_CJK_FONT,
        fontSize=7,
        textColor=Colors.MEDIUM_GRAY,
        alignment=TA_CENTER,
    )
    
    # 评级标签
    styles['Rating'] = ParagraphStyle(
        'Rating',
        fontName=_CJK_FONT_BOLD,
        fontSize=14,
        textColor=Colors.POSITIVE,
        alignment=TA_CENTER,
    )
    
    # 大数字
    styles['BigNumber'] = ParagraphStyle(
        'BigNumber',
        fontName=_CJK_FONT_BOLD,
        fontSize=24,
        textColor=Colors.NAVY,
        alignment=TA_CENTER,
        leading=28,
    )
    
    # 表格标题
    styles['TableTitle'] = ParagraphStyle(
        'TableTitle',
        fontName=_CJK_FONT_BOLD,
        fontSize=10,
        textColor=Colors.NAVY,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=4,
    )
    
    return styles


# =============================================================================
# 表格样式
# =============================================================================
def create_data_table_style():
    """创建数据表格样式 — 根据主题自动选择风格"""
    t = _active_theme

    # 通用设置
    base = [
        ('FONTNAME', (0, 0), (-1, 0), _CJK_FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), t.fonts.table_header if t else 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), _CJK_FONT),
        ('FONTSIZE', (0, 1), (-1, -1), t.fonts.table_body if t else 8),
        ('TEXTCOLOR', (0, 1), (-1, -1), Colors.DARK_GRAY),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    if t and t.table.style == 'three_line':
        # ── 三线表（中金风格）──
        header_bg = colors.HexColor(t.colors.table_header_bg)
        header_fg = colors.HexColor(t.colors.table_header_fg)
        border_c = colors.HexColor(t.colors.primary)
        row_line_c = colors.HexColor(t.colors.table_border)

        base += [
            ('BACKGROUND', (0, 0), (-1, 0), header_bg),
            ('TEXTCOLOR', (0, 0), (-1, 0), header_fg),
            # 顶部粗线
            ('LINEABOVE', (0, 0), (-1, 0), t.table.header_line_width, border_c),
            # 表头下分隔线
            ('LINEBELOW', (0, 0), (-1, 0), t.table.header_line_width, border_c),
            # 底部粗线
            ('LINEBELOW', (0, -1), (-1, -1), t.table.bottom_line_width, border_c),
        ]
        # 行间细线
        if t.table.row_lines:
            base.append(('LINEBELOW', (0, 1), (-1, -2), t.table.row_line_width, row_line_c))
    else:
        # ── 默认边框风格 ──
        base += [
            ('BACKGROUND', (0, 0), (-1, 0), Colors.NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), Colors.WHITE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [Colors.WHITE, colors.HexColor('#f8f9fa')]),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, Colors.NAVY),
            ('LINEBELOW', (0, 1), (-1, -2), 0.5, colors.HexColor('#dee2e6')),
            ('LINEBELOW', (0, -1), (-1, -1), 1, Colors.NAVY),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ]

    return TableStyle(base)


def create_key_metrics_style():
    """创建关键指标表格样式 - 有分割线"""
    t = _active_theme
    bg = colors.HexColor(t.colors.text_light) if t else colors.HexColor('#f8f9fa')
    val_color = colors.HexColor(t.colors.primary) if t else Colors.NAVY
    label_color = colors.HexColor(t.colors.text_medium) if t else Colors.MEDIUM_GRAY
    line_color = colors.HexColor(t.colors.table_border) if t else colors.HexColor('#dee2e6')

    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('FONTNAME', (0, 0), (0, -1), _CJK_FONT),
        ('FONTNAME', (1, 0), (1, -1), _CJK_FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), label_color),
        ('TEXTCOLOR', (1, 0), (1, -1), val_color),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        # 每行分割线
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, line_color),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])


# =============================================================================
# 辅助函数
# =============================================================================
def clean_markdown_symbols(text):
    """清理markdown符号"""
    if not text:
        return text
    
    import re
    # 去除 ## 和 ### 开头的符号
    text = re.sub(r'^#{2,3}\s+', '', text, flags=re.MULTILINE)
    # 去除 _** 开头的符号
    text = re.sub(r'_\*\*\s*', '', text)
    # 去除 ** 包围的文本（保留文本内容）
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # 去除单独的 **
    text = re.sub(r'\*\*', '', text)
    
    return text


def format_number(value, format_type='auto', currency_symbol=None):
    """格式化数字 - 智能处理大数字和精度

    Args:
        currency_symbol: 货币符号，如 '$' 或 '¥'。默认 '$'。
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 'N/A'

    cs = currency_symbol or '$'

    # 处理字符串（如 "41.8%"）
    if isinstance(value, str):
        # 如果已经是百分比格式，直接返回
        if '%' in value:
            return value
        # 尝试解析为数字
        try:
            clean_val = value.replace(',', '').replace('$', '').replace('¥', '').replace('%', '')
            num = float(clean_val)
            # 如果原字符串没有特殊格式，走数字格式化
        except:
            return value
    else:
        try:
            num = float(value)
        except:
            return str(value)

    # 数字格式化
    if format_type == 'currency':
        return f"{cs}{num:,.2f}"
    elif format_type == 'percent':
        return f"{num:.1f}%"
    elif format_type == 'ratio':
        return f"{num:.2f}x"
    elif format_type == 'billions':
        return f"{cs}{num/1e9:,.1f}B"
    elif format_type == 'millions':
        return f"{cs}{num/1e6:,.1f}M"
    elif format_type == 'auto':
        # 智能判断数字类型
        abs_num = abs(num)

        # 超大数字 - 使用 B/M/K 简化
        if abs_num >= 1e12:
            return f"{cs}{num/1e12:,.1f}T"
        elif abs_num >= 1e9:
            return f"{cs}{num/1e9:,.1f}B"
        elif abs_num >= 1e6:
            return f"{cs}{num/1e6:,.1f}M"
        elif abs_num >= 1e3:
            return f"{num:,.0f}"  # 千级数字，无小数
        # 小数 (如 PE ratio, 百分比)
        elif abs_num < 100 and abs_num > 0:
            # 限制精度到2位小数
            return f"{num:.2f}"
        elif abs_num == 0:
            return "0"
        else:
            return f"{num:,.2f}"
    
    return str(value)


def create_separator():
    """创建分隔线"""
    t = _active_theme
    sep_color = colors.HexColor(t.colors.separator) if t else Colors.LIGHT_GRAY
    sep_thick = 1.0 if (t and t.name == 'cicc') else 0.5
    return HRFlowable(
        width="100%",
        thickness=sep_thick,
        color=sep_color,
        spaceBefore=8, 
        spaceAfter=8
    )


def load_image_from_base64(base64_str, width, height):
    """从Base64加载图片"""
    try:
        if base64_str.startswith('data:image'):
            img_data = base64_str.split(',')[1]
        else:
            img_data = base64_str
        img_bytes = base64.b64decode(img_data)
        img_buffer = io.BytesIO(img_bytes)
        return Image(img_buffer, width=width, height=height)
    except Exception as e:
        return None


# =============================================================================
# 专业报告生成器
# =============================================================================
class ProfessionalEquityReport:
    """专业股票研究报告生成器"""
    
    def __init__(self, output_path: str, data: Dict[str, Any]):
        self.output_path = output_path
        self.data = data
        self.styles = create_styles()
        self.elements = []
        self.page_number = 0

        # 语言检测
        import re
        _sample = str(data.get('tagline', '')) + str(data.get('company_overview', ''))
        self.is_zh = bool(re.search(r'[\u4e00-\u9fff]', _sample))
        self.currency_symbol = '¥' if self.is_zh else '$'

        # 双语标题
        if self.is_zh:
            self.T = {
                'EQUITY_RESEARCH': '股票研究报告',
                'Key Metrics Snapshot': '核心指标概览',
                'Investment Thesis': '投资论点',
                'Company Overview': '公司概况',
                'Investment Overview': '投资概述',
                'Valuation Analysis': '估值分析',
                'Revenue & EBITDA Performance': '营收与EBITDA表现',
                'Earnings & Valuation Metrics': '盈利与估值指标',
                'Key Figures:': '关键数据：',
                'Risk Factors': '风险因素',
                'Competitive Analysis': '竞争分析',
                'Key Points': '核心要点',
                'News Summary': '新闻动态',
                'Financial Data': '财务数据',
                'Disclaimer': '免责声明',
                'Financial Analysis': '财务分析',
                'Peer Comparison': '同行对比',
                'Competitive Landscape': '竞争格局',
                'Key Takeaways': '核心要点',
                'Recent News & Events': '近期新闻与事件',
                'Sensitivity Analysis': '敏感性分析',
                'Key Catalysts': '关键催化剂',
                'Forecast Confidence Intervals': '预测置信区间',
                'Upcoming Catalysts': '即将到来的催化剂',
                'EV/EBITDA Peer Comparison': 'EV/EBITDA 同行对比',
                'Peer comparison data not available.': '暂无同行对比数据。',
            }
        else:
            self.T = {
                'EQUITY_RESEARCH': 'EQUITY RESEARCH',
                'Key Metrics Snapshot': 'Key Metrics Snapshot',
                'Investment Thesis': 'Investment Thesis',
                'Company Overview': 'Company Overview',
                'Investment Overview': 'Investment Overview',
                'Valuation Analysis': 'Valuation Analysis',
                'Revenue & EBITDA Performance': 'Revenue & EBITDA Performance',
                'Earnings & Valuation Metrics': 'Earnings & Valuation Metrics',
                'Key Figures:': 'Key Figures:',
                'Risk Factors': 'Risk Factors',
                'Competitive Analysis': 'Competitive Analysis',
                'Key Points': 'Key Points',
                'News Summary': 'News Summary',
                'Financial Data': 'Financial Data',
                'Disclaimer': 'Disclaimer',
            }
        
        # 创建文档
        self.doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            topMargin=Layout.MARGIN_TOP,
            bottomMargin=Layout.MARGIN_BOTTOM,
            leftMargin=Layout.MARGIN_LEFT,
            rightMargin=Layout.MARGIN_RIGHT,
        )
        
        # 公司信息
        self.ticker = data.get('company_ticker', 'TICK')
        self.company_name = data.get('company_name_full', 'Company')
    
    # =========================================================================
    # 第1页：封面
    # =========================================================================
    def build_cover_page(self):
        """构建封面页"""
        # 封面内容 - 减少间距使内容更紧凑
        cover_elements = []
        cover_elements.append(Spacer(1, 12*mm))
        cover_elements.append(Paragraph(self.T["EQUITY_RESEARCH"], self.styles['CoverSubtitle']))
        cover_elements.append(Spacer(1, 4*mm))
        cover_elements.append(Paragraph(self.company_name.upper(), self.styles['CoverTitle']))
        cover_elements.append(Spacer(1, 3*mm))
        cover_elements.append(Paragraph(f"{self.ticker} | {self.data.get('sector', 'Technology')}", self.styles['CoverSubtitle']))
        cover_elements.append(Spacer(1, 12*mm))
        
        # 评级和目标价
        rating = self.data.get('rating', 'N/A')
        target = self.data.get('target_price', 'N/A')
        price = self.data.get('share_price', 'N/A')
        
        t = _active_theme
        _cover_text_c = colors.HexColor(t.colors.cover_text) if t else Colors.WHITE
        _cover_accent_c = colors.HexColor(t.colors.cover_accent) if t else Colors.GOLD

        rating_color = Colors.POSITIVE if rating in ['Buy', 'Outperform', 'Overweight'] else (
            Colors.NEGATIVE if rating in ['Sell', 'Underperform', 'Underweight'] else _cover_accent_c
        )

        # 评级框
        rating_style = ParagraphStyle('RatingBox', fontName=_CJK_FONT_BOLD, fontSize=20,
                                      textColor=rating_color, alignment=TA_CENTER)
        cover_elements.append(Paragraph(f"Rating: {rating}", rating_style))
        cover_elements.append(Spacer(1, 3*mm))

        price_style = ParagraphStyle('PriceBox', fontName=_CJK_FONT, fontSize=14,
                                     textColor=_cover_text_c, alignment=TA_CENTER)
        cover_elements.append(Paragraph(f"Current: {price} | Target: {target}", price_style))
        cover_elements.append(Spacer(1, 8*mm))

        # 日期
        date_style = ParagraphStyle('DateStyle', fontName=_CJK_FONT, fontSize=11,
                                    textColor=Colors.MEDIUM_GRAY, alignment=TA_CENTER)
        cover_elements.append(Paragraph(self.data.get('report_date', datetime.now(EASTERN_TZ).strftime('%B %Y')), date_style))
        cover_elements.append(Spacer(1, 8*mm))
        
        # 嵌入封面内容 - 居中对齐
        inner_table = Table([[cover_elements]], colWidths=[Layout.CONTENT_WIDTH])
        inner_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        
        # 封面背景 - 增加高度到 105mm
        t = _active_theme
        cover_bg_c = colors.HexColor(t.colors.cover_bg) if t else Colors.NAVY
        cover_bg = Table([[inner_table]], colWidths=[Layout.CONTENT_WIDTH], rowHeights=[105*mm])
        cover_bg.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), cover_bg_c),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        
        self.elements.append(cover_bg)
        self.elements.append(Spacer(1, 8*mm))
        
        # 关键指标摘要
        self.elements.append(Paragraph(self.T["Key Metrics Snapshot"], self.styles['Heading2']))
        self.elements.append(Spacer(1, 3*mm))
        
        # 格式化指标值 - 保留 2 位小数
        def format_metric(value, is_percentage=False):
            if value == 'N/A' or value is None:
                return 'N/A'
            if isinstance(value, str):
                # 如果已经是字符串，尝试解析
                if '%' in value:
                    try:
                        num = float(value.replace('%', '').strip())
                        return f"{num:.2f}%"
                    except:
                        return value
                try:
                    num = float(value)
                except:
                    return value
            else:
                num = value
            
            if is_percentage:
                return f"{num:.2f}%"
            else:
                return f"{num:.2f}"
        
        if self.is_zh:
            metrics_data = [
                ['总市值', self.data.get('market_cap', 'N/A')],
                ['市盈率(动)', format_metric(self.data.get('fwd_pe', 'N/A'))],
                ['市净率', format_metric(self.data.get('pb_ratio', 'N/A'))],
                ['ROE', format_metric(self.data.get('roe', 'N/A'), is_percentage=True)],
                ['股息率', format_metric(self.data.get('dividend_yield', 'N/A'), is_percentage=True)],
                ['52周区间', self.data.get('52w_range', 'N/A')],
            ]
        else:
            metrics_data = [
                ['Market Cap', self.data.get('market_cap', 'N/A')],
                ['P/E (Fwd)', format_metric(self.data.get('fwd_pe', 'N/A'))],
                ['P/B Ratio', format_metric(self.data.get('pb_ratio', 'N/A'))],
                ['ROE', format_metric(self.data.get('roe', 'N/A'), is_percentage=True)],
                ['Dividend Yield', format_metric(self.data.get('dividend_yield', 'N/A'), is_percentage=True)],
                ['52W Range', self.data.get('52w_range', 'N/A')],
            ]
        
        # 分两列显示指标 - 居中对齐
        left_metrics = metrics_data[:3]
        right_metrics = metrics_data[3:]
        
        col_widths = [50*mm, 35*mm]  # 统一列宽
        
        left_table = Table(left_metrics, colWidths=col_widths)
        left_table.setStyle(create_key_metrics_style())
        
        right_table = Table(right_metrics, colWidths=col_widths)
        right_table.setStyle(create_key_metrics_style())
        
        # 居中布局
        total_table_width = sum(col_widths) * 2 + 10*mm  # 两表 + 间距
        side_padding = (Layout.CONTENT_WIDTH - total_table_width) / 2
        
        metrics_layout = Table(
            [[left_table, Spacer(10*mm, 1), right_table]], 
            colWidths=[sum(col_widths), 10*mm, sum(col_widths)]
        )
        metrics_layout.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        
        self.elements.append(metrics_layout)
        self.elements.append(Spacer(1, 6*mm))
        
        # 投资亮点
        tagline = self.data.get('tagline', '')
        if tagline:
            self.elements.append(Paragraph(self.T["Investment Thesis"], self.styles['Heading2']))
            # 高亮框
            tagline = clean_markdown_symbols(tagline)  # 清理markdown符号
            highlight_data = [[Paragraph(tagline, self.styles['Highlight'])]]
            highlight_table = Table(highlight_data, colWidths=[Layout.CONTENT_WIDTH - 10*mm])
            highlight_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
                ('BOX', (0, 0), (-1, -1), 1, Colors.GOLD),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ]))
            self.elements.append(highlight_table)
    
    # =========================================================================
    # 公司概述部分
    # =========================================================================
    def build_company_overview_section(self):
        """构建公司概述部分 - 自然流动"""
        self.elements.append(PageBreak())  # 封面后分页
        
        self.elements.append(Paragraph(self.T["Company Overview"], self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        overview = self.data.get('company_overview', '')
        if overview:
            overview = clean_markdown_symbols(overview)  # 清理markdown符号
            # 分段显示
            paragraphs = overview.split('\n')
            for para in paragraphs:
                para = para.strip()
                if para:
                    self.elements.append(Paragraph(para, self.styles['Body']))
                    self.elements.append(Spacer(1, 2*mm))
        
        self.elements.append(Spacer(1, 6*mm))
        
        # 投资观点
        investment = self.data.get('investment_overview', '')
        if investment:
            self.elements.append(Paragraph(self.T["Investment Overview"], self.styles['Heading2']))
            self.elements.append(Spacer(1, 2*mm))
            
            investment = clean_markdown_symbols(investment)  # 清理markdown符号
            paragraphs = investment.split('\n')
            for para in paragraphs:
                para = para.strip()
                if para:
                    self.elements.append(Paragraph(para, self.styles['Body']))
                    self.elements.append(Spacer(1, 2*mm))
    
    # =========================================================================
    # 财务分析部分 - 图文并排
    # =========================================================================
    def build_financial_analysis_section(self):
        """构建财务分析部分 - 自然流动"""
        self.elements.append(Spacer(1, 8*mm))
        
        self.elements.append(Paragraph(self.T.get("Financial Analysis", "财务分析"), self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        # 固定尺寸 - 确保左右一致
        fixed_width = 82 * mm
        fixed_height = 52 * mm
        
        # -------------------- Revenue & EBITDA 分析 --------------------
        self.elements.append(Paragraph(self.T["Revenue & EBITDA Performance"], self.styles['Heading2']))
        self.elements.append(Spacer(1, 2*mm))
        
        revenue_analysis = self._generate_revenue_analysis()
        revenue_chart = self.data.get('revenue_chart_path', '')
        
        left_content = [Paragraph(revenue_analysis, self.styles['Body'])]
        
        analysis_df = self.data.get('analysis_df')
        if analysis_df is not None and not analysis_df.empty:
            key_data = self._extract_key_metrics(analysis_df, ['Revenue', 'EBITDA', 'Revenue Growth'])
            if key_data:
                left_content.append(Spacer(1, 2*mm))
                left_content.append(Paragraph(self.T["Key Figures:"], self.styles['BodyBold']))
                for metric, value in key_data.items():
                    left_content.append(Paragraph(f"• {metric}: {value}", self.styles['BulletPoint']))
        
        right_content = []
        if revenue_chart and revenue_chart.startswith('data:image'):
            img = load_image_from_base64(revenue_chart, fixed_width, fixed_height)
            if img:
                right_content.append(img)
                right_content.append(Paragraph("数据来源：公司财报" if self.is_zh else "Source: Company Filings", self.styles['Caption']))
        
        if right_content:
            layout = Table([[left_content, right_content]], 
                          colWidths=[fixed_width + 2*mm, fixed_width + 2*mm])
            layout.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ]))
            # 使用 KeepTogether 防止图表分页
            self.elements.append(KeepTogether([layout]))
        else:
            for item in left_content:
                self.elements.append(item)
        
        self.elements.append(Spacer(1, 6*mm))
        
        # -------------------- EPS & Valuation 分析 --------------------
        eps_section = []  # 收集整个部分的元素
        eps_section.append(Paragraph(self.T["Earnings & Valuation Metrics"], self.styles['Heading2']))
        eps_section.append(Spacer(1, 2*mm))
        
        eps_analysis = self._generate_eps_analysis()
        eps_chart = self.data.get('eps_pe_chart_path', '')
        
        left_content = [Paragraph(eps_analysis, self.styles['Body'])]
        
        if analysis_df is not None and not analysis_df.empty:
            key_data = self._extract_key_metrics(analysis_df, ['EPS', 'PE Ratio'])
            if key_data:
                left_content.append(Spacer(1, 2*mm))
                left_content.append(Paragraph(self.T["Key Figures:"], self.styles['BodyBold']))
                for metric, value in key_data.items():
                    left_content.append(Paragraph(f"• {metric}: {value}", self.styles['BulletPoint']))
        
        right_content = []
        if eps_chart and eps_chart.startswith('data:image'):
            img = load_image_from_base64(eps_chart, fixed_width, fixed_height)
            if img:
                right_content.append(img)
                right_content.append(Paragraph("数据来源：公司财报" if self.is_zh else "Source: Company Filings", self.styles['Caption']))
        
        if right_content:
            layout = Table([[left_content, right_content]], 
                          colWidths=[fixed_width + 2*mm, fixed_width + 2*mm])
            layout.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ]))
            eps_section.append(layout)
        else:
            eps_section.extend(left_content)
        
        # 使用 KeepTogether 防止分页
        self.elements.append(KeepTogether(eps_section))
    
    # =========================================================================
    # 估值分析部分
    # =========================================================================
    def build_valuation_section(self):
        """构建估值分析部分 - 自然流动"""
        self.elements.append(Spacer(1, 8*mm))
        
        self.elements.append(Paragraph(self.T["Valuation Analysis"], self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        valuation = self.data.get('valuation_overview', '')
        if valuation:
            valuation = clean_markdown_symbols(valuation)  # 清理markdown符号
            paragraphs = valuation.split('\n')
            for para in paragraphs:
                para = para.strip()
                if para:
                    self.elements.append(Paragraph(para, self.styles['Body']))
                    self.elements.append(Spacer(1, 2*mm))
        
        self.elements.append(Spacer(1, 6*mm))
        
        # 同行对比
        self.elements.append(Paragraph(self.T.get("Peer Comparison", "同行对比"), self.styles['Heading2']))
        self.elements.append(Spacer(1, 3*mm))
        
        peer_df = self.data.get('peer_comparison_df')
        ev_chart = self.data.get('ev_ebitda_chart_path', '')
        
        # 固定尺寸 - 确保左右一致
        fixed_width = 82 * mm  # 固定宽度
        fixed_height = 50 * mm  # 固定高度
        
        # 左侧：同行对比表格
        left_content = []
        if peer_df is not None and not peer_df.empty:
            table = self._create_peer_table_fixed(peer_df, fixed_width)
            if table:
                left_content.append(table)
        else:
            left_content.append(Paragraph(self.T.get("Peer comparison data not available.", "Peer comparison data not available."), self.styles['Body']))
        
        # 右侧：图表
        right_content = []
        if ev_chart and ev_chart.startswith('data:image'):
            img = load_image_from_base64(ev_chart, fixed_width, fixed_height)
            if img:
                right_content.append(img)
                right_content.append(Paragraph(self.T.get("EV/EBITDA Peer Comparison", "EV/EBITDA Peer Comparison"), self.styles['Caption']))
        
        if left_content and right_content:
            layout = Table([[left_content, right_content]], 
                          colWidths=[fixed_width + 2*mm, fixed_width + 2*mm])
            layout.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ]))
            # 使用 KeepTogether 防止表格和图表分页
            self.elements.append(KeepTogether([layout]))
        else:
            for item in left_content:
                self.elements.append(item)
    
    # =========================================================================
    # 竞争与风险部分
    # =========================================================================
    def build_competition_risk_section(self):
        """构建竞争分析与风险部分 - 自然流动"""
        self.elements.append(Spacer(1, 8*mm))
        
        # 竞争分析
        self.elements.append(Paragraph(self.T.get("Competitive Landscape", "竞争格局"), self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        competitor = self.data.get('competitor_analysis', '')
        if competitor:
            competitor = clean_markdown_symbols(competitor)  # 清理markdown符号
            paragraphs = competitor.split('\n')
            for para in paragraphs:
                para = para.strip()
                if para:
                    self.elements.append(Paragraph(para, self.styles['Body']))
                    self.elements.append(Spacer(1, 2*mm))
        
        self.elements.append(Spacer(1, 5*mm))
        
        # 风险因素
        self.elements.append(Paragraph(self.T["Risk Factors"], self.styles['Heading2']))
        
        risks = self.data.get('risks', '')
        if risks:
            risks = clean_markdown_symbols(risks)  # 清理markdown符号
            risk_lines = risks.strip().split('\n')
            for line in risk_lines:  # 不限制数量
                line = line.strip()
                if line:
                    # 清理已有的项目符号（• - 或 • 或 -）
                    line = line.lstrip('•').lstrip('-').strip()
                    if line:
                        self.elements.append(Paragraph(f"▪ {line}", self.styles['BulletPoint']))
        
        self.elements.append(Spacer(1, 5*mm))
        
        # 主要要点
        takeaways = self.data.get('major_takeaways', '')
        if takeaways:
            self.elements.append(Paragraph(self.T.get("Key Takeaways", "核心要点"), self.styles['Heading2']))
            
            takeaways = clean_markdown_symbols(takeaways)  # 清理markdown符号
            takeaway_lines = takeaways.strip().split('\n')
            for line in takeaway_lines:  # 不限制数量
                line = line.strip()
                if line:
                    self.elements.append(Paragraph(f"✓ {line}", self.styles['BulletPoint']))
    
    # =========================================================================
    # 新闻分析部分
    # =========================================================================
    def build_news_section(self):
        """构建新闻分析部分"""
        news_summary = self.data.get('news_summary', '')
        enhanced_news = self.data.get('enhanced_news', {})
        retail_sentiment = self.data.get('retail_sentiment', {})
        company_news = self.data.get('company_news', [])
        
        # 如果没有新闻数据，跳过
        if not news_summary and not enhanced_news and not retail_sentiment:
            return
        
        self.elements.append(Spacer(1, 8*mm))
        self.elements.append(Paragraph(self.T.get("Recent News & Events", "近期新闻与事件"), self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        # 新闻摘要
        if news_summary:
            self.elements.append(Paragraph(self.T["News Summary"], self.styles['Heading2']))
            self.elements.append(Spacer(1, 2*mm))
            news_summary = clean_markdown_symbols(news_summary)  # 清理markdown符号
            paragraphs = news_summary.split('\n')
            for para in paragraphs:  # 不限制段落数
                para = para.strip()
                if para:
                    self.elements.append(Paragraph(para, self.styles['Body']))
                    self.elements.append(Spacer(1, 2*mm))
        
        # 增强新闻分析
        if enhanced_news:
            if enhanced_news.get('sentiment_summary'):
                sentiment = enhanced_news['sentiment_summary']
                overall = sentiment.get('overall', 'neutral')
                sentiment_color = Colors.POSITIVE if overall == 'positive' else (
                    Colors.NEGATIVE if overall == 'negative' else Colors.NEUTRAL
                )
                sentiment_style = ParagraphStyle(
                    'SentimentStyle', fontName=_CJK_FONT_BOLD, fontSize=10,
                    textColor=sentiment_color, alignment=TA_LEFT
                )
                self.elements.append(Spacer(1, 3*mm))
                self.elements.append(Paragraph(f"Overall Sentiment: {overall.upper()}", sentiment_style))
            
            # 新闻分类
            if enhanced_news.get('categories'):
                self.elements.append(Spacer(1, 3*mm))
                self.elements.append(Paragraph("News by Category:", self.styles['BodyBold']))
                for cat, count in enhanced_news['categories'].items():
                    self.elements.append(Paragraph(f"• {cat}: {count} articles", self.styles['BulletPoint']))

        if retail_sentiment:
            self.elements.append(Spacer(1, 4 * mm))
            self.elements.append(Paragraph("Retail Sentiment Insights", self.styles['Heading2']))

            summary_items = []
            if retail_sentiment.get('average_buzz') is not None:
                summary_items.append(f"Average Buzz: {retail_sentiment['average_buzz']}/100")
            if retail_sentiment.get('bullish_avg') is not None:
                summary_items.append(f"Bullish Avg: {retail_sentiment['bullish_avg']}%")
            summary_items.append(f"Source Alignment: {retail_sentiment.get('source_alignment', 'No coverage')}")
            summary_items.append(f"Coverage: {retail_sentiment.get('coverage', '0/3')}")

            for item in summary_items:
                self.elements.append(Paragraph(f"• {item}", self.styles['BulletPoint']))

            for source in retail_sentiment.get('sources', []):
                if not source.get('has_data'):
                    continue
                bullish_text = (
                    f"{source['bullish_pct']}%"
                    if source.get('bullish_pct') is not None
                    else 'N/A'
                )
                self.elements.append(
                    Paragraph(
                        f"{source['label']}: Buzz {source['buzz_score']}/100, "
                        f"Bullish {bullish_text}, "
                        f"{source['activity_label']} {source['activity_value']}, "
                        f"Trend {source['trend']}",
                        self.styles['Body'],
                    )
                )
                self.elements.append(Spacer(1, 1.5 * mm))
        
        # Recent Headlines 已禁用 - 不显示单条新闻标题列表
        # if company_news and len(company_news) > 0:
        #     self.elements.append(Spacer(1, 4*mm))
        #     self.elements.append(Paragraph("Recent Headlines:", self.styles['Heading3']))
        #     for news in company_news:
        #         title = news.get('title', news.get('headline', ''))
        #         date = news.get('publishedDate', news.get('date', ''))[:10] if news.get('publishedDate') or news.get('date') else ''
        #         if title:
        #             news_text = f"• [{date}] {title}" if date else f"• {title}"
        #             self.elements.append(Paragraph(news_text, self.styles['BulletPoint']))
    
    # =========================================================================
    # 敏感性分析部分
    # =========================================================================
    def build_sensitivity_section(self):
        """构建敏感性分析部分"""
        sensitivity = self.data.get('sensitivity_analysis', {})
        
        if not sensitivity:
            return
        
        self.elements.append(Spacer(1, 8*mm))
        self.elements.append(Paragraph(self.T.get("Sensitivity Analysis", "敏感性分析"), self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        # 敏感性摘要
        if sensitivity.get('summary'):
            summary = clean_markdown_symbols(sensitivity['summary'])  # 清理markdown符号
            paragraphs = summary.split('\n')
            for para in paragraphs:  # 不限制段落数
                para = para.strip()
                if para:
                    self.elements.append(Paragraph(para, self.styles['Body']))
                    self.elements.append(Spacer(1, 2*mm))
        
        # 置信区间
        if sensitivity.get('confidence_intervals'):
            self.elements.append(Spacer(1, 3*mm))
            ci_title = self.T.get("Forecast Confidence Intervals", "Forecast Confidence Intervals")
            confidence_level = "95%"
            self.elements.append(Paragraph(f"{ci_title} ({confidence_level}):", self.styles['Heading3']))
            currency = '¥' if self.is_zh else '$'
            for metric, ci in sensitivity['confidence_intervals'].items():
                if ci:
                    low = ci.get('lower', ci.get('low', None))
                    high = ci.get('upper', ci.get('high', None))
                    if low is not None and high is not None:
                        low_str = f"{currency}{low/1e9:,.1f}B"
                        high_str = f"{currency}{high/1e9:,.1f}B"
                    else:
                        low_str = 'N/A'
                        high_str = 'N/A'
                    self.elements.append(Paragraph(f"• {metric}: {low_str} - {high_str}", self.styles['BulletPoint']))
    
    # =========================================================================
    # 催化剂分析部分
    # =========================================================================
    def build_catalyst_section(self):
        """构建催化剂分析部分"""
        catalyst = self.data.get('catalyst_analysis', {})
        
        if not catalyst:
            return
        
        self.elements.append(Spacer(1, 8*mm))
        self.elements.append(Paragraph(self.T.get("Key Catalysts", "关键催化剂"), self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        # 催化剂摘要
        if catalyst.get('summary'):
            summary = clean_markdown_symbols(catalyst['summary'])  # 清理markdown符号
            paragraphs = summary.split('\n')
            for para in paragraphs:  # 不限制段落数
                para = para.strip()
                if para:
                    self.elements.append(Paragraph(para, self.styles['Body']))
                    self.elements.append(Spacer(1, 2*mm))
        
        # 顶级催化剂列表
        top_catalysts = catalyst.get('top_catalysts', [])
        if top_catalysts:
            self.elements.append(Spacer(1, 3*mm))
            self.elements.append(Paragraph(self.T.get("Upcoming Catalysts", "Upcoming Catalysts") + ":", self.styles['Heading3']))
            
            for cat in top_catalysts:  # 不限制数量
                event_type = cat.get('event_type', 'Event')
                description = cat.get('description', '')
                sentiment = cat.get('sentiment', 'neutral')
                impact = cat.get('impact_level', cat.get('impact', 'medium'))
                
                # 根据情绪设置颜色
                if sentiment == 'positive':
                    prefix = "▲"
                    color = Colors.POSITIVE
                elif sentiment == 'negative':
                    prefix = "▼"
                    color = Colors.NEGATIVE
                else:
                    prefix = "●"
                    color = Colors.NEUTRAL
                
                catalyst_style = ParagraphStyle(
                    'CatalystItem', fontName=_CJK_FONT, fontSize=9,
                    textColor=color, alignment=TA_LEFT, leftIndent=15
                )
                
                if self.is_zh:
                    impact_zh = {'high': '高', 'medium': '中', 'low': '低'}.get(impact, impact)
                    text = f"{prefix} [{event_type.upper()}] {description}（影响：{impact_zh}）"
                else:
                    text = f"{prefix} [{event_type.upper()}] {description} (Impact: {impact})"
                self.elements.append(Paragraph(text, catalyst_style))
                self.elements.append(Spacer(1, 1*mm))
        
        # 分类催化剂
        categorized = catalyst.get('categorized', {})
        if categorized:
            self.elements.append(Spacer(1, 4*mm))
            
            # 正面催化剂
            if categorized.get('positive'):
                self.elements.append(Paragraph("Positive Catalysts:", self.styles['BodyBold']))
                for item in categorized['positive']:  # 不限制数量
                    desc = item.get('description', '')
                    if desc:
                        self.elements.append(Paragraph(f"✓ {desc}", self.styles['BulletPoint']))
            
            # 负面风险
            if categorized.get('negative'):
                self.elements.append(Spacer(1, 2*mm))
                self.elements.append(Paragraph("Risk Factors:", self.styles['BodyBold']))
                for item in categorized['negative']:  # 不限制数量
                    desc = item.get('description', '')
                    if desc:
                        self.elements.append(Paragraph(f"⚠ {desc}", self.styles['BulletPoint']))
    
    # =========================================================================
    # 高级图表分析部分
    # =========================================================================
    def build_advanced_charts_section(self):
        """构建高级图表分析部分 - 包含配文说明"""
        # 检查是否有高级图表
        stock_price_chart = self.data.get('stock_price_chart_path', '')
        technical_chart = self.data.get('technical_indicators_path', '')
        radar_chart = self.data.get('financial_radar_path', '')
        cashflow_chart = self.data.get('cash_flow_chart_path', '')
        
        has_advanced_charts = any([stock_price_chart, technical_chart, radar_chart, cashflow_chart])
        
        if not has_advanced_charts:
            return
        
        self.elements.append(Spacer(1, 8*mm))
        self.elements.append(Paragraph("Technical & Advanced Analysis", self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        fixed_width = 82 * mm
        fixed_height = 52 * mm
        
        # -------------------- 股价走势分析 --------------------
        if stock_price_chart and stock_price_chart.startswith('data:image'):
            stock_section = []
            stock_section.append(Paragraph("Stock Price Performance", self.styles['Heading2']))
            stock_section.append(Spacer(1, 2*mm))
            
            # 配文分析
            stock_analysis = self._generate_stock_price_analysis()
            left_content = [Paragraph(stock_analysis, self.styles['Body'])]
            
            # 添加关键指标
            left_content.append(Spacer(1, 2*mm))
            left_content.append(Paragraph("Key Technical Levels:", self.styles['BodyBold']))
            left_content.append(Paragraph("• MA20: Short-term trend indicator", self.styles['BulletPoint']))
            left_content.append(Paragraph("• MA50: Medium-term support/resistance", self.styles['BulletPoint']))
            left_content.append(Paragraph("• MA200: Long-term trend direction", self.styles['BulletPoint']))
            
            # 图表
            right_content = []
            img = load_image_from_base64(stock_price_chart, fixed_width, fixed_height)
            if img:
                right_content.append(img)
                right_content.append(Paragraph("Stock Price with Moving Averages", self.styles['Caption']))
            
            if right_content:
                layout = Table([[left_content, right_content]], 
                              colWidths=[fixed_width + 2*mm, fixed_width + 2*mm])
                layout.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                stock_section.append(layout)
            else:
                stock_section.extend(left_content)
            
            self.elements.append(KeepTogether(stock_section))
            self.elements.append(Spacer(1, 6*mm))
        
        # -------------------- 技术指标分析 --------------------
        if technical_chart and technical_chart.startswith('data:image'):
            tech_section = []
            tech_section.append(Paragraph("Technical Indicators", self.styles['Heading2']))
            tech_section.append(Spacer(1, 2*mm))
            
            # 配文分析
            tech_analysis = self._generate_technical_analysis()
            left_content = [Paragraph(tech_analysis, self.styles['Body'])]
            
            # RSI和MACD说明
            left_content.append(Spacer(1, 2*mm))
            left_content.append(Paragraph("Indicator Interpretation:", self.styles['BodyBold']))
            left_content.append(Paragraph("• RSI > 70: Overbought condition", self.styles['BulletPoint']))
            left_content.append(Paragraph("• RSI < 30: Oversold condition", self.styles['BulletPoint']))
            left_content.append(Paragraph("• MACD crossover: Momentum signal", self.styles['BulletPoint']))
            
            # 图表
            right_content = []
            img = load_image_from_base64(technical_chart, fixed_width, fixed_height)
            if img:
                right_content.append(img)
                right_content.append(Paragraph("RSI & MACD Technical Indicators", self.styles['Caption']))
            
            if right_content:
                layout = Table([[left_content, right_content]], 
                              colWidths=[fixed_width + 2*mm, fixed_width + 2*mm])
                layout.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                tech_section.append(layout)
            else:
                tech_section.extend(left_content)
            
            self.elements.append(KeepTogether(tech_section))
            self.elements.append(Spacer(1, 6*mm))
        
        # -------------------- 财务比率雷达图 --------------------
        if radar_chart and radar_chart.startswith('data:image'):
            radar_section = []
            radar_section.append(Paragraph("Financial Ratio Analysis", self.styles['Heading2']))
            radar_section.append(Spacer(1, 2*mm))
            
            # 配文分析
            radar_analysis = self._generate_radar_analysis()
            left_content = [Paragraph(radar_analysis, self.styles['Body'])]
            
            # 比率说明
            left_content.append(Spacer(1, 2*mm))
            left_content.append(Paragraph("Key Ratios Explained:", self.styles['BodyBold']))
            left_content.append(Paragraph("• ROE: Return on shareholder equity", self.styles['BulletPoint']))
            left_content.append(Paragraph("• ROA: Asset utilization efficiency", self.styles['BulletPoint']))
            left_content.append(Paragraph("• Margins: Profitability indicators", self.styles['BulletPoint']))
            
            # 图表
            right_content = []
            img = load_image_from_base64(radar_chart, fixed_width, fixed_height)
            if img:
                right_content.append(img)
                right_content.append(Paragraph("Financial Ratio Radar Chart", self.styles['Caption']))
            
            if right_content:
                layout = Table([[left_content, right_content]], 
                              colWidths=[fixed_width + 2*mm, fixed_width + 2*mm])
                layout.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                radar_section.append(layout)
            else:
                radar_section.extend(left_content)
            
            self.elements.append(KeepTogether(radar_section))
            self.elements.append(Spacer(1, 6*mm))
        
        # -------------------- 现金流分析 --------------------
        if cashflow_chart and cashflow_chart.startswith('data:image'):
            cf_section = []
            cf_section.append(Paragraph("Cash Flow Analysis", self.styles['Heading2']))
            cf_section.append(Spacer(1, 2*mm))
            
            # 配文分析
            cf_analysis = self._generate_cashflow_analysis()
            left_content = [Paragraph(cf_analysis, self.styles['Body'])]
            
            # 现金流说明
            left_content.append(Spacer(1, 2*mm))
            left_content.append(Paragraph("Cash Flow Components:", self.styles['BodyBold']))
            left_content.append(Paragraph("• Operating CF: Core business cash generation", self.styles['BulletPoint']))
            left_content.append(Paragraph("• Investing CF: Capital expenditure & investments", self.styles['BulletPoint']))
            left_content.append(Paragraph("• Financing CF: Debt & equity transactions", self.styles['BulletPoint']))
            
            # 图表
            right_content = []
            img = load_image_from_base64(cashflow_chart, fixed_width, fixed_height)
            if img:
                right_content.append(img)
                right_content.append(Paragraph("Cash Flow Statement Analysis", self.styles['Caption']))
            
            if right_content:
                layout = Table([[left_content, right_content]], 
                              colWidths=[fixed_width + 2*mm, fixed_width + 2*mm])
                layout.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                cf_section.append(layout)
            else:
                cf_section.extend(left_content)
            
            self.elements.append(KeepTogether(cf_section))
    
    def _generate_stock_price_analysis(self) -> str:
        """生成股价走势分析配文"""
        return (
            f"{self.company_name}'s stock price performance is analyzed using multiple moving averages "
            f"to identify trend direction and potential support/resistance levels. The chart displays "
            f"the 20-day, 50-day, and 200-day moving averages alongside daily closing prices. "
            f"Volume analysis provides insight into trading activity and potential price momentum. "
            f"Investors should monitor crossover signals between moving averages as potential entry/exit indicators."
        )
    
    def _generate_technical_analysis(self) -> str:
        """生成技术指标分析配文"""
        return (
            f"Technical analysis for {self.company_name} incorporates momentum indicators including "
            f"the Relative Strength Index (RSI) and Moving Average Convergence Divergence (MACD). "
            f"RSI measures the speed and magnitude of price movements, with readings above 70 suggesting "
            f"overbought conditions and below 30 indicating oversold conditions. MACD provides trend-following "
            f"momentum signals through the relationship between two exponential moving averages."
        )
    
    def _generate_radar_analysis(self) -> str:
        """生成财务比率雷达图分析配文"""
        return (
            f"The financial ratio radar chart provides a multi-dimensional view of {self.company_name}'s "
            f"financial health across key metrics including profitability, efficiency, and leverage ratios. "
            f"This visualization enables quick comparison against industry benchmarks and historical performance. "
            f"Stronger performance is indicated by larger coverage area on the radar chart, while gaps "
            f"highlight areas requiring management attention or further analysis."
        )
    
    def _generate_cashflow_analysis(self) -> str:
        """生成现金流分析配文"""
        return (
            f"{self.company_name}'s cash flow analysis examines the three primary components of cash movement: "
            f"operating, investing, and financing activities. Strong operating cash flow indicates healthy "
            f"core business performance, while investing activities reflect capital allocation decisions. "
            f"Financing cash flows show the company's approach to capital structure management. "
            f"The net cash flow trend provides insight into overall liquidity and financial flexibility."
        )
    
    # =========================================================================
    # 财务数据附录
    # =========================================================================
    def build_financial_appendix(self):
        """构建财务数据附录"""
        self.elements.append(Spacer(1, 8*mm))
        
        self.elements.append(Paragraph(self.T["Financial Data"], self.styles['SectionTitle']))
        self.elements.append(create_separator())
        
        # 财务摘要表
        financial_df = self.data.get('financial_summary_df')
        if financial_df is not None and not financial_df.empty:
            table_title = "利润表摘要" if self.is_zh else "Income Statement Summary"
            self.elements.append(Paragraph(table_title, self.styles['TableTitle']))
            table = self._create_financial_table(financial_df)
            if table:
                self.elements.append(table)
            self.elements.append(Spacer(1, 5*mm))
        
        # 信用指标表
        credit_df = self.data.get('credit_cashflow_df')
        if credit_df is not None and not credit_df.empty:
            credit_title = "信用与现金流指标" if self.is_zh else "Credit & Cash Flow Metrics"
            self.elements.append(Paragraph(credit_title, self.styles['TableTitle']))
            table = self._create_financial_table(credit_df)
            if table:
                self.elements.append(table)
    
    # =========================================================================
    # 免责声明页
    # =========================================================================
    def build_disclaimer_page(self):
        """构建免责声明"""
        self.elements.append(Spacer(1, 10*mm))
        self.elements.append(create_separator())
        
        disclaimer_header = "免责声明" if self.is_zh else "DISCLAIMER"
        self.elements.append(Paragraph(disclaimer_header, self.styles['Heading3']))
        self.elements.append(Spacer(1, 3*mm))

        if self.is_zh:
            default_disclaimer = (
                "本报告仅供参考，不构成任何投资建议。报告中的信息来源被认为是可靠的，"
                "但其准确性无法保证。过往业绩不代表未来表现。"
                "投资者在做出任何投资决策前，应进行独立的尽职调查。"
            )
        else:
            default_disclaimer = (
                "This report is for informational purposes only and does not constitute investment advice. "
                "The information contained herein has been obtained from sources believed to be reliable, "
                "but its accuracy cannot be guaranteed. Past performance is not indicative of future results. "
                "Investors should conduct their own due diligence before making any investment decisions."
            )
        disclaimer = self.data.get('disclaimer_text', default_disclaimer)
        
        disclaimer_style = ParagraphStyle(
            'Disclaimer',
            fontName=_CJK_FONT,
            fontSize=7.5,
            textColor=Colors.MEDIUM_GRAY,
            alignment=TA_JUSTIFY,
            leading=10,
        )
        
        self.elements.append(Paragraph(disclaimer, disclaimer_style))
        
        self.elements.append(Spacer(1, 5*mm))
        
        # 数据来源
        if self.is_zh:
            source_text = f"数据来源：{self.data.get('data_source_text', '公司财报, AKShare')}"
        else:
            source_text = f"Data Source: {self.data.get('data_source_text', 'Company Filings, FMP API')}"
        self.elements.append(Paragraph(source_text, self.styles['Caption']))

        # 报告信息
        if self.is_zh:
            report_info = f"报告生成时间：{datetime.now(EASTERN_TZ).strftime('%Y-%m-%d %H:%M')} | {self.data.get('research_source', 'AI4Finance FinRobot')}"
        else:
            report_info = f"Report Generated: {datetime.now(EASTERN_TZ).strftime('%Y-%m-%d %H:%M')} ET | {self.data.get('research_source', 'AI4Finance FinRobot')}"
        self.elements.append(Paragraph(report_info, self.styles['Caption']))
    
    # =========================================================================
    # 辅助方法
    # =========================================================================
    def _generate_revenue_analysis(self) -> str:
        """生成收入分析文本"""
        analysis_df = self.data.get('analysis_df')
        if analysis_df is None or analysis_df.empty:
            if self.is_zh:
                return "暂无营收与EBITDA分析数据。"
            return "Revenue and EBITDA analysis data is not available for detailed commentary."

        try:
            years = [col for col in analysis_df.columns if col.endswith('A')][-3:]

            revenue_row = analysis_df[analysis_df['metrics'] == 'Revenue']
            ebitda_row = analysis_df[analysis_df['metrics'] == 'EBITDA']
            growth_row = analysis_df[analysis_df['metrics'] == 'Revenue Growth']

            latest_year = years[-1] if years else ''

            if self.is_zh:
                text = f"{self.company_name}展现出"

                if not growth_row.empty and latest_year:
                    growth = growth_row[latest_year].values[0]
                    if isinstance(growth, str) and '%' in growth:
                        growth_val = float(growth.replace('%', ''))
                    else:
                        growth_val = float(growth) if not pd.isna(growth) else 0

                    if growth_val > 10:
                        text += f"强劲的营收增长（{latest_year[:4]}年同比增长{growth_val:.1f}%），"
                    elif growth_val > 0:
                        text += f"稳健的营收增长（{latest_year[:4]}年同比增长{growth_val:.1f}%），"
                    else:
                        text += "承压的营收表现，"

                text += "公司持续扩大市场份额。"

                if not ebitda_row.empty:
                    text += "EBITDA利润率反映出公司卓越的运营效率和成本管控能力。"

                text += "管理层对盈利能力优化的重视在近期季度中得到了充分体现。"
            else:
                text = f"{self.company_name} has demonstrated "

                if not growth_row.empty and latest_year:
                    growth = growth_row[latest_year].values[0]
                    if isinstance(growth, str) and '%' in growth:
                        growth_val = float(growth.replace('%', ''))
                    else:
                        growth_val = float(growth) if not pd.isna(growth) else 0

                    if growth_val > 10:
                        text += "strong revenue growth, "
                    elif growth_val > 0:
                        text += "moderate revenue growth, "
                    else:
                        text += "challenging revenue performance, "

                text += "with the company continuing to expand its market presence. "

                if not ebitda_row.empty:
                    text += "EBITDA margins reflect the company's operational efficiency and cost management capabilities. "

                text += "Management's focus on profitability optimization has been evident in recent quarters."

            return text
        except Exception as e:
            if self.is_zh:
                return "营收分析表明公司业务持续运营，具体业绩指标详见附图。"
            return "Revenue analysis indicates continued business operations with performance metrics as shown in the accompanying chart."
    
    def _generate_eps_analysis(self) -> str:
        """生成EPS分析文本"""
        analysis_df = self.data.get('analysis_df')
        if analysis_df is None or analysis_df.empty:
            if self.is_zh:
                return "每股收益数据反映了公司为股东创造价值的能力。"
            return "Earnings per share data provides insight into shareholder value creation."

        try:
            eps_row = analysis_df[analysis_df['metrics'] == 'EPS']
            pe_row = analysis_df[analysis_df['metrics'] == 'PE Ratio']

            if self.is_zh:
                text = f"{self.company_name}的盈利趋势反映出"

                if not eps_row.empty:
                    years = [col for col in eps_row.columns if col.endswith('A')]
                    if len(years) >= 2:
                        latest = pd.to_numeric(eps_row[years[-1]].values[0], errors='coerce')
                        prev = pd.to_numeric(eps_row[years[-2]].values[0], errors='coerce')
                        if not pd.isna(latest) and not pd.isna(prev):
                            if latest > prev:
                                text += f"积极的盈利增长势头（EPS从{prev:.2f}增至{latest:.2f}），"
                            else:
                                text += "盈利承压的态势，"

                text += "估值倍数反映了市场对未来增长的预期。"

                if not pe_row.empty:
                    text += "通过与历史均值及同行P/E的对比，可以为当前市场定价提供参考依据。"
            else:
                text = f"{self.company_name}'s earnings trajectory reflects "

                if not eps_row.empty:
                    years = [col for col in eps_row.columns if col.endswith('A')]
                    if len(years) >= 2:
                        latest = pd.to_numeric(eps_row[years[-1]].values[0], errors='coerce')
                        prev = pd.to_numeric(eps_row[years[-2]].values[0], errors='coerce')
                        if not pd.isna(latest) and not pd.isna(prev):
                            if latest > prev:
                                text += "positive earnings momentum, "
                            else:
                                text += "earnings pressure, "

                text += "while valuation multiples indicate market expectations for future growth. "

                if not pe_row.empty:
                    text += "The P/E ratio comparison against historical averages and peers provides context for current market pricing."

            return text
        except:
            if self.is_zh:
                return "盈利分析显示了公司在分析期间内的盈利能力趋势。"
            return "Earnings analysis shows the company's profitability trends over the analysis period."
    
    def _extract_key_metrics(self, df: pd.DataFrame, metrics: List[str]) -> Dict[str, str]:
        """提取关键指标最新值"""
        result = {}
        try:
            years = [col for col in df.columns if col.endswith('A')]
            latest_year = years[-1] if years else None
            
            if latest_year:
                for metric in metrics:
                    row = df[df['metrics'] == metric]
                    if not row.empty:
                        value = row[latest_year].values[0]
                        result[f"{metric} ({latest_year})"] = format_number(value, currency_symbol=self.currency_symbol)
        except:
            pass
        return result
    
    def _create_financial_table(self, df: pd.DataFrame) -> Optional[Table]:
        """创建财务数据表格"""
        try:
            if df is None or df.empty:
                return None
            
            headers = ['指标' if self.is_zh else 'Metric'] + list(df.columns)
            data = [headers]
            
            for idx, row in df.iterrows():
                row_data = [str(idx)]
                for val in row:
                    row_data.append(format_number(val, currency_symbol=self.currency_symbol))
                data.append(row_data)

            # 动态列宽
            n_cols = len(headers)
            first_col = 40 * mm
            other_cols = (Layout.CONTENT_WIDTH - first_col) / (n_cols - 1) if n_cols > 1 else Layout.CONTENT_WIDTH
            col_widths = [first_col] + [other_cols] * (n_cols - 1)
            
            table = Table(data, colWidths=col_widths)
            table.setStyle(create_data_table_style())
            return table
        except Exception as e:
            return None
    
    def _create_peer_table(self, df: pd.DataFrame) -> Optional[Table]:
        """创建同行对比表格"""
        try:
            if df is None or df.empty:
                return None
            
            headers = ['Company'] + list(df.columns)[:4]  # 限制4列
            data = [headers]
            
            for idx, row in df.head(6).iterrows():
                row_data = [str(idx)]
                for val in list(row)[:4]:
                    row_data.append(format_number(val, currency_symbol=self.currency_symbol))
                data.append(row_data)
            
            n_cols = len(data[0])
            col_widths = [80 * mm / n_cols] * n_cols
            
            table = Table(data, colWidths=col_widths)
            table.setStyle(create_data_table_style())
            return table
        except:
            return None
    
    def _create_peer_table_fixed(self, df: pd.DataFrame, total_width: float) -> Optional[Table]:
        """创建固定宽度的同行对比表格"""
        try:
            if df is None or df.empty:
                return None
            
            headers = ['Year'] + list(df.columns)[:3]  # 限制3列
            data = [headers]
            
            for idx, row in df.head(6).iterrows():
                row_data = [str(idx)]
                for val in list(row)[:3]:
                    row_data.append(format_number(val, currency_symbol=self.currency_symbol))
                data.append(row_data)
            
            n_cols = len(data[0])
            col_widths = [total_width / n_cols] * n_cols
            
            table = Table(data, colWidths=col_widths)
            table.setStyle(create_data_table_style())
            return table
        except:
            return None
    
    # =========================================================================
    # 页眉页脚
    # =========================================================================
    def _add_pdf_metadata(self, canvas_obj, doc):
        """添加PDF元数据（第一页）"""
        # 设置PDF元数据
        canvas_obj.setTitle(f"{self.company_name} ({self.ticker}) - Equity Research Report")
        canvas_obj.setAuthor(self.data.get('research_source', 'AI4Finance FinRobot'))
        canvas_obj.setSubject(f"Equity Research Report for {self.company_name}")
        canvas_obj.setKeywords(f"{self.ticker}, {self.company_name}, Equity Research, Investment Analysis")
        canvas_obj.setCreator('FinRobot Equity Research Platform')
    
    def add_page_header_footer(self, canvas_obj, doc):
        """添加页眉页脚"""
        canvas_obj.saveState()
        
        # 页眉
        canvas_obj.setFont(_CJK_FONT, 8)
        canvas_obj.setFillColor(Colors.MEDIUM_GRAY)
        canvas_obj.drawString(Layout.MARGIN_LEFT, Layout.PAGE_HEIGHT - 12*mm, 
                             f"{self.company_name} ({self.ticker})")
        header_right = "股票研究" if self.is_zh else "Equity Research"
        canvas_obj.drawRightString(Layout.PAGE_WIDTH - Layout.MARGIN_RIGHT,
                                   Layout.PAGE_HEIGHT - 12*mm, header_right)
        
        # 页眉线
        t = _active_theme
        line_c = colors.HexColor(t.colors.header_line) if t else Colors.LIGHT_GRAY
        line_w = 1.0 if (t and t.name == 'cicc') else 0.5
        canvas_obj.setStrokeColor(line_c)
        canvas_obj.setLineWidth(line_w)
        canvas_obj.line(Layout.MARGIN_LEFT, Layout.PAGE_HEIGHT - 14*mm,
                       Layout.PAGE_WIDTH - Layout.MARGIN_RIGHT, Layout.PAGE_HEIGHT - 14*mm)
        
        # 页脚
        canvas_obj.drawCentredString(Layout.PAGE_WIDTH / 2, 10*mm, 
                                     f"Page {doc.page}")
        
        canvas_obj.restoreState()
    
    # =========================================================================
    # 构建完整报告
    # =========================================================================
    def build(self) -> str:
        """构建完整PDF报告 - 内容自然流动"""
        print("📄 Building professional equity report...")
        
        # 按顺序构建各部分 - 内容自然流动，减少强制分页
        self.build_cover_page()
        self.build_company_overview_section()    # 封面后分页
        self.build_financial_analysis_section()  # 自然流动
        self.build_valuation_section()           # 自然流动
        self.build_news_section()                # 新闻分析 (只显示 News Summary，不显示 Recent Headlines)
        self.build_sensitivity_section()         # 敏感性分析 (新增)
        self.build_catalyst_section()            # 催化剂分析 (新增)
        self.build_advanced_charts_section()     # 高级图表分析 (新增)
        self.build_competition_risk_section()    # 自然流动
        self.build_financial_appendix()          # 自然流动
        self.build_disclaimer_page()             # 底部
        
        # 生成PDF
        self.doc.build(
            self.elements,
            onFirstPage=self._add_pdf_metadata,
            onLaterPages=self.add_page_header_footer
        )
        
        print(f"✅ Professional report generated: {self.output_path}")
        return self.output_path


# =============================================================================
# 便捷函数
# =============================================================================
def generate_professional_report(output_path: str, data: Dict[str, Any]) -> str:
    """生成专业股票研究报告"""
    report = ProfessionalEquityReport(output_path, data)
    return report.build()
