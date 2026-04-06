# FinRobot 架构重构设计方案

## 📋 文档说明

本文档记录了 FinRobot 从 FMP API 迁移到 Yahoo Finance 过程中遇到的问题和提出的架构重构方案。旨在提供一个清晰、可扩展的数据源适配器模式，便于后续其他 AI Agent 审核和优化。

---

## 🎯 问题背景

### 当前问题

1. **数据源变更导致代码失效**
   - 原代码依赖 FMP API（付费），免费计划不支持财务报表数据
   - 切换到 Yahoo Finance（免费）后，数据格式不匹配
   - 所有财务指标返回 `None`，导致报告生成失败

2. **数据格式差异**
   
   | 数据源 | 数据格式 | 列名示例 |
   |--------|---------|---------|
   | FMP API | `[{date, revenue, ebitda, ...}, ...]` | `calendarYear`, `revenue`, `ebitda` |
   | Yahoo Finance | `pd.DataFrame` (日期为列名) | `2024-12-31`, `Total Revenue`, `EBITDA` |

3. **新闻模块失效**
   - FMP 新闻 API 需要付费订阅
   - 当前返回 404 错误，无法获取新闻数据

### 失败案例

```python
# 当前日志输出
Historical Metrics Extracted from API:
metrics 2024A 2023A 2022A 2021A
0               Revenue  None  None  None  None
1    Cost of Operations  None  None  None  None
2                  EBITDA  None  None  None  None
```

---

## 🏗️ 架构设计：数据源适配器模式

### 核心思想

**解耦数据源与业务逻辑**，通过适配器模式将不同数据源的数据转换为统一的内部格式。

```
┌─────────────────────────────────────────────────────────────────┐
│                    FinRobot Core (Agents & Logic)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Financial    │  │ Text         │  │ Report               │  │
│  │ Analysis     │  │ Generation   │  │ Generation           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                          ↕
┌─────────────────────────────────────────────────────────────────┐
│                   Unified Data Model (Standard Format)           │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ • Financial Statements (Income, Balance, Cash Flow)        │ │
│  │ • Key Metrics & Ratios (PE, PB, ROE, etc.)                 │ │
│  │ • Market Data (Price, Volume, Market Cap)                  │ │
│  │ • Company Profile (Sector, Industry, Description)          │ │
│  │ • News & Sentiment (Date, Title, Content, Score)           │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                          ↕ ↕ ↕
┌─────────────────────────────────────────────────────────────────┐
│                    Data Source Adapters                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Yahoo Finance│  │ FMP API      │  │ Alpha Vantage        │  │
│  │ (yfinance)   │  │ (Premium)    │  │ (Free Tier)          │  │
│  │ ✅ Full      │  │ ✅ Full      │  │ ✅ Partial           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Crypto.com   │  │ CoinGecko    │  │ ... (future)         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📐 详细设计

### 1. 统一数据模型 (Data Classes)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

@dataclass
class FinancialStatement:
    """统一财务报表格式"""
    year: int
    period: str  # 'annual' or 'quarterly'
    
    # Income Statement
    revenue: Optional[float]
    cost_of_revenue: Optional[float]
    gross_profit: Optional[float]
    operating_expenses: Optional[float]
    ebitda: Optional[float]
    net_income: Optional[float]
    eps: Optional[float]
    
    # Balance Sheet
    total_assets: Optional[float]
    total_liabilities: Optional[float]
    shareholders_equity: Optional[float]
    
    # Cash Flow
    operating_cash_flow: Optional[float]
    investing_cash_flow: Optional[float]
    financing_cash_flow: Optional[float]

@dataclass
class CompanyProfile:
    """统一公司信息格式"""
    ticker: str
    name: str
    sector: str
    industry: str
    description: Optional[str]
    
    # Market Data
    price: Optional[float]
    market_cap: Optional[float]
    volume: Optional[int]
    
    # Ratios
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    dividend_yield: Optional[float]
    beta: Optional[float]
    
    # Other
    exchange: str
    country: str
    employees: Optional[int]

@dataclass
class NewsItem:
    """统一新闻格式"""
    date: datetime
    title: str
    content: str
    source: str
    url: Optional[str]
    sentiment_score: Optional[float]  # -1.0 to 1.0
    categories: List[str]  # ['earnings', 'mergers', 'regulatory', ...]

@dataclass
class CompanyData:
    """统一的公司数据容器"""
    profile: CompanyProfile
    income_statements: List[FinancialStatement]
    balance_sheets: List[FinancialStatement]
    cash_flows: List[FinancialStatement]
    news: List[NewsItem]
    technical_indicators: dict  # SMA, RSI, MACD, etc.
```

### 2. 数据源适配器基类

```python
from abc import ABC, abstractmethod

class DataSourceAdapter(ABC):
    """数据源适配器基类"""
    
    @abstractmethod
    def fetch_income_statement(self, ticker: str) -> List[FinancialStatement]:
        """获取利润表"""
        pass
    
    @abstractmethod
    def fetch_balance_sheet(self, ticker: str) -> List[FinancialStatement]:
        """获取资产负债表"""
        pass
    
    @abstractmethod
    def fetch_cash_flow(self, ticker: str) -> List[FinancialStatement]:
        """获取现金流量表"""
        pass
    
    @abstractmethod
    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """获取公司基本信息"""
        pass
    
    @abstractmethod
    def fetch_news(self, ticker: str, days: int, limit: int) -> List[NewsItem]:
        """获取新闻"""
        pass
    
    @abstractmethod
    def get_technical_indicators(self, ticker: str) -> dict:
        """获取技术指标"""
        pass
```

### 3. Yahoo Finance 适配器实现

```python
import yfinance as yf
import pandas as pd
from datetime import datetime

class YahooFinanceAdapter(DataSourceAdapter):
    """Yahoo Finance 数据适配器"""
    
    def __init__(self):
        self.session = None
    
    def _parse_financials(self, raw_df: pd.DataFrame) -> List[FinancialStatement]:
        """
        将 yfinance 返回的 DataFrame 转换为 FinancialStatement 列表
        
        yfinance 格式:
        - 列：日期 (Timestamp)
        - 行：财务指标名称 (如 'Total Revenue', 'EBITDA')
        
        转换逻辑:
        - 转置 DataFrame
        - 提取年份作为 year 字段
        - 映射指标名称到标准字段
        """
        statements = []
        
        if raw_df is None or raw_df.empty:
            return statements
        
        # 转置：日期变列，指标变行
        transposed = raw_df.T
        
        for date_col in transposed.columns:
            year = date_col.year if hasattr(date_col, 'year') else int(date_col)
            
            # 获取该年的数据行
            row = transposed[date_col]
            
            # 映射 yfinance 字段名到标准字段名
            statement = FinancialStatement(
                year=year,
                period='annual',
                revenue=self._get_value(row, ['Total Revenue', 'Total Sales']),
                cost_of_revenue=self._get_value(row, ['Cost Of Revenue', 'Cost Of Sales']),
                gross_profit=self._get_value(row, ['Gross Profit']),
                operating_expenses=self._get_value(row, ['Operating Expense', 'Total Operating Expenses']),
                ebitda=self._get_value(row, ['EBITDA', 'Earnings Before Interest And Taxes']),
                net_income=self._get_value(row, ['Net Income', 'Net Income Common Stockholders']),
                eps=self._get_value(row, ['Diluted EPS', 'Basic EPS']),
                total_assets=self._get_value(row, ['Total Assets']),
                total_liabilities=self._get_value(row, ['Total Liabilities Net Minority Interest']),
                shareholders_equity=self._get_value(row, ['Total Equity Gross Minority']),
                operating_cash_flow=self._get_value(row, ['Operating Cash Flow']),
                investing_cash_flow=self._get_value(row, ['Investing Cash Flow']),
                financing_cash_flow=self._get_value(row, ['Financing Cash Flow'])
            )
            statements.append(statement)
        
        return statements
    
    def _get_value(self, row: pd.Series, field_names: List[str]):
        """从 Series 中查找第一个存在的字段"""
        for field in field_names:
            if field in row:
                value = row[field]
                # 处理 NaN 和 None
                if pd.isna(value) or value is None:
                    return None
                return float(value)
        return None
    
    def fetch_income_statement(self, ticker: str) -> List[FinancialStatement]:
        """获取利润表"""
        stock = yf.Ticker(ticker)
        raw_df = stock.financials
        return self._parse_financials(raw_df)
    
    def fetch_balance_sheet(self, ticker: str) -> List[FinancialStatement]:
        """获取资产负债表"""
        stock = yf.Ticker(ticker)
        raw_df = stock.balance_sheet
        return self._parse_financials(raw_df)
    
    def fetch_cash_flow(self, ticker: str) -> List[FinancialStatement]:
        """获取现金流量表"""
        stock = yf.Ticker(ticker)
        raw_df = stock.cashflow
        return self._parse_financials(raw_df)
    
    def fetch_company_profile(self, ticker: str) -> CompanyProfile:
        """获取公司基本信息"""
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if not info:
            raise ValueError(f"No data found for ticker: {ticker}")
        
        return CompanyProfile(
            ticker=ticker,
            name=info.get('longName') or info.get('shortName'),
            sector=info.get('sector', 'Unknown'),
            industry=info.get('industry', 'Unknown'),
            description=info.get('longBusinessSummary'),
            price=info.get('currentPrice') or info.get('regularMarketPrice'),
            market_cap=info.get('marketCap'),
            volume=info.get('averageVolume'),
            pe_ratio=info.get('forwardPE'),
            pb_ratio=info.get('priceToBook'),
            dividend_yield=info.get('dividendYield'),
            beta=info.get('beta'),
            exchange=info.get('exchange', 'N/A'),
            country=info.get('country', 'N/A'),
            employees=info.get('fullTimeEmployees')
        )
    
    def fetch_news(self, ticker: str, days: int = 5, limit: int = 10) -> List[NewsItem]:
        """获取新闻"""
        stock = yf.Ticker(ticker)
        news_list = stock.news
        
        if not news_list:
            return []
        
        news_items = []
        cutoff_date = datetime.now() - pd.Timedelta(days=days)
        
        for item in news_list[:limit]:
            # 解析发布时间戳
            publish_time = item.get('providerPublishTime')
            if not publish_time:
                continue
            
            pub_date = datetime.fromtimestamp(publish_time)
            if pub_date < cutoff_date:
                continue
            
            # 提取内容
            summary = item.get('summary', '')
            text = item.get('relatedContent', '')
            content = f"{summary}\n{text}"[:2000]  # 限制长度
            
            news_items.append(NewsItem(
                date=pub_date,
                title=item.get('title', ''),
                content=content,
                source=item.get('publisher', ''),
                url=item.get('link'),
                sentiment_score=self._analyze_sentiment(summary),  # 可选
                categories=self._categorize_news(item)  # 可选
            ))
        
        return news_items
    
    def _analyze_sentiment(self, text: str) -> float:
        """简单的 sentiment 分析（可以用 NLP 库优化）"""
        # 这里可以集成 VADER, TextBlob, 或调用 LLM
        # 简单实现：基于关键词
        positive_words = ['gain', 'profit', 'growth', 'upgrade', 'positive', 'beat']
        negative_words = ['loss', 'decline', 'downgrade', 'negative', 'miss', 'risk']
        
        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        total = pos_count + neg_count
        if total == 0:
            return 0.0
        return (pos_count - neg_count) / total
    
    def _categorize_news(self, item: dict) -> List[str]:
        """新闻分类（可以基于关键词或 ML）"""
        title = (item.get('title', '') + ' ' + item.get('summary', '')).lower()
        categories = []
        
        if any(word in title for word in ['earnings', 'revenue', 'quarterly', 'annual']):
            categories.append('earnings')
        if any(word in title for word in ['merger', 'acquisition', 'merge', 'acquire']):
            categories.append('mergers')
        if any(word in title for word in ['regulatory', 'sec', 'compliance', 'investigation']):
            categories.append('regulatory')
        if any(word in title for word in ['product', 'launch', 'release']):
            categories.append('product')
        
        return categories if categories else ['general']
    
    def get_technical_indicators(self, ticker: str) -> dict:
        """获取技术指标"""
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        
        if hist.empty:
            return {}
        
        close = hist['Close']
        volume = hist['Volume']
        
        # 计算指标
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, float('nan'))
        rsi = 100 - (100 / (1 + rs))
        
        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        
        return {
            'sma50': float(sma50),
            'sma200': float(sma200) if sma200 is not None else None,
            'rsi14': float(rsi.iloc[-1]),
            'macd': float(macd.iloc[-1]),
            'macd_signal': float(signal.iloc[-1]),
            'price': float(close.iloc[-1]),
            'volume': int(volume.iloc[-1])
        }
```

### 4. FMP API 适配器（备用）

```python
import requests
from typing import List, Dict

class FMPAdapter(DataSourceAdapter):
    """FMP API 数据适配器（需要付费订阅）"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/stable"
    
    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """统一的 API 请求方法"""
        url = f"{self.base_url}/{endpoint}"
        params = params or {}
        params['apikey'] = self.api_key
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def fetch_income_statement(self, ticker: str) -> List[FinancialStatement]:
        """获取利润表"""
        data = self._make_request("income-statement", {"symbol": ticker})
        
        statements = []
        for row in data:
            statements.append(FinancialStatement(
                year=row.get('calendarYear'),
                period='annual',
                revenue=row.get('revenue'),
                cost_of_revenue=row.get('costOfRevenue'),
                gross_profit=row.get('grossProfit'),
                ebitda=row.get('ebitda'),
                net_income=row.get('netIncome'),
                eps=row.get('eps'),
                # ... 其他字段
            ))
        return statements
    
    # 其他方法类似实现
```

### 5. 数据获取器（Facade 模式）

```python
class FinancialDataFetcher:
    """统一数据获取器"""
    
    def __init__(self, source: str = "yfinance", **config):
        """
        Args:
            source: 数据源类型 ('yfinance', 'fmp')
            config: 配置参数（如 FMP API key）
        """
        if source == "yfinance":
            self.adapter = YahooFinanceAdapter()
        elif source == "fmp":
            if 'api_key' not in config:
                raise ValueError("FMP adapter requires api_key")
            self.adapter = FMPAdapter(api_key=config['api_key'])
        else:
            raise ValueError(f"Unsupported data source: {source}")
    
    def get_company_data(self, ticker: str) -> CompanyData:
        """获取完整公司数据"""
        print(f"Fetching data for {ticker} from {type(self.adapter).__name__}...")
        
        return CompanyData(
            profile=self.adapter.fetch_company_profile(ticker),
            income_statements=self.adapter.fetch_income_statement(ticker),
            balance_sheets=self.adapter.fetch_balance_sheet(ticker),
            cash_flows=self.adapter.fetch_cash_flow(ticker),
            news=self.adapter.fetch_news(ticker, days=30, limit=20),
            technical_indicators=self.adapter.get_technical_indicators(ticker)
        )
    
    def get_ticker_data(self, tickers: List[str]) -> Dict[str, CompanyData]:
        """获取多个 ticker 的数据"""
        return {ticker: self.get_company_data(ticker) for ticker in tickers}
```

---

## 🔄 重构步骤

### Phase 1: 基础架构（本周）

1. ✅ 定义统一数据模型（`FinancialStatement`, `CompanyProfile`, `NewsItem`, `CompanyData`）
2. ✅ 创建适配器基类（`DataSourceAdapter`）
3. ✅ 实现 Yahoo Finance 适配器
4. ✅ 创建数据获取器（`FinancialDataFetcher`）

### Phase 2: 数据迁移（下周）

1. 重构 `market_data_api.py`，使用新适配器
2. 更新 `financial_data_processor.py`，适配新数据格式
3. 修复 PDF 生成逻辑（处理缺失数据）
4. 添加错误处理和降级逻辑

### Phase 3: 功能增强（下下周）

1. 实现 FMP 适配器（作为备用数据源）
2. 添加数据源自动切换逻辑
3. 实现新闻分类和 sentiment 分析
4. 添加缓存机制提升性能

### Phase 4: 优化和测试

1. 单元测试（mock 不同数据源）
2. 集成测试
3. 性能优化
4. 文档完善

---

## 💡 关键设计决策

### 1. 为什么使用适配器模式？

- **解耦**：业务逻辑不依赖具体数据源
- **可扩展**：添加新数据源只需实现接口
- **可测试**：轻松 mock 数据源进行测试
- **容错性**：可以配置多个数据源，自动切换

### 2. 为什么统一数据格式？

- **一致性**：所有业务逻辑处理相同格式
- **简化**：减少代码重复
- **可维护**：数据格式变更只需修改适配器

### 3. 如何处理缺失数据？

- **优雅降级**：缺失数据用 `None` 表示
- **智能填充**：使用默认值或估算值
- **明确警告**：在报告中标注数据缺失

### 4. 新闻模块设计

- **统一格式**：不同新闻源转换为相同 `NewsItem`
- **情感分析**：可选的 sentiment 评分
- **分类系统**：按主题分类（earnings, mergers, etc.）
- **多源聚合**：可以组合多个新闻源

---

## 📊 预期收益

### 当前问题
- ❌ FMP 免费计划不支持财务报表
- ❌ 代码与 FMP 强耦合
- ❌ 新闻模块失效
- ❌ 难以添加新数据源

### 重构后
- ✅ 支持多个数据源（Yahoo Finance, FMP, Alpha Vantage 等）
- ✅ 业务逻辑与数据源完全解耦
- ✅ 灵活的新闻模块设计
- ✅ 易于扩展和维护

### 代码量对比

| 模块 | 当前 | 重构后 | 说明 |
|------|------|--------|------|
| 数据获取 | ~800 行 | ~400 行 | 复用适配器 |
| 数据处理 | ~600 行 | ~300 行 | 统一格式 |
| 业务逻辑 | ~1000 行 | ~1000 行 | 无变化 |
| **总计** | **~2400 行** | **~1700 行** | **减少 ~30%** |

---

## 🚧 待审核问题

### 1. 架构设计
- [ ] 适配器模式是否过于复杂？
- [ ] 是否需要引入依赖注入框架？
- [ ] 数据模型是否足够抽象？

### 2. 性能考虑
- [ ] 是否需要缓存机制？
- [ ] 并发请求如何处理？
- [ ] 大数据量时性能如何优化？

### 3. 错误处理
- [ ] 数据源失败时的降级策略？
- [ ] 是否需要熔断器模式？
- [ ] 日志和监控如何设计？

### 4. 测试策略
- [ ] 如何 mock 外部 API？
- [ ] 单元测试覆盖率目标？
- [ ] 集成测试流程？

---

## 📚 参考资源

- [Adapter Pattern](https://refactoring.guru/design-patterns/adapter)
- [Python Data Classes](https://docs.python.org/3/library/dataclasses.html)
- [yfinance Documentation](https://yfinance.readthedocs.io/)
- [Financial Modeling Prep API](https://site.financialmodelingprep.com/developer/docs)

---

## 📝 版本历史

| 日期 | 作者 | 变更 |
|------|------|------|
| 2026-04-06 | AI Assistant | 初始版本 |

---

## ✅ 下一步行动

1. 等待其他 Agent 审核此设计
2. 根据反馈调整方案
3. 开始 Phase 1 实现
4. 逐步推进到 Phase 4

---

**备注**: 本文档为设计草稿，欢迎提出改进建议！
