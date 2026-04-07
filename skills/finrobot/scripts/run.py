#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinRobot 统一入口 — 在 Docker 容器中执行各分析模块，自动发送结果到 Telegram。

用法:
  python run.py report   --ticker 600519 --name "贵州茅台" --style cicc
  python run.py forecast --ticker BTC --name "Bitcoin"
  python run.py chart    --ticker ETH --name "Ethereum" --timeframe 15m
  python run.py backtest --ticker 600519 --name "贵州茅台" --strategy sma --optimize
  python run.py portfolio --ticker BTC ETH SOL --name "Bitcoin" "Ethereum" "Solana"
  python run.py annual   --ticker AAPL --name "Apple" --fyear 2024
  python run.py rag      --docs /path/to/report.pdf --question "EBITDA是多少"
"""

import argparse
import os
import sys
import re
import subprocess
import glob
from pathlib import Path

# 常量
DOCKER_IMAGE = "finrobot:v2"
CONTAINER_NAME = "finrobot_run"
CONFIG_MOUNT = "/home/guyii/clawd/code/FinRobot/finrobot_equity/core/config"
OUTPUT_DIR = "/home/guyii/clawd/code/FinRobot/skill_output"
TG_SCRIPT = "/home/guyii/.claude/skills/telegram-sendfile/scripts/send_file.py"
WORKDIR = "/app/finrobot_equity/core/src"

# Crypto 已知 ticker
CRYPTO_TICKERS = {
    'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'DOT', 'AVAX',
    'MATIC', 'LINK', 'UNI', 'ATOM', 'LTC', 'ETC', 'FIL', 'APT', 'ARB',
    'OP', 'NEAR', 'AAVE', 'MKR', 'SUI', 'SEI', 'TIA', 'PEPE', 'SHIB', 'WIF',
}


def detect_market(ticker: str) -> str:
    t = ticker.strip().upper()
    if re.match(r'^\d{6}$', t):
        return 'a_share'
    if t in CRYPTO_TICKERS:
        return 'crypto'
    return 'us_stock'


def auto_lang(ticker: str, lang: str = None) -> str:
    if lang:
        return lang
    return 'zh' if detect_market(ticker) == 'a_share' else 'en'


def auto_style(ticker: str, style: str = None) -> str:
    if style:
        return style
    return 'cicc' if detect_market(ticker) == 'a_share' else 'default'


def docker_exec(cmd: str, timeout: int = 600) -> str:
    """在 Docker 容器中执行命令。"""
    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 检查容器是否存在
    check = subprocess.run(
        ["docker", "inspect", CONTAINER_NAME],
        capture_output=True, timeout=5
    )

    if check.returncode != 0:
        # 启动临时容器
        print(f"🐳 Starting container {CONTAINER_NAME}...")
        subprocess.run([
            "docker", "run", "-d", "--name", CONTAINER_NAME,
            "-v", f"{CONFIG_MOUNT}:/app/finrobot_equity/core/config:ro",
            "-v", f"{OUTPUT_DIR}:/app/skill_output",
            DOCKER_IMAGE, "sleep", "3600"
        ], capture_output=True, timeout=30)

    # 执行命令
    full_cmd = f"cd {WORKDIR} && {cmd}"
    print(f"🔄 Executing: {cmd[:100]}...")

    result = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "bash", "-c", full_cmd],
        capture_output=True, text=True, timeout=timeout
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        # 只打印错误，不打印警告
        errors = [l for l in result.stderr.split('\n') if 'Error' in l or 'error' in l]
        if errors:
            print('\n'.join(errors))

    return result.stdout


def send_telegram(filepath: str, caption: str = ""):
    """通过 Telegram 发送文件。"""
    if not os.path.exists(filepath):
        print(f"⚠️ File not found: {filepath}")
        return
    try:
        subprocess.run(
            [sys.executable, TG_SCRIPT, filepath, caption],
            timeout=30, capture_output=True
        )
        print(f"📤 Sent: {os.path.basename(filepath)}")
    except Exception as e:
        print(f"⚠️ Telegram send failed: {e}")


def send_outputs(pattern: str, caption_prefix: str):
    """发送匹配的输出文件到 Telegram。"""
    files = sorted(glob.glob(pattern))
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in ('.pdf', '.png', '.txt', '.json'):
            send_telegram(f, f"{caption_prefix} — {os.path.basename(f)}")


# ═══════════════════════════════════════════════════════════════
# 子命令实现
# ═══════════════════════════════════════════════════════════════

def cmd_report(args):
    """#1 股票研究报告"""
    ticker = args.ticker[0]
    name = args.name[0]
    lang = auto_lang(ticker, args.lang)
    style = auto_style(ticker, args.style)
    out = f"/app/skill_output/{ticker}/report"

    # Step 1: 生成分析数据
    docker_exec(
        f"python generate_financial_analysis.py "
        f"--company-ticker {ticker} --company-name '{name}' "
        f"--data-source auto --years-limit 5 --language {lang} "
        f"--generate-text-sections --enable-sensitivity-analysis "
        f"--enable-catalyst-analysis --config-file ../config/config.ini "
        f"--output-dir {out}/analysis",
        timeout=300
    )

    # Step 2: 生成 PDF
    docker_exec(
        f"python generate_pdf_report.py "
        f"--company-ticker {ticker} --company-name '{name}' "
        f"--analysis-dir {out}/analysis --output-dir {out} "
        f"--style {style} --skip-market-fetch "
        f"--config-file ../config/config.ini",
        timeout=180
    )

    send_outputs(f"{OUTPUT_DIR}/{ticker}/report/*.pdf", f"📊 {name}({ticker}) 研究报告")


def cmd_annual(args):
    """#2 年度报告"""
    ticker = args.ticker[0]
    name = args.name[0]
    lang = auto_lang(ticker, args.lang)
    style = auto_style(ticker, args.style)
    fyear = args.fyear or '2024'
    out = f"/app/skill_output/{ticker}/annual"

    docker_exec(
        f"python generate_annual_report.py "
        f"--company-ticker {ticker} --company-name '{name}' "
        f"--fyear {fyear} --language {lang} --style {style} "
        f"--config-file ../config/config.ini --output-dir {out}",
        timeout=300
    )

    send_outputs(f"{OUTPUT_DIR}/{ticker}/annual/*.pdf", f"📋 {name}({ticker}) FY{fyear} 年报")


def cmd_forecast(args):
    """#3 市场预测"""
    tickers = args.ticker
    names = args.name
    lang = auto_lang(tickers[0], args.lang)
    out = "/app/skill_output/forecasts"

    ticker_args = ' '.join(tickers)
    name_args = ' '.join([f"'{n}'" for n in names])

    docker_exec(
        f"python generate_market_forecast.py "
        f"--company-ticker {ticker_args} --company-name {name_args} "
        f"--language {lang} --config-file ../config/config.ini "
        f"--output-dir {out}",
        timeout=180
    )

    send_outputs(f"{OUTPUT_DIR}/forecasts/*.txt", f"📈 市场预测")


def cmd_chart(args):
    """#6 K线分析"""
    ticker = args.ticker[0]
    name = args.name[0]
    lang = auto_lang(ticker, args.lang)
    days = args.days or 60
    tf = args.timeframe or '1d'
    out = f"/app/skill_output/{ticker}/chart"

    # 如果是分钟级 K 线（crypto），用 crypto_adapter 直接获取
    docker_exec(
        f"python generate_chart_analysis.py "
        f"--company-ticker {ticker} --company-name '{name}' "
        f"--days {days} --language {lang} "
        f"--config-file ../config/config.ini --output-dir {out}",
        timeout=120
    )

    send_outputs(f"{OUTPUT_DIR}/{ticker}/chart/*.png", f"📊 {name}({ticker}) K线图")
    send_outputs(f"{OUTPUT_DIR}/{ticker}/chart/*.txt", f"📊 {name}({ticker}) 技术分析")


def cmd_backtest(args):
    """#7-8 策略回测"""
    ticker = args.ticker[0]
    name = args.name[0]
    lang = auto_lang(ticker, args.lang)
    strategy = args.strategy or 'sma'
    optimize = '--optimize' if args.optimize else ''
    days = args.days or 500
    out = f"/app/skill_output/{ticker}/backtest"

    docker_exec(
        f"python generate_backtest.py "
        f"--company-ticker {ticker} --company-name '{name}' "
        f"--strategy {strategy} {optimize} --days {days} "
        f"--language {lang} --config-file ../config/config.ini "
        f"--output-dir {out}",
        timeout=300
    )

    send_outputs(f"{OUTPUT_DIR}/{ticker}/backtest/*.json", f"📈 {name}({ticker}) {strategy} 回测")


def cmd_portfolio(args):
    """#10 投资组合"""
    tickers = args.ticker
    names = args.name
    lang = auto_lang(tickers[0], args.lang)
    out = "/app/skill_output/portfolio"

    ticker_args = ' '.join(tickers)
    name_args = ' '.join([f"'{n}'" for n in names])

    docker_exec(
        f"python generate_portfolio.py "
        f"--tickers {ticker_args} --names {name_args} "
        f"--language {lang} --config-file ../config/config.ini "
        f"--output-dir {out}",
        timeout=300
    )

    send_outputs(f"{OUTPUT_DIR}/portfolio/*.txt", f"💼 投资组合分析")


def cmd_rag(args):
    """#4 RAG 问答"""
    docs = ' '.join(args.docs)
    question = args.question
    lang = args.lang or 'zh'
    collection = args.collection or 'finrobot_rag'

    result = docker_exec(
        f"python generate_rag_qa.py "
        f"--docs {docs} --collection {collection} "
        f"--question '{question}' --language {lang} "
        f"--config-file ../config/config.ini",
        timeout=120
    )

    # RAG 结果直接打印（不需要发文件）
    return result


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="FinRobot — AI Financial Analysis")
    subparsers = parser.add_subparsers(dest='command', help='Analysis command')

    # 通用参数
    def add_common(p):
        p.add_argument('--ticker', nargs='+', required=True)
        p.add_argument('--name', nargs='+', required=True)
        p.add_argument('--lang', default=None, choices=['zh', 'en'])
        p.add_argument('--style', default=None, choices=['default', 'cicc'])

    # report
    p = subparsers.add_parser('report', help='Equity research report')
    add_common(p)

    # annual
    p = subparsers.add_parser('annual', help='Annual report')
    add_common(p)
    p.add_argument('--fyear', default='2024')

    # forecast
    p = subparsers.add_parser('forecast', help='Market forecast')
    add_common(p)

    # chart
    p = subparsers.add_parser('chart', help='Chart analysis')
    add_common(p)
    p.add_argument('--timeframe', default='1d', choices=['1m', '5m', '15m', '1h', '4h', '1d'])
    p.add_argument('--days', type=int, default=60)

    # backtest
    p = subparsers.add_parser('backtest', help='Strategy backtest')
    add_common(p)
    p.add_argument('--strategy', default='sma', choices=['sma', 'rsi', 'bollinger'])
    p.add_argument('--optimize', action='store_true')
    p.add_argument('--days', type=int, default=500)

    # portfolio
    p = subparsers.add_parser('portfolio', help='Portfolio analysis')
    add_common(p)

    # rag
    p = subparsers.add_parser('rag', help='RAG Q&A')
    p.add_argument('--docs', nargs='+', required=True)
    p.add_argument('--question', required=True)
    p.add_argument('--lang', default='zh')
    p.add_argument('--collection', default='finrobot_rag')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        'report': cmd_report,
        'annual': cmd_annual,
        'forecast': cmd_forecast,
        'chart': cmd_chart,
        'backtest': cmd_backtest,
        'portfolio': cmd_portfolio,
        'rag': cmd_rag,
    }

    print(f"\n{'=' * 50}")
    print(f"🤖 FinRobot — {args.command.upper()}")
    print(f"{'=' * 50}")

    try:
        commands[args.command](args)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print(f"{'=' * 50}")
    print(f"✅ Done!")


if __name__ == '__main__':
    main()
