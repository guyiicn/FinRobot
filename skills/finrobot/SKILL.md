---
name: finrobot
description: "FinRobot AI financial analysis platform. Generates equity research reports,\
  \ annual reports, market forecasts, K-line chart analysis, trading strategy backtests,\
  \ portfolio analysis, and RAG Q&A on financial documents.\n\
  \ Supports 3 markets: A-shares (China), US stocks, and Cryptocurrency.\n\
  \ Auto-detects market from ticker: 6-digit=A-share, BTC/ETH/SOL=crypto, letters=US.\n\n\
  \ Use when: User wants to analyze stocks, predict market movement, generate research\
  \ reports, backtest trading strategies, or ask questions about financial documents.\n\
  \ Triggers (Chinese): '分析茅台', '生成研报', '年报', '预测走势', 'K线分析', '回测策略', '投资组合分析',\
  \ '问研报'\n\
  \ Triggers (English): 'analyze AAPL', 'equity report', 'annual report', 'forecast BTC',\
  \ 'chart analysis', 'backtest', 'portfolio analysis', 'ask about report'\n\
  \ Don't use for: Real-time trading execution, blockchain transactions, wallet management."
---

# FinRobot — AI Financial Analysis Platform

Multi-market financial analysis platform supporting A-shares, US stocks, and cryptocurrency.
All analysis runs inside Docker container `finrobot:v2` (Python 3.10 + pyautogen).

## Available Commands

### 1. Equity Research Report (股票研究报告)
Generate professional PDF report with financial analysis, valuation, risks, and AI-generated text.

```bash
python ~/.claude/skills/finrobot/scripts/run.py report \
  --ticker 600519 --name "贵州茅台" --style cicc --lang zh
```

Triggers: "分析XX", "生成XX研报", "equity report for XX", "analyze XX"

### 2. Annual Report (年度报告)
Generate annual report with business overview, operating results, financial position, risks.

```bash
python ~/.claude/skills/finrobot/scripts/run.py annual \
  --ticker 600519 --name "贵州茅台" --fyear 2024 --style cicc --lang zh
```

Triggers: "XX年报", "annual report for XX"

### 3. Market Forecast (市场预测)
Predict stock/crypto price movement for next week based on news + financials + price action.

```bash
python ~/.claude/skills/finrobot/scripts/run.py forecast \
  --ticker BTC --name "Bitcoin" --lang en
# Multiple tickers:
python ~/.claude/skills/finrobot/scripts/run.py forecast \
  --ticker 600519 000858 --name "贵州茅台" "五粮液" --lang zh
```

Triggers: "预测XX走势", "XX forecast", "XX下周会涨还是跌"

### 4. Chart Analysis (K线分析)
Generate candlestick chart + GPT-4o vision technical analysis.

```bash
python ~/.claude/skills/finrobot/scripts/run.py chart \
  --ticker BTC --name "Bitcoin" --timeframe 15m --days 200 --lang en
```

Timeframes: 1m, 5m, 15m, 1h, 4h, 1d (crypto only for intraday)
Triggers: "XX K线分析", "BTC 15分钟K线", "chart analysis for XX", "XX技术分析"

### 5. Strategy Backtest (策略回测)
Backtest trading strategies (SMA/RSI/Bollinger) with parameter optimization.

```bash
python ~/.claude/skills/finrobot/scripts/run.py backtest \
  --ticker 600519 --name "贵州茅台" --strategy sma --optimize --lang zh
```

Strategies: sma, rsi, bollinger
Triggers: "回测XX", "backtest XX", "XX均线策略", "测试XX交易策略"

### 6. Portfolio Analysis (投资组合)
Multi-agent analysis: sentiment + risk + fundamental analysts → CIO decision.

```bash
python ~/.claude/skills/finrobot/scripts/run.py portfolio \
  --ticker BTC ETH SOL --name "Bitcoin" "Ethereum" "Solana" --lang en
```

Triggers: "分析XX板块组合", "portfolio analysis", "XX组合怎么配置"

### 7. RAG Q&A (文档问答)
Ask questions about previously generated reports.

```bash
python ~/.claude/skills/finrobot/scripts/run.py rag \
  --docs /path/to/report.pdf --question "EBITDA利润率是多少" --lang zh
```

Triggers: "问XX报告", "ask about XX report", "XX的营收是多少"

## Market Auto-Detection

| Ticker Format | Market | Data Source | Example |
|--------------|--------|-------------|---------|
| 6 digits | A-share | akshare + THS | 600519, 000917 |
| Letters (known crypto) | Crypto | CCXT + CoinGecko | BTC, ETH, SOL |
| Other letters | US Stock | yfinance | AAPL, MSFT |

## Style Themes

- `--style default` — Investment bank blue (海军蓝)
- `--style cicc` — CICC red (中金红 + NotoSansSC font)

## Output

All generated files are automatically sent to Telegram via @guyiifile_bot.
Output files are saved to `/home/guyii/clawd/code/FinRobot/skill_output/`.
