"""
统一数据模型 — 所有数据源适配器输出到这些 dataclass，所有业务逻辑从这里读取。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class FinancialStatement:
    """统一财务报表格式"""
    year: int
    period: str = 'annual'  # 'annual' or 'quarterly'

    # Income Statement
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_expenses: Optional[float] = None
    sga_expenses: Optional[float] = None
    ebitda: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None

    # Balance Sheet
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    shareholders_equity: Optional[float] = None
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None

    # Cash Flow
    operating_cash_flow: Optional[float] = None
    investing_cash_flow: Optional[float] = None
    financing_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    capital_expenditure: Optional[float] = None

    # Ratios (computed or fetched)
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None
    net_margin: Optional[float] = None
    sga_margin: Optional[float] = None
    revenue_growth: Optional[float] = None
    pe_ratio: Optional[float] = None
    roe: Optional[float] = None

    def compute_margins(self):
        """从原始数据计算 margin 指标"""
        if self.revenue and self.revenue != 0:
            if self.gross_profit is not None and self.gross_margin is None:
                self.gross_margin = self.gross_profit / self.revenue
            if self.operating_income is not None and self.operating_margin is None:
                self.operating_margin = self.operating_income / self.revenue
            if self.ebitda is not None and self.ebitda_margin is None:
                self.ebitda_margin = self.ebitda / self.revenue
            if self.net_income is not None and self.net_margin is None:
                self.net_margin = self.net_income / self.revenue
            if self.sga_expenses is not None and self.sga_margin is None:
                self.sga_margin = self.sga_expenses / self.revenue

    def to_dict(self) -> dict:
        """转为字典，方便构建 DataFrame"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class CompanyProfile:
    """统一公司信息格式"""
    ticker: str
    name: str = ''
    sector: str = ''
    industry: str = ''
    description: Optional[str] = None

    # Market Data
    price: Optional[float] = None
    market_cap: Optional[float] = None
    volume: Optional[int] = None

    # Ratios
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None

    # Other
    exchange: str = ''
    country: str = ''
    currency: str = 'USD'
    employees: Optional[int] = None
    website: Optional[str] = None


@dataclass
class NewsItem:
    """统一新闻格式"""
    date: datetime = field(default_factory=datetime.now)
    title: str = ''
    content: str = ''
    source: str = ''
    url: Optional[str] = None
    sentiment_score: Optional[float] = None  # -1.0 to 1.0
    categories: List[str] = field(default_factory=list)


@dataclass
class CompanyData:
    """统一的公司数据容器 — 适配器的最终输出"""
    profile: CompanyProfile = field(default_factory=lambda: CompanyProfile(ticker=''))
    financial_statements: List[FinancialStatement] = field(default_factory=list)
    news: List[NewsItem] = field(default_factory=list)
    technical_indicators: dict = field(default_factory=dict)

    def get_statement_by_year(self, year: int) -> Optional[FinancialStatement]:
        for s in self.financial_statements:
            if s.year == year:
                return s
        return None

    def get_years(self) -> List[int]:
        return sorted(set(s.year for s in self.financial_statements), reverse=True)

    def to_metrics_dataframe(self):
        """转换为 financial_data_processor 期望的 DataFrame 格式"""
        import pandas as pd

        if not self.financial_statements:
            return None

        # 按年排序（最新在前）
        stmts = sorted(self.financial_statements, key=lambda s: s.year, reverse=True)

        # 计算 margins
        for s in stmts:
            s.compute_margins()

        # 计算 revenue growth
        for i in range(len(stmts) - 1):
            curr = stmts[i]
            prev = stmts[i + 1]
            if curr.revenue and prev.revenue and prev.revenue != 0:
                curr.revenue_growth = (curr.revenue - prev.revenue) / prev.revenue

        years = [f"{s.year}A" for s in stmts]

        # 定义 metrics 映射：(display_name, attr_name, is_margin)
        metrics_spec = [
            ('Revenue', 'revenue', False),
            ('Cost of Operations', 'cost_of_revenue', False),
            ('SG&A', 'sga_expenses', False),
            ('Contribution Profit', 'gross_profit', False),
            ('Contribution Margin', 'gross_margin', True),
            ('EBITDA', 'ebitda', False),
            ('EBITDA Margin', 'ebitda_margin', True),
            ('SG&A Margin', 'sga_margin', True),
            ('Revenue Growth', 'revenue_growth', True),
            ('EPS', 'eps', False),
            ('PE Ratio', 'pe_ratio', False),
        ]

        data = {'metrics': [m[0] for m in metrics_spec]}
        for i, stmt in enumerate(stmts):
            col = years[i]
            data[col] = []
            for metric_name, attr_name, is_margin in metrics_spec:
                val = getattr(stmt, attr_name, None)
                # Margins 输出为百分比字符串（与 FMP 路径一致，forecast 函数需要这个格式）
                if is_margin and val is not None and not (isinstance(val, float) and pd.isna(val)):
                    data[col].append(f"{val*100:.1f}%")
                else:
                    data[col].append(val)

        return pd.DataFrame(data)
