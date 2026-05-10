#!/usr/bin/env python
# coding: utf-8

import argparse
import os
import pandas as pd
import json 

from modules.common_utils import load_config, get_api_key
from modules.financial_data_processor import calculate_growth_and_forecasts, extract_historical_metrics_from_api_data
from modules.market_data_api import (
    get_comprehensive_financial_data,
    combine_peer_financial_data,
    project_ebitda_for_peers,
    get_company_news
)
from modules.text_generator_agents import generate_text_section

# 新增模块导入
from modules.sensitivity_analyzer import SensitivityAnalyzer
from modules.catalyst_analyzer import CatalystAnalyzer
from modules.news_integrator import NewsIntegrator, get_enhanced_company_news
from modules.retail_sentiment_client import RetailSentimentClient

# 数据源适配器
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from finrobot_equity.core.src.data_sources import get_adapter

def main():
    parser = argparse.ArgumentParser(description="Generate financial analysis data using FMP API instead of PDF extraction.")
    
    # Company Identifiers
    parser.add_argument("--company-ticker", type=str, required=True, help="Stock ticker (e.g., AAPL).")
    parser.add_argument("--company-name", type=str, required=True, help="Full company name (e.g., Apple Inc.).")
    
    # API Configuration
    parser.add_argument("--config-file", type=str, default=None, help="Path to the configuration file (e.g., config.ini).")
    parser.add_argument("--years-limit", type=int, default=5, help="Number of years of historical data to fetch.")
    
    # Output Configuration
    parser.add_argument("--output-dir", type=str, help="Directory to save all outputs. Default: ./output/[TICKER]/analysis/")
    parser.add_argument("--output-csv-name", type=str, default="financial_metrics_and_forecasts.csv", help="Name for the output CSV file.")

    # Peer Analysis
    parser.add_argument("--peer-tickers", type=str, nargs="*", default=[], help="List of peer tickers for comparative analysis (e.g., GOOG MSFT).")

    # Text Generation
    parser.add_argument("--generate-text-sections", action="store_true", help="Enable generation of text sections using OpenAI.")
    parser.add_argument("--text-output-dir", type=str, default=None, help="Directory to save generated text files.")

    # NEWS PARAMETERS
    parser.add_argument("--news-days-back", type=int, default=5, help="Number of days to look back for company news (default: 5)")
    parser.add_argument("--news-limit", type=int, default=50, help="Maximum number of news articles to fetch (default: 50)")
    parser.add_argument("--retail-sentiment-days-back", type=int, default=7, help="Number of days to look back for retail sentiment insights (default: 7)")

    # 新增分析选项
    parser.add_argument("--enable-sensitivity-analysis", action="store_true", help="Enable sensitivity analysis for forecasts")
    parser.add_argument("--enable-catalyst-analysis", action="store_true", help="Enable catalyst identification and analysis")
    parser.add_argument("--enable-enhanced-news", action="store_true", help="Enable enhanced news integration with categorization")

    # 同行 comparables（A股专用）
    parser.add_argument("--comparables", type=str, nargs="*", default=[], help="同行 ticker 列表，用于 comparables table（仅 ths 数据源生效）")

    # Forecast Configuration
    parser.add_argument("--revenue-growth-2025", type=float, default=0.05, help="Revenue growth assumption for 2025E (default: 5%)")
    parser.add_argument("--revenue-growth-2026", type=float, default=0.06, help="Revenue growth assumption for 2026E (default: 6%)")
    parser.add_argument("--revenue-growth-2027", type=float, default=0.04, help="Revenue growth assumption for 2027E (default: 4%)")
    parser.add_argument("--margin-improvement", type=float, default=0.01, help="Annual margin improvement assumption (default: 1%)")
    parser.add_argument("--sga-margin-improvement", type=float, default=-0.005, help="SG&A margin change assumption (default: -0.5% efficiency gain)")

    # API Options
    parser.add_argument("--period", type=str, default="annual", choices=["annual", "quarterly"], help="Data period (annual or quarterly)")

    # Data Source Selection
    parser.add_argument("--data-source", type=str, default="auto", choices=["auto", "yahoo", "akshare", "eastmoney", "ths", "fmp"],
                       help="Data source: 'yahoo' (US), 'akshare' (A/sina), 'ths' (A/同花顺), 'eastmoney' (A/em), 'fmp' (paid), 'auto'")

    # Language
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"],
                       help="Report language: 'zh' (Chinese, default), 'en' (English)")

    args = parser.parse_args()

    # Setup output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.join(".", "output", args.company_ticker, "analysis")
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output will be saved to: {output_dir}")

    # Text output directory
    text_output_dir = args.text_output_dir if args.text_output_dir else output_dir
    if args.generate_text_sections:
        os.makedirs(text_output_dir, exist_ok=True)
        print(f"Text outputs will be saved to: {text_output_dir}")

    # Load configuration and API keys
    openai_base_url = None
    adanos_api_key = os.getenv("ADANOS_API_KEY")
    adanos_base_url = os.getenv("ADANOS_BASE_URL", "https://api.adanos.org")
    try:
        config = load_config(args.config_file)
        fmp_api_key = get_api_key(config, section="API_KEYS", key="fmp_api_key")
        adanos_api_key = config.get("API_KEYS", "adanos_api_key", fallback=adanos_api_key)
        adanos_base_url = config.get("API_KEYS", "adanos_base_url", fallback=adanos_base_url)
        if args.generate_text_sections:
            openai_api_key = get_api_key(config, section="API_KEYS", key="openai_api_key")
            # Try to get base_url for proxy services (like SiliconFlow)
            try:
                openai_base_url = get_api_key(config, section="API_KEYS", key="openai_base_url")
                print(f"Using OpenAI base URL: {openai_base_url}")
            except:
                pass  # base_url is optional
            # Try to get model name for proxy services
            try:
                openai_model = get_api_key(config, section="API_KEYS", key="openai_model")
                print(f"Using model: {openai_model}")
            except:
                openai_model = None  # model is optional
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Please ensure config.ini exists with valid API keys:")
        print("[API_KEYS]")
        print("fmp_api_key = YOUR_FMP_API_KEY")
        print("openai_api_key = YOUR_OPENAI_API_KEY")
        print("openai_base_url = https://api.xxx.com/v1  # optional, for proxy services")
        return

    print(f"Starting financial analysis for {args.company_name} ({args.company_ticker})")

    # 1. Fetch Financial Data — 适配器模式
    use_adapter = args.data_source in ('yahoo', 'akshare', 'eastmoney', 'ths', 'auto')
    company_data = None
    historical_metrics_df = None

    if use_adapter:
        source = args.data_source if args.data_source in ('yahoo', 'akshare', 'eastmoney', 'ths') else 'yahoo'
        print(f"Fetching financial data via {source} adapter...")
        try:
            adapter = get_adapter(source)
            company_data = adapter.fetch_all(
                ticker=args.company_ticker,
                period=args.period,
                limit=args.years_limit
            )

            # 通过适配器的统一数据模型生成 metrics DataFrame
            historical_metrics_df = company_data.to_metrics_dataframe()

            if historical_metrics_df is not None and not historical_metrics_df.empty:
                # 检查是否有有效数据
                data_cols = [c for c in historical_metrics_df.columns if c != 'metrics']
                has_data = any(
                    historical_metrics_df[col].apply(lambda x: x is not None and x == x).any()
                    for col in data_cols
                )
                if has_data:
                    available_years = [c.replace('A', '') for c in data_cols]
                    print(f"Successfully fetched {len(data_cols)} years via {adapter.name}")
                    print(f"Available years: {available_years}")
                else:
                    print(f"Warning: {adapter.name} returned empty data, falling back...")
                    historical_metrics_df = None
            else:
                print(f"Warning: {adapter.name} returned no data")
                historical_metrics_df = None

        except Exception as e:
            print(f"Adapter error: {e}")
            if args.data_source == 'yahoo':
                print("Yahoo adapter failed, exiting.")
                return
            print("Falling back to FMP API...")
            historical_metrics_df = None

    # Fallback to FMP API (original path)
    if historical_metrics_df is None:
        print(f"Fetching financial data from FMP API...")
        financial_data = get_comprehensive_financial_data(
            ticker=args.company_ticker,
            api_key=fmp_api_key,
            period=args.period,
            limit=args.years_limit
        )

        if financial_data.get('income_statement') is None or financial_data['income_statement'].empty:
            print("Error: Could not fetch data from any source. Exiting.")
            return

        print("Successfully fetched financial data from FMP API")
        income_df = financial_data['income_statement']
        print(f"Retrieved {len(income_df)} years of income statement data")
        available_years = sorted(income_df['year'].tolist(), reverse=True)
        print(f"Available years: {available_years}")

        print("Processing historical financial metrics...")
        historical_metrics_df = extract_historical_metrics_from_api_data(financial_data)

    if historical_metrics_df is None or historical_metrics_df.empty:
        print("Error: Failed to process historical metrics from any source. Exiting.")
        return

    print("\nHistorical Metrics Extracted:")
    print(historical_metrics_df.to_string())

    # 3. Forecasting
    print("Generating forecasts...")
    
    # Determine the latest actual year for base year
    actual_years = [col for col in historical_metrics_df.columns if col.endswith("A") and col != "metrics"]
    latest_year = max(actual_years) if actual_years else "2024A"
    
    print(f"Using {latest_year} as base year for forecasts")
    
    forecast_config = {
        "revenue_base_year": latest_year,
        "revenue_growth_assumptions": {
            "2025E": args.revenue_growth_2025, 
            "2026E": args.revenue_growth_2026, 
            "2027E": args.revenue_growth_2027
        }, 
        "ebitda_growth_factor": 1.05,
        "margin_improvement": {
            "Contribution Margin": args.margin_improvement, 
            "EBITDA Margin": args.margin_improvement
        },
        "sga_margin_change": args.sga_margin_improvement
    }
    
    print(f"Forecast assumptions:")
    print(f"  Revenue Growth 2025E: {args.revenue_growth_2025*100:.1f}%")
    print(f"  Revenue Growth 2026E: {args.revenue_growth_2026*100:.1f}%") 
    print(f"  Revenue Growth 2027E: {args.revenue_growth_2027*100:.1f}%")
    print(f"  Margin Improvement: {args.margin_improvement*100:.1f}% annually")
    print(f"  SG&A Efficiency: {args.sga_margin_improvement*100:.1f}% annually")
    
    final_data_df = calculate_growth_and_forecasts(historical_metrics_df, forecast_config)
    print("\nFinal Metrics with Forecasts:")
    print(final_data_df.to_string())

    # Save the main analysis file
    output_csv_path = os.path.join(output_dir, args.output_csv_name)
    final_data_df.to_csv(output_csv_path, index=False)
    print(f"Successfully saved financial analysis to: {output_csv_path}")

    # 4. Peer Comparison Analysis
    projected_peer_ebitda = None
    df_ev_ebitda_peers = None
    if args.peer_tickers and fmp_api_key:
        print(f"\nFetching data for peer comparison: {args.peer_tickers}")
        all_tickers = args.peer_tickers + [args.company_ticker]
        
        try:
            df_ebitda_peers, df_ev_ebitda_peers = combine_peer_financial_data(
                all_tickers, fmp_api_key, years_limit=args.years_limit
            )
            
            if df_ebitda_peers is not None and not df_ebitda_peers.empty:
                projected_peer_ebitda = project_ebitda_for_peers(df_ebitda_peers, num_projection_years=1)
                peer_ebitda_path = os.path.join(output_dir, "peer_ebitda_comparison.csv")
                projected_peer_ebitda.to_csv(peer_ebitda_path)
                print(f"Saved peer EBITDA comparison to: {peer_ebitda_path}")
            else:
                print("Warning: No peer EBITDA data could be retrieved")
            
            if df_ev_ebitda_peers is not None and not df_ev_ebitda_peers.empty:
                peer_ev_ebitda_path = os.path.join(output_dir, "peer_ev_ebitda_comparison.csv")
                df_ev_ebitda_peers.to_csv(peer_ev_ebitda_path)
                print(f"Saved peer EV/EBITDA comparison to: {peer_ev_ebitda_path}")
            else:
                print("Warning: No peer EV/EBITDA data could be retrieved")
                
        except Exception as e:
            print(f"Error fetching peer data: {e}")
            print("Continuing without peer comparison...")
    else:
        print("Skipping peer comparison (no peer tickers provided)")

    # 4.5 Fetch Company News
    company_news = None
    enhanced_news_data = None

    # 优先用适配器的新闻
    if company_data and company_data.news:
        print(f"\nUsing news from adapter ({len(company_data.news)} items)...")
        company_news = [
            {"title": n.title, "date": n.date.isoformat(), "source": n.source, "url": n.url}
            for n in company_data.news
        ]
        news_output_path = os.path.join(output_dir, "company_news.json")
        with open(news_output_path, 'w', encoding='utf-8') as f:
            json.dump(company_news, f, indent=2, ensure_ascii=False)
        print(f"Saved company news to: {news_output_path}")

    elif fmp_api_key:
        print(f"\nFetching company news for {args.company_ticker}...")
        try:
            if args.enable_enhanced_news:
                # 使用增强版新闻获取
                enhanced_news_data = get_enhanced_company_news(
                    ticker=args.company_ticker,
                    api_key=fmp_api_key,
                    days_back=args.news_days_back,
                    limit=args.news_limit
                )
                company_news = enhanced_news_data.get('articles', [])
                
                # 保存增强版新闻数据
                enhanced_news_path = os.path.join(output_dir, "enhanced_news.json")
                with open(enhanced_news_path, 'w', encoding='utf-8') as f:
                    json.dump(enhanced_news_data, f, indent=2, ensure_ascii=False)
                print(f"Saved enhanced news data to: {enhanced_news_path}")
                
                # 保存新闻摘要
                news_summary_path = os.path.join(output_dir, "news_summary.md")
                with open(news_summary_path, 'w', encoding='utf-8') as f:
                    f.write(enhanced_news_data.get('summary', ''))
                print(f"Saved news summary to: {news_summary_path}")
            else:
                # 使用原始新闻获取
                company_news = get_company_news(
                    ticker=args.company_ticker,
                    api_key=fmp_api_key,
                    days_back=args.news_days_back,
                    limit=args.news_limit
                )
            
            if company_news:
                news_output_path = os.path.join(output_dir, "company_news.json")
                with open(news_output_path, 'w', encoding='utf-8') as f:
                    json.dump(company_news, f, indent=2, ensure_ascii=False)
                print(f"Saved company news to: {news_output_path}")
            else:
                print("Warning: No news data could be retrieved")
        except Exception as e:
            print(f"Error fetching company news: {e}")
            print("Continuing without news data...")
    else:
        print("Skipping news fetch (no FMP API key)")

    # 4.55 Fetch Retail Sentiment Insights
    retail_sentiment_data = None
    if adanos_api_key:
        print(f"\nFetching retail sentiment insights for {args.company_ticker}...")
        try:
            retail_client = RetailSentimentClient(
                api_key=adanos_api_key,
                base_url=adanos_base_url,
            )
            retail_sentiment_data = retail_client.get_snapshot(
                args.company_ticker,
                days_back=args.retail_sentiment_days_back,
            )

            retail_sentiment_path = os.path.join(output_dir, "retail_sentiment.json")
            with open(retail_sentiment_path, "w", encoding="utf-8") as f:
                json.dump(retail_sentiment_data, f, indent=2, ensure_ascii=False)
            print(f"Saved retail sentiment insights to: {retail_sentiment_path}")
        except Exception as e:
            print(f"Error fetching retail sentiment insights: {e}")
            print("Continuing without retail sentiment insights...")
    else:
        print("Skipping retail sentiment insights (no ADANOS_API_KEY / adanos_api_key configured)")

    # 4.6 敏感性分析
    sensitivity_results = None
    if args.enable_sensitivity_analysis:
        print(f"\nPerforming sensitivity analysis...")
        try:
            sensitivity_analyzer = SensitivityAnalyzer(final_data_df)
            
            # 收入敏感性分析
            revenue_sensitivity = sensitivity_analyzer.analyze_revenue_sensitivity()
            
            # 利润率敏感性分析
            margin_sensitivity = sensitivity_analyzer.analyze_margin_sensitivity()
            
            # 综合敏感性表格
            combined_sensitivity = sensitivity_analyzer.generate_sensitivity_table()
            
            # 置信区间
            revenue_ci = sensitivity_analyzer.calculate_confidence_interval('Revenue')
            ebitda_ci = sensitivity_analyzer.calculate_confidence_interval('EBITDA')
            
            sensitivity_results = {
                'revenue_sensitivity': revenue_sensitivity.to_dict() if not revenue_sensitivity.empty else {},
                'margin_sensitivity': margin_sensitivity.to_dict() if not margin_sensitivity.empty else {},
                'combined_sensitivity': combined_sensitivity.to_dict() if not combined_sensitivity.empty else {},
                'confidence_intervals': sensitivity_analyzer.confidence_intervals,
                'summary': sensitivity_analyzer.generate_sensitivity_summary(language=args.language)
            }
            
            # 保存敏感性分析结果
            sensitivity_path = os.path.join(output_dir, "sensitivity_analysis.json")
            with open(sensitivity_path, 'w', encoding='utf-8') as f:
                json.dump(sensitivity_results, f, indent=2, default=str)
            print(f"Saved sensitivity analysis to: {sensitivity_path}")
            
            # 保存敏感性摘要
            sensitivity_summary_path = os.path.join(output_dir, "sensitivity_summary.md")
            with open(sensitivity_summary_path, 'w', encoding='utf-8') as f:
                f.write(sensitivity_results['summary'])
            print(f"Saved sensitivity summary to: {sensitivity_summary_path}")
            
        except Exception as e:
            print(f"Error performing sensitivity analysis: {e}")
            print("Continuing without sensitivity analysis...")

    # 4.7 催化剂分析
    catalyst_results = None
    if args.enable_catalyst_analysis and company_news:
        print(f"\nPerforming catalyst analysis...")
        try:
            catalyst_analyzer = CatalystAnalyzer(args.company_ticker, fmp_api_key, company_name=args.company_name, language=args.language)
            
            # 识别催化剂
            catalysts = catalyst_analyzer.identify_catalysts(company_news)
            
            # 分类催化剂
            categorized_catalysts = catalyst_analyzer.categorize_catalysts()
            
            # 获取顶级催化剂
            top_catalysts = catalyst_analyzer.get_top_catalysts(5)
            
            # 生成摘要
            catalyst_summary = catalyst_analyzer.generate_catalyst_summary()
            
            catalyst_results = {
                'catalysts': [
                    {
                        'event_type': c.event_type,
                        'description': c.description,
                        'expected_date': c.expected_date,
                        'impact_level': c.impact_level,
                        'probability': c.probability,
                        'sentiment': c.sentiment
                    }
                    for c in catalysts
                ],
                'categorized': {
                    k: [{'description': c.description, 'impact': c.impact_level} for c in v]
                    for k, v in categorized_catalysts.items()
                },
                'top_catalysts': top_catalysts,
                'summary': catalyst_summary
            }
            
            # 保存催化剂分析结果
            catalyst_path = os.path.join(output_dir, "catalyst_analysis.json")
            with open(catalyst_path, 'w', encoding='utf-8') as f:
                json.dump(catalyst_results, f, indent=2, default=str)
            print(f"Saved catalyst analysis to: {catalyst_path}")
            
            # 保存催化剂摘要
            catalyst_summary_path = os.path.join(output_dir, "catalyst_summary.md")
            with open(catalyst_summary_path, 'w', encoding='utf-8') as f:
                f.write(catalyst_summary)
            print(f"Saved catalyst summary to: {catalyst_summary_path}")
            
        except Exception as e:
            print(f"Error performing catalyst analysis: {e}")
            print("Continuing without catalyst analysis...")

    # 5. Text Generation (Unified Logic)
    if args.generate_text_sections:
        print("\nGenerating AI-powered text sections...")
        
        if 'openai_api_key' not in locals() or not openai_api_key:
            print("Error: OpenAI API key not loaded. Skipping text generation.")
        else:
            data_for_text_gen = {
                "financial_metrics": final_data_df,
                "peer_ebitda": projected_peer_ebitda,
                "peer_ev_ebitda": df_ev_ebitda_peers,
                "company_news": company_news,
                "enhanced_news": enhanced_news_data,
                "retail_sentiment": retail_sentiment_data,
                "sensitivity_analysis": sensitivity_results,
                "catalyst_analysis": catalyst_results
            }
            
            # A single list for all text types to be generated (including news_summary)
            all_text_types = [
                "tagline", "company_overview", "investment_overview", 
                "valuation_overview", "risks", "competitor_analysis", 
                "major_takeaways", "news_summary"  # NEW
            ]
            
            # A single loop calling the unified generation function
            for text_type in all_text_types:
                # Skip news_summary if no news data available
                if text_type == "news_summary" and not company_news:
                    print(f"Skipping 'news_summary' - no news data available")
                    # Create placeholder file
                    fallback_text = f"{args.company_name}（{args.company_ticker}）暂无近期新闻数据。" if args.language == 'zh' else f"No recent news available for {args.company_name} ({args.company_ticker})."
                    file_path = os.path.join(text_output_dir, f"{text_type}.txt")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(fallback_text)
                    print(f"Created placeholder for '{text_type}' at {file_path}")
                    continue
                
                print(f"Generating '{text_type}' for {args.company_name} ({args.company_ticker})...")
                try:
                    # Call the single, unified function for all types
                    generated_text = generate_text_section(
                        data_for_text_gen,
                        text_type,
                        openai_api_key,
                        args.company_name,
                        args.company_ticker,
                        base_url=openai_base_url,
                        model=openai_model,
                        language=args.language
                    )
                    
                    # Fallback validation — 双语支持
                    is_zh = args.language == 'zh'

                    if text_type == "competitor_analysis" and (not generated_text or len(generated_text) < 50):
                         print(f"⚠️ Warning: Competitor analysis seems too short, using fallback.")
                         generated_text = f"{args.company_name}凭借持续稳健的财务表现和相对于行业主要竞争对手的战略性市场定位，展现出良好的竞争态势。" if is_zh else f"{args.company_name} demonstrates competitive positioning within its industry sector through consistent financial performance and strategic market positioning relative to key competitors."

                    elif text_type == "major_takeaways":
                         # 中文版不检查 "Revenue Growth:" 英文关键词
                         has_sections = ("Revenue Growth:" in generated_text) or ("营收" in generated_text and "利润" in generated_text)
                         if not has_sections:
                             print(f"⚠️ Warning: Major takeaways missing required sections, using fallback.")
                             if is_zh:
                                 generated_text = f"营收增长：{args.company_name}的营收增长呈现持续向好趋势。\n\n毛利率：{args.company_name}的毛利率体现了良好的运营效能。\n\nSG&A费用率：{args.company_name}的管理及销售费用管理展现了严格的成本控制。\n\nEBITDA利润率：{args.company_name}的EBITDA利润率稳定性反映了扎实的基本面。"
                             else:
                                 generated_text = f"Revenue Growth: {args.company_name}'s revenue growth shows consistent performance trends.\n\nGross Profit Margin: {args.company_name}'s gross profit margins demonstrate operational effectiveness.\n\nSG&A Expense Margin: {args.company_name}'s SG&A expense management shows disciplined cost control.\n\nEBITDA Margin Stability: {args.company_name}'s EBITDA margin stability reflects strong underlying fundamentals."

                    elif text_type == "news_summary" and (not generated_text or len(generated_text) < 30):
                        print(f"⚠️ Warning: News summary seems too short, using fallback.")
                        generated_text = f"{args.company_name}近期新闻报道反映了市场对公司运营和战略举措的持续关注和发展动态。" if is_zh else f"Recent news coverage for {args.company_name} reflects ongoing market interest and developments in the company's operations and strategic initiatives."

                    file_path = os.path.join(text_output_dir, f"{text_type}.txt")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(generated_text)
                    print(f"✅ Successfully generated and saved '{text_type}' to {file_path}")
                    
                except Exception as e:
                    print(f"Error generating text for '{text_type}': {e}")
                    # Create a fallback file if generation fails
                    fallback_text = f"{args.company_name}（{args.company_ticker}）{text_type.replace('_', '')}分析暂不可用。" if args.language == 'zh' else f"{args.company_name} ({args.company_ticker}) {text_type.replace('_', ' ')} analysis not available."
                    file_path = os.path.join(text_output_dir, f"{text_type}.txt")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(fallback_text)
                    print(f"Created fallback text for '{text_type}' at {file_path}")
    else:
        print("Skipping text generation (not enabled)")

    # 6. Save additional financial statement data for reference
    print("\nSaving additional financial statement data...")

    if company_data is not None:
        # 适配器路径：保存统一格式的原始数据
        import dataclasses
        stmts = company_data.financial_statements
        if stmts:
            stmts_dicts = [s.to_dict() for s in stmts]
            stmts_df = pd.DataFrame(stmts_dicts)
            stmt_path = os.path.join(output_dir, "financial_statements_raw.csv")
            stmts_df.to_csv(stmt_path, index=False)
            print(f"Saved financial statements to: {stmt_path} ({len(stmts_df)} rows)")

        # 保存公司信息
        profile_path = os.path.join(output_dir, "company_profile.json")
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(dataclasses.asdict(company_data.profile), f, indent=2, ensure_ascii=False)
        print(f"Saved company profile to: {profile_path}")

        # 采集同行 comparables（仅 THS 路径）
        if hasattr(adapter, 'fetch_comparables'):
            main_ticker = adapter._normalize_ticker(args.company_ticker)

            # 优先用用户指定的 --comparables，否则自动找同行
            peer_list = [adapter._normalize_ticker(t) for t in args.comparables] if args.comparables else []
            if not peer_list and hasattr(adapter, 'fetch_auto_peers'):
                print(f"\n🔍 未指定同行，自动查找同行业公司...")
                peer_list = adapter.fetch_auto_peers(main_ticker, top_n=4)

            if peer_list:
                print(f"\n📊 采集同行估值数据: {peer_list}")
                all_tickers = [main_ticker] + [t for t in peer_list if t != main_ticker]
                comparables_data = adapter.fetch_comparables(all_tickers)

                # 补全主标的的 name
                for item in comparables_data:
                    if item.get('ticker') == main_ticker:
                        item['name'] = args.company_name

                comparables_path = os.path.join(output_dir, "comparables.json")
                with open(comparables_path, 'w', encoding='utf-8') as f:
                    json.dump(comparables_data, f, indent=2, ensure_ascii=False)
                print(f"Saved comparables to: {comparables_path}")

        # 保存技术指标
        if company_data.technical_indicators:
            tech_path = os.path.join(output_dir, "technical_indicators.json")
            with open(tech_path, 'w', encoding='utf-8') as f:
                json.dump(company_data.technical_indicators, f, indent=2)
            print(f"Saved technical indicators to: {tech_path}")
    elif 'financial_data' in dir():
        # FMP 路径：原始逻辑
        for statement_name, df in financial_data.items():
            if df is not None and not df.empty:
                statement_path = os.path.join(output_dir, f"{statement_name}_raw_data.csv")
                df.to_csv(statement_path, index=False)
                print(f"Saved {statement_name} to: {statement_path} ({len(df)} rows)")

    # 7. Create summary report
    all_text_types = ["tagline", "company_overview", "investment_overview", "valuation_overview", "risks", "competitor_analysis", "major_takeaways", "news_summary"]
    
    summary_data = {
        "company_ticker": args.company_ticker,
        "company_name": args.company_name,
        "analysis_date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_source": "Financial Modeling Prep API",
        "data_period": args.period,
        "years_analyzed": len(actual_years),
        "available_years": available_years,
        "latest_year": latest_year,
        "forecast_years": list(forecast_config["revenue_growth_assumptions"].keys()),
        "peer_tickers": args.peer_tickers,
        "news_days_back": args.news_days_back,
        "news_articles_fetched": len(company_news) if company_news else 0,
        "enhanced_news_enabled": args.enable_enhanced_news,
        "sensitivity_analysis_enabled": args.enable_sensitivity_analysis,
        "catalyst_analysis_enabled": args.enable_catalyst_analysis,
        "forecast_config": forecast_config,
        "files_generated": {
            "main_analysis": args.output_csv_name,
            "peer_ebitda": "peer_ebitda_comparison.csv" if projected_peer_ebitda is not None else None,
            "peer_ev_ebitda": "peer_ev_ebitda_comparison.csv" if df_ev_ebitda_peers is not None else None,
            "company_news": "company_news.json" if company_news else None,
            "enhanced_news": "enhanced_news.json" if enhanced_news_data else None,
            "sensitivity_analysis": "sensitivity_analysis.json" if sensitivity_results else None,
            "catalyst_analysis": "catalyst_analysis.json" if catalyst_results else None,
            "text_sections": all_text_types if args.generate_text_sections else []
        }
    }
    
    summary_path = os.path.join(output_dir, "analysis_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary_data, f, indent=2, default=str)
    print(f"Saved analysis summary to: {summary_path}")

    # 8. Print final summary and next steps
    print(f"\n" + "="*60)
    print(f"✅ Financial analysis completed successfully!")
    print(f"📁 All outputs saved to: {output_dir}")
    print(f"📊 Main analysis file: {output_csv_path}")
    if args.generate_text_sections:
        print(f"📝 AI text sections generated and saved in: {text_output_dir}")
    
    print(f"\n🚀 Ready to create equity report using:")
    print(f"python create_equity_report.py \\")
    print(f"  --company-ticker {args.company_ticker} \\")
    print(f"  --company-name \"{args.company_name}\" \\")
    print(f"  --analysis-csv {output_csv_path} \\")
    print(f"  --ratios-csv {os.path.join(output_dir, 'ratios_raw_data.csv')} \\")
    
    if args.peer_tickers and projected_peer_ebitda is not None:
        print(f"  --peer-ebitda-csv {os.path.join(output_dir, 'peer_ebitda_comparison.csv')} \\")
    if args.peer_tickers and df_ev_ebitda_peers is not None:
        print(f"  --peer-ev-ebitda-csv {os.path.join(output_dir, 'peer_ev_ebitda_comparison.csv')} \\")
    
    if args.generate_text_sections:
        for i, text_type in enumerate(all_text_types):
            param_name = text_type.replace('_', '-')
            file_path = os.path.join(text_output_dir, f'{text_type}.txt')
            # Add backslash for line continuation, except for the last item
            continuation = " \\" if i < len(all_text_types) - 1 else ""
            print(f"  --{param_name}-file {file_path}{continuation}")
    
    print(f"\n🎯 All files ready for report generation!")


if __name__ == "__main__":
    main()
