#!/usr/bin/env python
# coding: utf-8
"""
交易策略回测 — 基于 BackTrader，支持 A股/美股。
复用 FinRobot 原版 BackTraderUtils 架构，增加 A 股数据源和参数优化。

内置策略:
  - sma: SMA 均线交叉（金叉买/死叉卖）
  - rsi: RSI 超买超卖
  - bollinger: 布林带突破

用法:
  # A股 SMA 回测 + 参数优化
  python3 generate_backtest.py --company-ticker 600519 --company-name "贵州茅台" \\
      --strategy sma --optimize --language zh --config-file ../config/config.ini

  # 美股 布林带策略
  python3 generate_backtest.py --company-ticker AAPL --company-name "Apple" \\
      --strategy bollinger --days 500 --language en --config-file ../config/config.ini

  # 自定义 SMA 参数
  python3 generate_backtest.py --company-ticker 600519 --company-name "贵州茅台" \\
      --strategy sma --params '{"fast":10,"slow":30}' --language zh --config-file ../config/config.ini
"""

import argparse
import os
import re
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pprint import pformat

import pandas as pd
import numpy as np
import backtrader as bt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.common_utils import load_config, get_api_key
from modules.chart_fonts import setup_chart_fonts
setup_chart_fonts()


def _is_a_share(ticker: str) -> bool:
    return bool(re.match(r'^\d{6}$', ticker))


# ═══════════════════════════════════════════════════════════════
# 内置策略
# ═══════════════════════════════════════════════════════════════

class SmaCross(bt.Strategy):
    """SMA 均线交叉策略"""
    params = (('fast', 5), ('slow', 20),)

    def __init__(self):
        sma_fast = bt.ind.SMA(period=self.p.fast)
        sma_slow = bt.ind.SMA(period=self.p.slow)
        self.crossover = bt.ind.CrossOver(sma_fast, sma_slow)

    def next(self):
        if not self.position:
            if self.crossover > 0:
                self.buy()
        elif self.crossover < 0:
            self.close()


class RsiStrategy(bt.Strategy):
    """RSI 超买超卖策略"""
    params = (('period', 14), ('oversold', 30), ('overbought', 70),)

    def __init__(self):
        self.rsi = bt.ind.RSI(period=self.p.period)

    def next(self):
        if not self.position:
            if self.rsi < self.p.oversold:
                self.buy()
        elif self.rsi > self.p.overbought:
            self.close()


class BollingerStrategy(bt.Strategy):
    """布林带突破策略"""
    params = (('period', 20), ('devfactor', 2.0),)

    def __init__(self):
        self.boll = bt.ind.BollingerBands(period=self.p.period, devfactor=self.p.devfactor)

    def next(self):
        if not self.position:
            if self.data.close[0] < self.boll.lines.bot[0]:
                self.buy()
        elif self.data.close[0] > self.boll.lines.top[0]:
            self.close()


STRATEGIES = {
    'sma': SmaCross,
    'rsi': RsiStrategy,
    'bollinger': BollingerStrategy,
}

# 参数优化搜索空间
OPTIMIZE_GRID = {
    'sma': {'fast': range(3, 15, 2), 'slow': range(15, 60, 5)},
    'rsi': {'period': range(10, 25, 2), 'oversold': range(20, 40, 5), 'overbought': range(65, 85, 5)},
    'bollinger': {'period': range(15, 35, 5), 'devfactor': [1.5, 2.0, 2.5, 3.0]},
}


# ═══════════════════════════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════════════════════════

def fetch_data(ticker: str, days: int = 500) -> pd.DataFrame:
    """获取 OHLCV 数据，自动选择 A股/美股 数据源。"""
    is_ashare = _is_a_share(ticker)

    if is_ashare:
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
                raise ValueError(f"No data for {ticker}")
            df = df.tail(days).copy()
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.rename(columns={
                'open': 'Open', 'high': 'High', 'low': 'Low',
                'close': 'Close', 'volume': 'Volume',
            }, inplace=True)
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
            # backtrader 需要 openinterest 列
            df['OpenInterest'] = 0
            print(f"  ✅ A股数据: {len(df)} 个交易日 ({df.index[0].date()} ~ {df.index[-1].date()})")
            return df
        finally:
            os.environ.update(saved)
    else:
        import yfinance as yf
        end = datetime.now()
        start = end - timedelta(days=int(days * 1.5))  # 多取确保有足够交易日
        df = yf.download(ticker, start=start.strftime('%Y-%m-%d'),
                         end=end.strftime('%Y-%m-%d'), auto_adjust=True, progress=False)
        if df.empty:
            raise ValueError(f"No data for {ticker}")
        df = df.tail(days)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['OpenInterest'] = 0
        print(f"  ✅ 美股数据: {len(df)} 个交易日 ({df.index[0].date()} ~ {df.index[-1].date()})")
        return df


# ═══════════════════════════════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════════════════════════════

def run_backtest(df: pd.DataFrame, strategy_class, params: dict = None,
                  cash: float = 100000, commission: float = 0.001,
                  save_fig: str = None) -> Dict:
    """运行单次回测，返回结果字典。"""
    cerebro = bt.Cerebro()

    # 添加策略
    if params:
        cerebro.addstrategy(strategy_class, **params)
    else:
        cerebro.addstrategy(strategy_class)

    # 添加数据
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    # 设置初始资金和手续费
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)

    # 设置仓位大小（每次用90%资金）
    cerebro.addsizer(bt.sizers.PercentSizer, percents=90)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.03)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    # 运行
    start_val = cerebro.broker.getvalue()
    results = cerebro.run()
    end_val = cerebro.broker.getvalue()
    strat = results[0]

    # 提取结果
    sharpe = strat.analyzers.sharpe.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()
    ret = strat.analyzers.returns.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    total_return = (end_val - start_val) / start_val * 100
    total_trades = trades.get('total', {}).get('total', 0)
    won = trades.get('won', {}).get('total', 0)
    lost = trades.get('lost', {}).get('total', 0)
    win_rate = (won / total_trades * 100) if total_trades > 0 else 0

    result = {
        'start_value': start_val,
        'end_value': round(end_val, 2),
        'total_return': round(total_return, 2),
        'annual_return': round(ret.get('rnorm100', 0), 2),
        'sharpe_ratio': round(sharpe.get('sharperatio', 0) or 0, 3),
        'max_drawdown': round(dd.get('max', {}).get('drawdown', 0), 2),
        'total_trades': total_trades,
        'won': won,
        'lost': lost,
        'win_rate': round(win_rate, 1),
        'params': params or {},
    }

    # 保存图表
    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig = cerebro.plot(style='candle', iplot=False, volume=True)[0][0]
            fig.set_size_inches(14, 8)
            fig.savefig(save_fig, dpi=120, bbox_inches='tight')
            plt.close('all')
            result['chart_path'] = save_fig
            print(f"  📈 回测图表: {save_fig}")
        except Exception as e:
            print(f"  ⚠️ 图表保存失败: {e}")

    return result


def optimize_strategy(df: pd.DataFrame, strategy_name: str,
                       cash: float = 100000, commission: float = 0.001) -> List[Dict]:
    """网格搜索优化策略参数。"""
    strategy_class = STRATEGIES[strategy_name]
    grid = OPTIMIZE_GRID[strategy_name]

    # 生成参数组合
    import itertools
    keys = list(grid.keys())
    values = [list(v) for v in grid.values()]
    combos = list(itertools.product(*values))

    print(f"  🔍 优化搜索: {len(combos)} 种参数组合...")
    results = []

    for combo in combos:
        params = dict(zip(keys, combo))
        # 跳过无效组合（如 sma: fast >= slow）
        if strategy_name == 'sma' and params.get('fast', 0) >= params.get('slow', 0):
            continue

        try:
            r = run_backtest(df, strategy_class, params, cash, commission)
            results.append(r)
        except:
            pass

    # 按收益率排序
    results.sort(key=lambda x: x['total_return'], reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════
# LLM 分析
# ═══════════════════════════════════════════════════════════════

def analyze_results(result: Dict, company_name: str, ticker: str, strategy_name: str,
                     api_key: str, base_url: str = None, model: str = None,
                     language: str = 'zh', optimize_results: List[Dict] = None) -> str:
    """用 LLM 分析回测结果。"""
    if not api_key:
        return ""

    prompt = f"公司: {company_name} ({ticker})\n策略: {strategy_name}\n\n"
    prompt += f"回测结果:\n"
    prompt += f"  总收益率: {result['total_return']}%\n"
    prompt += f"  年化收益: {result['annual_return']}%\n"
    prompt += f"  夏普比率: {result['sharpe_ratio']}\n"
    prompt += f"  最大回撤: {result['max_drawdown']}%\n"
    prompt += f"  总交易次数: {result['total_trades']}\n"
    prompt += f"  胜率: {result['win_rate']}%\n"
    prompt += f"  参数: {result['params']}\n"

    if optimize_results:
        prompt += f"\n参数优化 Top 5:\n"
        for i, r in enumerate(optimize_results[:5], 1):
            prompt += f"  {i}. {r['params']} → 收益{r['total_return']}%, 夏普{r['sharpe_ratio']}, 回撤{r['max_drawdown']}%\n"

    sys_prompt = (
        "你是一位量化交易策略分析师。请简要分析回测结果，评价策略表现，"
        "指出优缺点，并给出改进建议。200字以内，中文回答。" if language == 'zh' else
        "You are a quant strategist. Briefly analyze the backtest results, evaluate performance, "
        "note strengths/weaknesses, and suggest improvements. Under 200 words."
    )

    try:
        from openai import OpenAI
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
            temperature=0.5, max_tokens=500,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[分析失败: {e}]"


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Trading Strategy Backtest (BackTrader)")
    parser.add_argument("--company-ticker", type=str, required=True)
    parser.add_argument("--company-name", type=str, required=True)
    parser.add_argument("--strategy", type=str, default="sma",
                        choices=list(STRATEGIES.keys()),
                        help="Strategy: sma, rsi, bollinger")
    parser.add_argument("--params", type=str, default="",
                        help="Strategy params as JSON (e.g. '{\"fast\":10,\"slow\":30}')")
    parser.add_argument("--days", type=int, default=500, help="Trading days of data")
    parser.add_argument("--cash", type=float, default=100000, help="Initial cash")
    parser.add_argument("--commission", type=float, default=0.001, help="Commission rate")
    parser.add_argument("--optimize", action="store_true", help="Run parameter optimization")
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--config-file", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)

    args = parser.parse_args()
    ticker = args.company_ticker if _is_a_share(args.company_ticker) else args.company_ticker.upper()
    is_ashare = _is_a_share(ticker)

    output_dir = args.output_dir or os.path.join('.', 'output', ticker, 'backtest')
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
    except:
        pass

    strategy_names = {'sma': 'SMA均线交叉', 'rsi': 'RSI超买超卖', 'bollinger': '布林带突破'}
    strategy_display = strategy_names.get(args.strategy, args.strategy) if args.language == 'zh' else args.strategy.upper()

    print(f"\n{'=' * 60}")
    print(f"📈 TRADING STRATEGY BACKTEST (BackTrader)")
    print(f"{'=' * 60}")
    print(f"Company: {args.company_name} ({ticker})")
    print(f"Strategy: {strategy_display}")
    print(f"Period: {args.days} trading days | Cash: {args.cash:,.0f}")
    print(f"Market: {'A-share (T+1)' if is_ashare else 'US'}")
    if args.optimize:
        print(f"Mode: Parameter Optimization")
    print(f"{'=' * 60}\n")

    # 1. 获取数据
    print("📥 Fetching market data...")
    try:
        df = fetch_data(ticker, args.days)
    except Exception as e:
        print(f"❌ Data fetch failed: {e}")
        return

    # 2. 运行回测
    strategy_class = STRATEGIES[args.strategy]
    params = json.loads(args.params) if args.params else {}

    print(f"\n🔄 Running backtest...")
    chart_path = os.path.join(output_dir, f"{ticker}_{args.strategy}_backtest.png")
    result = run_backtest(df, strategy_class, params or None, args.cash, args.commission, chart_path)

    # 打印结果
    cs = '¥' if is_ashare else '$'
    print(f"\n{'━' * 50}")
    print(f"📊 {'回测结果' if args.language == 'zh' else 'Backtest Results'}")
    print(f"{'━' * 50}")
    print(f"  {'策略' if args.language == 'zh' else 'Strategy'}: {strategy_display}")
    print(f"  {'参数' if args.language == 'zh' else 'Params'}: {result['params']}")
    print(f"  {'初始资金' if args.language == 'zh' else 'Start'}: {cs}{result['start_value']:,.0f}")
    print(f"  {'最终资金' if args.language == 'zh' else 'End'}: {cs}{result['end_value']:,.0f}")
    print(f"  {'总收益率' if args.language == 'zh' else 'Return'}: {result['total_return']:+.2f}%")
    print(f"  {'年化收益' if args.language == 'zh' else 'Annual'}: {result['annual_return']:+.2f}%")
    print(f"  {'夏普比率' if args.language == 'zh' else 'Sharpe'}: {result['sharpe_ratio']}")
    print(f"  {'最大回撤' if args.language == 'zh' else 'Max DD'}: -{result['max_drawdown']:.2f}%")
    print(f"  {'交易次数' if args.language == 'zh' else 'Trades'}: {result['total_trades']}")
    print(f"  {'胜率' if args.language == 'zh' else 'Win Rate'}: {result['win_rate']}% ({result['won']}W/{result['lost']}L)")
    print(f"{'━' * 50}")

    # 3. 参数优化
    optimize_results = None
    if args.optimize:
        print(f"\n🔍 {'参数优化中...' if args.language == 'zh' else 'Optimizing parameters...'}")
        optimize_results = optimize_strategy(df, args.strategy, args.cash, args.commission)

        if optimize_results:
            print(f"\n{'━' * 50}")
            print(f"🏆 {'最优参数 Top 5' if args.language == 'zh' else 'Top 5 Parameters'}")
            print(f"{'━' * 50}")
            for i, r in enumerate(optimize_results[:5], 1):
                print(f"  {i}. {r['params']} → "
                      f"{'收益' if args.language == 'zh' else 'Return'}: {r['total_return']:+.2f}%, "
                      f"{'夏普' if args.language == 'zh' else 'Sharpe'}: {r['sharpe_ratio']}, "
                      f"{'回撤' if args.language == 'zh' else 'DD'}: -{r['max_drawdown']:.2f}%")

            # 用最优参数重新回测并生成图表
            best = optimize_results[0]
            print(f"\n  📈 {'用最优参数重新回测...' if args.language == 'zh' else 'Re-running with best params...'}")
            best_chart = os.path.join(output_dir, f"{ticker}_{args.strategy}_best.png")
            result = run_backtest(df, strategy_class, best['params'], args.cash, args.commission, best_chart)

    # 4. LLM 分析
    if api_key:
        print(f"\n🤖 {'AI分析...' if args.language == 'zh' else 'AI Analysis...'}")
        analysis = analyze_results(result, args.company_name, ticker, strategy_display,
                                    api_key, base_url, model, args.language, optimize_results)
        if analysis:
            print(f"\n💡 {'AI策略评价' if args.language == 'zh' else 'AI Analysis'}:")
            print(analysis)

    # 5. 保存结果
    report = {
        'ticker': ticker,
        'company': args.company_name,
        'strategy': args.strategy,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'result': result,
        'optimize_top5': [r for r in (optimize_results or [])[:5]],
    }
    json_path = os.path.join(output_dir, f"{ticker}_{args.strategy}_result.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"✅ {'回测完成!' if args.language == 'zh' else 'BACKTEST COMPLETE!'}")
    print(f"{'=' * 60}")
    print(f"📊 JSON: {json_path}")
    if result.get('chart_path'):
        print(f"📈 Chart: {result['chart_path']}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
