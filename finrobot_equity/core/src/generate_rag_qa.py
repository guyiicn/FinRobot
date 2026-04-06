#!/usr/bin/env python
# coding: utf-8
"""
RAG 问答系统 — 对已生成的报告/文档进行智能问答。

支持两种模式：
  1. 交互式问答（默认）：加载文档后进入对话循环
  2. 单次问答：--question 参数直接提问

用法:
  # 对茅台研报进行问答
  python3 generate_rag_qa.py \\
      --docs ./output/600519_maotai/report/Professional_Equity_Report_600519.pdf \\
      --collection maotai_report \\
      --language zh --config-file ../config/config.ini

  # 单次提问
  python3 generate_rag_qa.py \\
      --docs ./output/600519_maotai/report/*.pdf \\
      --question "茅台的EBITDA利润率是多少？" \\
      --config-file ../config/config.ini

  # 加载多个文档
  python3 generate_rag_qa.py \\
      --docs ./output/600519/annual_report/600519_Annual_Report_FY2024.pdf \\
            ./output/600519_maotai/report/Professional_Equity_Report_600519.pdf \\
      --collection maotai_all \\
      --config-file ../config/config.ini
"""

import argparse
import os
import sys
import glob
import hashlib
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.common_utils import load_config, get_api_key


# ═══════════════════════════════════════════════════════════════
# 文档加载与分块
# ═══════════════════════════════════════════════════════════════

def _extract_text_from_pdf(pdf_path: str) -> str:
    """从 PDF 提取文本"""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return '\n\n'.join(text_parts)
    except Exception as e:
        print(f"  ⚠️ pdfplumber failed for {pdf_path}: {e}")
        # fallback to pdfminer
        try:
            from pdfminer.high_level import extract_text
            return extract_text(pdf_path)
        except Exception as e2:
            print(f"  ⚠️ pdfminer also failed: {e2}")
            return ''


def _extract_text_from_txt(txt_path: str) -> str:
    with open(txt_path, 'r', encoding='utf-8') as f:
        return f.read()


def load_documents(paths: List[str]) -> List[dict]:
    """加载文档列表，返回 [{source, text}]"""
    docs = []
    expanded = []
    for p in paths:
        expanded.extend(glob.glob(p))

    for path in expanded:
        path = os.path.abspath(path)
        if not os.path.exists(path):
            print(f"  ⚠️ File not found: {path}")
            continue

        ext = os.path.splitext(path)[1].lower()
        print(f"  📄 Loading: {os.path.basename(path)}")

        if ext == '.pdf':
            text = _extract_text_from_pdf(path)
        elif ext in ('.txt', '.md', '.csv', '.json'):
            text = _extract_text_from_txt(path)
        else:
            print(f"  ⚠️ Unsupported format: {ext}")
            continue

        if text.strip():
            docs.append({'source': os.path.basename(path), 'text': text, 'path': path})
            print(f"    ✅ {len(text)} chars extracted")
        else:
            print(f"    ⚠️ No text extracted")

    return docs


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """将文本分块"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        # 尝试在句号处断开
        if end < len(text):
            for sep in ['。\n', '.\n', '\n\n', '。', '.', '\n']:
                last = chunk.rfind(sep)
                if last > chunk_size * 0.5:
                    end = start + last + len(sep)
                    chunk = text[start:end]
                    break
        chunks.append(chunk.strip())
        start = end - overlap
    return [c for c in chunks if len(c) > 20]


# ═══════════════════════════════════════════════════════════════
# 向量数据库
# ═══════════════════════════════════════════════════════════════

class RAGStore:
    """基于 ChromaDB 的 RAG 存储"""

    def __init__(self, collection_name: str = 'finrobot_docs',
                 persist_dir: str = None, openai_api_key: str = None):
        import chromadb

        self.persist_dir = persist_dir or os.path.join(os.path.expanduser('~'), '.finrobot_rag')
        os.makedirs(self.persist_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.persist_dir)

        # 使用 OpenAI embedding 或默认
        if openai_api_key:
            try:
                from chromadb.utils import embedding_functions
                self.ef = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=openai_api_key,
                    model_name="text-embedding-3-small",
                )
                print(f"  📐 Embedding: OpenAI text-embedding-3-small")
            except Exception as e:
                print(f"  ⚠️ OpenAI embedding failed: {e}, using default")
                self.ef = None
        else:
            self.ef = None

        kwargs = {'name': collection_name}
        if self.ef:
            kwargs['embedding_function'] = self.ef

        self.collection = self.client.get_or_create_collection(**kwargs)
        print(f"  📦 Collection '{collection_name}': {self.collection.count()} chunks")

    def add_documents(self, docs: List[dict], chunk_size: int = 800):
        """添加文档到向量库"""
        all_chunks = []
        all_ids = []
        all_meta = []

        for doc in docs:
            chunks = chunk_text(doc['text'], chunk_size=chunk_size)
            for i, chunk in enumerate(chunks):
                doc_id = hashlib.md5(f"{doc['source']}_{i}".encode()).hexdigest()
                all_chunks.append(chunk)
                all_ids.append(doc_id)
                all_meta.append({'source': doc['source'], 'chunk_idx': i})

        if all_chunks:
            # 批量添加（chromadb 限制每次最多 5461 条）
            batch = 500
            for start in range(0, len(all_chunks), batch):
                end = min(start + batch, len(all_chunks))
                self.collection.upsert(
                    documents=all_chunks[start:end],
                    ids=all_ids[start:end],
                    metadatas=all_meta[start:end],
                )
            print(f"  ✅ Added {len(all_chunks)} chunks, total: {self.collection.count()}")

    def query(self, question: str, n_results: int = 5) -> List[dict]:
        """检索相关文档片段"""
        results = self.collection.query(
            query_texts=[question],
            n_results=min(n_results, self.collection.count()),
        )
        contexts = []
        if results and results['documents']:
            for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                contexts.append({'text': doc, 'source': meta.get('source', '')})
        return contexts


# ═══════════════════════════════════════════════════════════════
# 问答引擎
# ═══════════════════════════════════════════════════════════════

QA_PROMPTS = {
    'zh': (
        "你是一位专业的金融分析助手。请根据以下检索到的文档内容回答用户的问题。\n"
        "如果文档中没有足够信息，请诚实地说明。\n"
        "回答要准确、简洁，引用具体数据时标注来源文档。使用中文回答。"
    ),
    'en': (
        "You are a professional financial analysis assistant. Answer the user's question "
        "based on the retrieved document context below.\n"
        "If the context doesn't contain enough information, say so honestly.\n"
        "Be accurate, concise, and cite specific data with source documents."
    ),
}


def answer_question(question: str, store: RAGStore, api_key: str,
                    base_url: str = None, model: str = None,
                    language: str = 'zh', n_results: int = 5) -> str:
    """检索相关内容并回答问题"""
    # 检索
    contexts = store.query(question, n_results=n_results)
    if not contexts:
        return "未找到相关文档内容。" if language == 'zh' else "No relevant documents found."

    # 构建上下文
    context_text = ""
    for i, ctx in enumerate(contexts, 1):
        context_text += f"\n--- 文档片段 {i} (来源: {ctx['source']}) ---\n{ctx['text']}\n"

    system_prompt = QA_PROMPTS.get(language, QA_PROMPTS['en'])
    user_prompt = f"检索到的文档内容:\n{context_text}\n\n用户问题: {question}"

    if not api_key:
        return f"[No API key]\n\nRetrieved context:\n{context_text}"

    try:
        from openai import OpenAI
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        resp = client.chat.completions.create(
            model=model or 'gpt-4o-mini',
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"回答生成失败: {e}\n\n检索到的内容:\n{context_text}"


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="RAG Q&A on Financial Reports")
    parser.add_argument("--docs", type=str, nargs="+", required=True,
                        help="Document paths (PDF/TXT, supports glob)")
    parser.add_argument("--collection", type=str, default="finrobot_docs",
                        help="ChromaDB collection name")
    parser.add_argument("--question", type=str, default=None,
                        help="Single question (skip interactive mode)")
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--config-file", type=str, default=None)
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--n-results", type=int, default=5)
    parser.add_argument("--rebuild", action="store_true",
                        help="Force rebuild vector index")

    args = parser.parse_args()

    # 加载配置
    api_key = base_url = model = None
    try:
        config = load_config(args.config_file)
        api_key = get_api_key(config, "API_KEYS", "openai_api_key")
        try: base_url = get_api_key(config, "API_KEYS", "openai_base_url")
        except: pass
        try: model = get_api_key(config, "API_KEYS", "openai_model")
        except: pass
    except Exception as e:
        print(f"⚠️ Config error: {e}")

    print(f"\n{'=' * 60}")
    print(f"🔍 RAG Q&A — Financial Document Assistant")
    print(f"{'=' * 60}")

    # 初始化向量库
    if args.rebuild:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(os.path.expanduser('~'), '.finrobot_rag'))
        try:
            client.delete_collection(args.collection)
            print(f"  🗑️ Deleted collection '{args.collection}'")
        except:
            pass

    store = RAGStore(
        collection_name=args.collection,
        openai_api_key=api_key,
    )

    # 加载文档（如果库是空的或强制重建）
    if store.collection.count() == 0 or args.rebuild:
        print(f"\n📥 Loading documents...")
        docs = load_documents(args.docs)
        if docs:
            store.add_documents(docs, chunk_size=args.chunk_size)
        else:
            print("❌ No documents loaded. Exiting.")
            return
    else:
        print(f"  📦 Using existing index ({store.collection.count()} chunks)")

    print(f"{'=' * 60}\n")

    # 单次问答模式
    if args.question:
        print(f"❓ {args.question}\n")
        answer = answer_question(
            args.question, store, api_key, base_url, model,
            args.language, args.n_results,
        )
        print(f"💡 {answer}")
        return

    # 交互式问答模式
    prompt = "请输入问题（输入 quit 退出）：" if args.language == 'zh' else "Enter question (type 'quit' to exit): "
    print(f"💬 {'进入交互式问答模式' if args.language == 'zh' else 'Interactive Q&A mode'}")
    print(f"   {'输入 quit/exit 退出' if args.language == 'zh' else 'Type quit/exit to leave'}\n")

    while True:
        try:
            question = input(f"❓ {prompt}").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not question or question.lower() in ('quit', 'exit', 'q', '退出'):
            break

        answer = answer_question(
            question, store, api_key, base_url, model,
            args.language, args.n_results,
        )
        print(f"\n💡 {answer}\n")

    print("\n👋 Bye!")


if __name__ == '__main__':
    main()
