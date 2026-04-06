"""
图表中文字体配置 — 确保 matplotlib 图表正确渲染中文。
所有生成图表的脚本在开头调用 setup_chart_fonts() 即可。
"""
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

_configured = False


def setup_chart_fonts():
    """配置 matplotlib 中文字体，只执行一次。"""
    global _configured
    if _configured:
        return
    _configured = True

    # 优先级：Noto Sans CJK > FZFangSong > SimHei > 系统默认
    candidates = ['Noto Sans CJK JP', 'Noto Sans CJK SC', 'FZFangSong-Z02',
                   'SimHei', 'WenQuanYi Micro Hei', 'Microsoft YaHei']

    available = {f.name for f in fm.fontManager.ttflist}
    chosen = None
    for c in candidates:
        if c in available:
            chosen = c
            break

    if chosen:
        plt.rcParams['font.sans-serif'] = [chosen, 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        print(f"  📝 [chart_fonts] 使用字体: {chosen}")
    else:
        # 回退：手动注册 NotoSansSC TTF
        import os
        noto_path = os.path.join(os.path.dirname(__file__), 'fonts', 'NotoSansSC.ttf')
        if os.path.exists(noto_path):
            try:
                fm.fontManager.addfont(noto_path)
                plt.rcParams['font.sans-serif'] = ['Noto Sans SC', 'DejaVu Sans']
                plt.rcParams['axes.unicode_minus'] = False
                print(f"  📝 [chart_fonts] 注册并使用: NotoSansSC.ttf")
                return
            except:
                pass
        print("  ⚠️ [chart_fonts] 未找到中文字体，图表中文可能显示异常")
