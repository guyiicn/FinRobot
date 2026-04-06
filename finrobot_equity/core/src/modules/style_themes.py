"""
报告样式主题系统 — 支持多种投行/券商报告风格。

用法:
    from modules.style_themes import get_theme, AVAILABLE_THEMES
    theme = get_theme('cicc')    # 中金风格
    theme = get_theme('default') # 默认投行蓝风格

每个主题定义: 配色、字体、表格样式、分隔线样式等视觉元素。
不改变布局结构（边距、栏宽、模块排列顺序）。
"""
import os
from dataclasses import dataclass, field
from typing import Optional
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont


# ── 字体注册 ──
_FONTS_DIR = os.path.join(os.path.dirname(__file__), 'fonts')

def _register_noto_sans_sc():
    """注册 NotoSansSC (思源黑体) — 中金风格用"""
    path = os.path.join(_FONTS_DIR, 'NotoSansSC.ttf')
    if os.path.exists(path):
        try:
            pdfmetrics.registerFont(TTFont('NotoSansSC', path))
            return True
        except Exception as e:
            print(f"  [style_themes] NotoSansSC 注册失败: {e}")
    return False

def _register_stsong():
    """注册 STSong-Light (宋体 CID) — 默认风格用"""
    try:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        return True
    except:
        return False


# ═══════════════════════════════════════════════════════════════
# 主题数据结构
# ═══════════════════════════════════════════════════════════════
@dataclass
class ThemeColors:
    """主题配色"""
    primary: str        # 主色（标题、强调）
    secondary: str      # 辅助色（副标题装饰）
    text_dark: str      # 深色正文
    text_medium: str    # 中灰次要文本
    text_light: str     # 浅灰背景/分隔线
    positive: str = '#38a169'   # 正面-绿
    negative: str = '#e53e3e'   # 负面-红
    neutral: str  = '#718096'   # 中性-灰
    cover_bg: str = '#1a365d'   # 封面背景色
    cover_text: str = '#ffffff' # 封面文字色
    cover_accent: str = '#c9a227'  # 封面强调色（副标题）
    table_header_bg: str = '#1a365d'
    table_header_fg: str = '#ffffff'
    table_row_alt: str = '#f8f9fa'
    table_border: str = '#dee2e6'
    separator: str = '#1a365d'  # 分隔线颜色
    header_line: str = '#e2e8f0'  # 页眉线颜色

    def hex(self, attr: str):
        return colors.HexColor(getattr(self, attr))


@dataclass
class ThemeFonts:
    """主题字体"""
    regular: str = 'STSong-Light'
    bold: str = 'STSong-Light'

    # 字号
    cover_title: float = 32
    section_title: float = 18
    heading2: float = 13
    heading3: float = 11
    body: float = 9.5
    caption: float = 8
    table_header: float = 8
    table_body: float = 8


@dataclass
class ThemeTable:
    """表格风格"""
    style: str = 'bordered'  # 'bordered' (全边框) 或 'three_line' (三线表)
    header_bg: bool = True   # 表头是否有背景色
    alt_rows: bool = True    # 是否有交替行色
    outer_border: bool = True
    row_lines: bool = True   # 每行分隔线
    header_line_width: float = 1.5
    bottom_line_width: float = 1.0
    row_line_width: float = 0.5


@dataclass
class Theme:
    """完整主题"""
    name: str
    display_name: str
    colors: ThemeColors
    fonts: ThemeFonts
    table: ThemeTable
    # 封面样式
    cover_style: str = 'block'  # 'block' (色块) 或 'line' (横条)
    # 章节标题装饰
    section_title_bar: bool = False  # 标题左侧竖条
    section_title_bar_width: float = 3  # 竖条宽度(pt)


# ═══════════════════════════════════════════════════════════════
# 默认主题 (Investment Bank Blue)
# ═══════════════════════════════════════════════════════════════
THEME_DEFAULT = Theme(
    name='default',
    display_name='Investment Bank (Default)',
    colors=ThemeColors(
        primary='#1a365d',
        secondary='#c9a227',
        text_dark='#2d3748',
        text_medium='#718096',
        text_light='#e2e8f0',
        cover_bg='#1a365d',
        cover_text='#ffffff',
        cover_accent='#c9a227',
        table_header_bg='#1a365d',
        table_header_fg='#ffffff',
        table_row_alt='#f8f9fa',
        table_border='#dee2e6',
        separator='#1a365d',
        header_line='#e2e8f0',
    ),
    fonts=ThemeFonts(
        regular='STSong-Light',
        bold='STSong-Light',
    ),
    table=ThemeTable(
        style='bordered',
        header_bg=True,
        alt_rows=True,
        outer_border=True,
        row_lines=True,
    ),
    cover_style='block',
    section_title_bar=False,
)


# ═══════════════════════════════════════════════════════════════
# 中金风格 (CICC Style)
# ═══════════════════════════════════════════════════════════════
THEME_CICC = Theme(
    name='cicc',
    display_name='中金研究 (CICC Style)',
    colors=ThemeColors(
        primary='#C41E3A',       # 中金红
        secondary='#8B0000',     # 深红
        text_dark='#333333',     # 深灰黑正文
        text_medium='#666666',   # 中灰
        text_light='#f0f0f0',    # 浅灰背景
        positive='#CC0000',      # A股惯例：红涨
        negative='#009900',      # A股惯例：绿跌
        neutral='#666666',
        cover_bg='#ffffff',      # 白底封面
        cover_text='#333333',    # 深色文字
        cover_accent='#C41E3A',  # 红色强调
        table_header_bg='#f5f5f5',  # 浅灰表头
        table_header_fg='#333333',  # 深色文字
        table_row_alt='#fafafa',
        table_border='#cccccc',
        separator='#C41E3A',      # 红色分隔线
        header_line='#C41E3A',    # 红色页眉线
    ),
    fonts=ThemeFonts(
        regular='NotoSansSC',
        bold='NotoSansSC',
        cover_title=28,
        section_title=16,
        heading2=12,
        heading3=10.5,
        body=10,
        caption=8,
        table_header=8.5,
        table_body=8.5,
    ),
    table=ThemeTable(
        style='three_line',
        header_bg=True,
        alt_rows=False,
        outer_border=False,
        row_lines=True,
        header_line_width=1.5,
        bottom_line_width=1.5,
        row_line_width=0.3,
    ),
    cover_style='line',
    section_title_bar=True,
    section_title_bar_width=3,
)


# ═══════════════════════════════════════════════════════════════
# 主题注册表
# ═══════════════════════════════════════════════════════════════
AVAILABLE_THEMES = {
    'default': THEME_DEFAULT,
    'cicc': THEME_CICC,
}


def get_theme(name: str = 'default') -> Theme:
    """
    获取主题实例并确保字体已注册。

    Args:
        name: 'default' 或 'cicc'
    """
    name = name.lower()
    if name not in AVAILABLE_THEMES:
        avail = ', '.join(AVAILABLE_THEMES.keys())
        raise ValueError(f"Unknown theme '{name}'. Available: {avail}")

    theme = AVAILABLE_THEMES[name]

    # 确保字体已注册
    if theme.fonts.regular == 'NotoSansSC':
        if not _register_noto_sans_sc():
            print(f"  ⚠️ NotoSansSC 不可用, 回退到 STSong-Light")
            theme.fonts.regular = 'STSong-Light'
            theme.fonts.bold = 'STSong-Light'
            _register_stsong()
    else:
        _register_stsong()

    return theme
