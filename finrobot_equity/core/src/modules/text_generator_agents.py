#!/usr/bin/env python
# coding: utf-8

import pandas as pd
from typing import Dict, Optional
from openai import OpenAI

from modules.retail_sentiment_client import format_retail_sentiment_for_prompt


def _get_fallback_text(prompt_type: str, company_name: str, language: str = None) -> str:
    """Returns fallback text when agent generation fails."""
    lang = language or DEFAULT_LANGUAGE

    fallbacks_en = {
        "tagline": f"{company_name} demonstrates strong financial fundamentals with consistent revenue growth and solid profitability metrics. The company maintains a competitive position in its market segment through operational efficiency and strategic initiatives. Strong balance sheet metrics support continued value creation for shareholders.",
        "company_overview": f"{company_name} operates as a prominent player in its industry sector, demonstrating consistent financial performance through strategic market positioning and operational excellence. The company has shown resilient growth patterns supported by strong demand dynamics and effective cost management strategies.",
        "investment_overview": f"{company_name} has delivered solid financial performance in recent periods, supported by strong operational execution and favorable market conditions. Revenue growth has been driven by robust demand and strategic initiatives, while margin improvements reflect operational efficiency gains.",
        "valuation_overview": f"{company_name} trades at reasonable valuation levels relative to its peer group, supported by strong fundamental metrics and growth prospects. The company's financial profile demonstrates consistent profitability and cash generation capabilities.",
        "risks": "Key risks include: (1) Industry competition and market share pressure, (2) Regulatory changes affecting operations, (3) Economic downturns impacting demand, (4) Technology disruption risks, (5) Supply chain and operational challenges.",
        "competitor_analysis": f"{company_name} demonstrates competitive positioning within its industry through consistent financial performance and strategic market positioning relative to key competitors in the sector.",
        "major_takeaways": f"Revenue Growth: {company_name}'s revenue growth shows consistent performance trends.\n\nGross Profit Margin: {company_name}'s gross profit margins demonstrate operational effectiveness.\n\nSG&A Expense Margin: {company_name}'s SG&A expense management shows disciplined cost control.\n\nEBITDA Margin Stability: {company_name}'s EBITDA margin stability reflects strong underlying fundamentals.",
        "news_summary": f"Recent news coverage for {company_name} reflects ongoing market interest and developments in the company's operations and strategic initiatives."
    }

    fallbacks_zh = {
        "tagline": f"{company_name}展现出稳健的财务基本面，营收保持持续增长，盈利能力指标稳健。公司凭借运营效率和战略举措在细分市场中维持了竞争优势地位。强劲的资产负债表指标支撑着为股东持续创造价值。",
        "company_overview": f"{company_name}是其行业领域的重要参与者，通过战略性市场定位和卓越的运营管理展现了持续稳健的财务表现。公司在强劲需求动能和有效成本管理策略的支撑下，呈现出韧性增长态势。",
        "investment_overview": f"{company_name}在近期展现了稳健的财务表现，得益于强劲的运营执行力和有利的市场环境。营收增长由强劲需求和战略举措驱动，利润率改善反映了运营效率的提升。",
        "valuation_overview": f"{company_name}的估值水平相对于同行处于合理区间，强劲的基本面指标和增长前景提供了支撑。公司的财务状况展示了持续的盈利能力和现金创造能力。",
        "risks": "主要风险包括：（1）行业竞争加剧和市场份额压力；（2）监管政策变化影响运营；（3）经济下行影响需求；（4）技术颠覆风险；（5）供应链和运营挑战。",
        "competitor_analysis": f"{company_name}凭借持续稳健的财务表现和相对于行业主要竞争对手的战略性市场定位，展现出良好的竞争态势。",
        "major_takeaways": f"营收增长：{company_name}的营收增长呈现持续向好趋势。\n\n毛利率：{company_name}的毛利率体现了良好的运营效能。\n\nSG&A费用率：{company_name}的SG&A费用管理展现了严格的成本控制。\n\nEBITDA利润率：{company_name}的EBITDA利润率稳定性反映了扎实的基本面。",
        "news_summary": f"{company_name}近期新闻报道反映了市场对公司运营和战略举措的持续关注和发展动态。"
    }

    fallbacks = fallbacks_zh if lang == "zh" else fallbacks_en
    return fallbacks.get(prompt_type, f"{company_name}的{prompt_type.replace('_', '')}分析。" if lang == "zh" else f"{company_name} analysis for {prompt_type.replace('_', ' ')} section.")


# System prompts for each text section
SYSTEM_PROMPTS = {
    "en": {
        "tagline": "You are an equity research analyst. Create a 3-sentence professional tagline summarizing the company's financial position. Be concise and professional. Do not use markdown.",
        "company_overview": "You are a financial analyst. Write a comprehensive company overview (300-400 words) covering business model, products/services, market position, and recent performance. Use plain text, no markdown.",
        "investment_overview": "You are an investment analyst. Write an investment update (200-300 words) covering recent financial performance, growth drivers, and outlook. Use plain text, no markdown.",
        "valuation_overview": "You are a valuation analyst. Write a valuation analysis (200-300 words) covering current valuation metrics, peer comparison, and fair value assessment. Use plain text, no markdown.",
        "risks": "You are a risk analyst. List 5 key investment risks in bullet point format. Be specific and concise.",
        "competitor_analysis": "You are a competitive analyst. Write a competitor analysis (200-300 words) comparing the company to its peers. Use plain text, no markdown.",
        "major_takeaways": "You are a financial analyst. Provide 4 major takeaways covering: Revenue Growth, Gross Profit Margin, SG&A Expense Margin, and EBITDA Margin. Format each with a header followed by 1-2 sentences.",
        "news_summary": "You are a financial news analyst. Summarize the recent news (200-300 words) highlighting key developments and their investment implications. Use plain text, no markdown.",
    },
    "zh": {
        "tagline": "你是一位资深券商股票研究分析师。请用3句话撰写专业的投资标语，概括公司的财务状况和投资价值。要求简洁专业，使用中文，不使用markdown格式。",
        "company_overview": "你是一位金融分析师。请撰写一份全面的公司概况（300-400字），涵盖商业模式、主要产品/服务、市场地位、竞争优势和近期业绩表现。使用中文纯文本，不使用markdown格式。",
        "investment_overview": "你是一位投资分析师。请撰写一份投资更新（200-300字），涵盖近期财务表现、增长驱动因素、行业趋势和未来展望。使用中文纯文本，不使用markdown格式。",
        "valuation_overview": "你是一位估值分析师。请撰写估值分析（200-300字），涵盖当前估值指标（PE/PB/EV/EBITDA）、同行比较、合理估值区间和投资建议。使用中文纯文本，不使用markdown格式。",
        "risks": "你是一位风险分析师。请列出5个关键投资风险，每个风险用一句话描述，包括风险类别和具体影响。使用中文，项目符号格式。",
        "competitor_analysis": "你是一位竞争分析师。请撰写竞争分析（200-300字），对比公司与主要竞争对手的市场份额、财务指标、技术优势和战略差异。使用中文纯文本，不使用markdown格式。",
        "major_takeaways": "你是一位金融分析师。请提供4个核心要点，分别涵盖：营收增长、毛利率、SG&A费用率和EBITDA利润率。每个要点包含一个标题和1-2句分析。使用中文。",
        "news_summary": "你是一位财经新闻分析师。请总结近期新闻动态（200-300字），突出关键事件及其对投资的影响。使用中文纯文本，不使用markdown格式。",
    },
}

# 默认语言
DEFAULT_LANGUAGE = "zh"


def _df_to_string(df: Optional[pd.DataFrame], name: str) -> str:
    """Converts a DataFrame to a markdown string for use in a prompt."""
    if df is None or df.empty:
        return f"{name}:\n[Data not available]\n"
    
    try:
        return f"{name}:\n{df.to_markdown()}\n"
    except Exception as e:
        return f"{name}:\n[Error formatting data: {e}]\n"


def _prepare_user_prompt(data: Dict, prompt_type: str, company_name: str, company_ticker: str) -> str:
    """Prepare user prompt with financial data."""
    financial_metrics = data.get('financial_metrics')
    peer_ebitda = data.get('peer_ebitda')
    peer_ev_ebitda = data.get('peer_ev_ebitda')
    company_news = data.get('company_news')
    retail_sentiment = data.get('retail_sentiment')
    
    prompt = f"Company: {company_name} ({company_ticker})\n\n"
    
    if financial_metrics is not None and not financial_metrics.empty:
        prompt += _df_to_string(financial_metrics, "Financial Metrics")
    
    if peer_ebitda is not None and not peer_ebitda.empty:
        prompt += _df_to_string(peer_ebitda, "Peer EBITDA Comparison")
        
    if peer_ev_ebitda is not None and not peer_ev_ebitda.empty:
        prompt += _df_to_string(peer_ev_ebitda, "Peer EV/EBITDA Comparison")
    
    if prompt_type == "news_summary" and company_news:
        prompt += f"\n## Recent News:\n"
        for i, article in enumerate(company_news[:10], 1):  # Limit to 10 articles
            prompt += f"{i}. {article.get('title', 'N/A')} ({article.get('publishedDate', 'N/A')[:10]})\n"
            prompt += f"   {article.get('text', 'N/A')[:200]}...\n\n"

    if prompt_type == "news_summary" and retail_sentiment:
        prompt += "\n" + format_retail_sentiment_for_prompt(retail_sentiment) + "\n"

    prompt += f"\nPlease provide the {prompt_type.replace('_', ' ')} based on the above data."
    # language hint 会通过 system prompt 控制，这里不需要额外处理
    return prompt


# 兼容旧调用：默认语言设置为中文
def set_default_language(lang: str):
    """设置默认语言 ('zh' 或 'en')"""
    global DEFAULT_LANGUAGE
    DEFAULT_LANGUAGE = lang


def generate_text_section(data: Dict, prompt_type: str, api_key: str, company_name: str, company_ticker: str, base_url: str = None, model: str = None, language: str = None) -> str:
    """
    Generates a specific text section for the equity report using OpenAI Chat API.
    
    Args:
        data: Financial data dictionary
        prompt_type: Type of text section to generate
        api_key: OpenAI API key
        company_name: Company name
        company_ticker: Stock ticker
        base_url: Optional API base URL (for proxy services like SiliconFlow)
        model: Optional model name (default: gpt-4o-mini or configured model)
    """
    
    global DEFAULT_LANGUAGE
    lang = language or DEFAULT_LANGUAGE
    # 更新全局默认语言，确保 fallback 也用同一语言
    DEFAULT_LANGUAGE = lang

    print(f"🤖 Generating '{prompt_type}' text section... (lang={lang})")

    # Validate API key
    if not api_key:
        print(f"⚠️ Warning: No API key provided. Using fallback text for '{prompt_type}'.")
        return _get_fallback_text(prompt_type, company_name, language=lang)
    
    # Determine model to use
    default_model = "gpt-4o-mini"
    if model:
        default_model = model
    
    # Create OpenAI client
    try:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
            print(f"📡 Using API base URL: {base_url}")
        
        client = OpenAI(**client_kwargs)
        print(f"🤖 Using model: {default_model}")
    except Exception as e:
        print(f"⚠️ Warning: Could not create OpenAI client: {e}")
        return _get_fallback_text(prompt_type, company_name, language=DEFAULT_LANGUAGE)
    
    # Get system prompt based on language
    lang = language or DEFAULT_LANGUAGE
    lang_prompts = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["en"])
    system_prompt = lang_prompts.get(prompt_type, f"You are a financial analyst. Provide {prompt_type.replace('_', ' ')} analysis.")
    
    # Prepare user prompt with data
    user_prompt = _prepare_user_prompt(data, prompt_type, company_name, company_ticker)
    
    # Call OpenAI API
    try:
        response = client.chat.completions.create(
            model=default_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        generated_text = response.choices[0].message.content.strip()
        
        if generated_text:
            print(f"✅ Successfully generated '{prompt_type}' ({len(generated_text)} chars)")
            return generated_text
        else:
            print(f"⚠️ Warning: Empty response for '{prompt_type}'")
            return _get_fallback_text(prompt_type, company_name, language=DEFAULT_LANGUAGE)
            
    except Exception as e:
        print(f"❌ Error generating '{prompt_type}': {e}")
        return _get_fallback_text(prompt_type, company_name, language=DEFAULT_LANGUAGE)

# Backward compatibility - keep old function signature
def _query_openai(prompt: str, api_key: str) -> str:
    """Legacy function for backward compatibility."""
    return "Text generation now handled by agents."

if __name__ == '__main__':
    print("Testing agent-based text_generator...")
