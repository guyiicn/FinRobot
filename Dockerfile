# FinRobot Docker Image v2
# 基于已有镜像增量构建，避免重新下载 base image
# 支持: 股票研究报告/年报/市场预测/RAG问答/K线分析/策略回测

FROM finrobot-finrobot:latest

LABEL version="2.0"
LABEL description="FinRobot v2: Full 8-module AI Financial Analysis Platform"

# 安装新增的 Python 依赖
RUN pip install --no-cache-dir \
        "pyautogen==0.2.35" \
        akshare \
        mplfinance \
        backtrader \
        pdfplumber \
        chromadb \
        python-dotenv \
        finnhub-python \
    || echo "Some packages may have failed, continuing..."

# 复制更新后的代码（覆盖旧代码）
COPY finrobot_equity/ /app/finrobot_equity/
COPY finrobot/ /app/finrobot/

# 确保目录存在
RUN mkdir -p /app/output /app/finrobot_equity/logs /app/finrobot_equity/core/config

WORKDIR /app

# 验证关键模块可用
RUN python -c "import akshare; print('akshare OK')" && \
    python -c "import mplfinance; print('mplfinance OK')" && \
    python -c "import backtrader; print('backtrader OK')" && \
    python -c "import chromadb; print('chromadb OK')" && \
    python -c "import autogen; print('autogen OK:', autogen.__version__)" && \
    python -c "import reportlab; print('reportlab OK')" && \
    echo "All modules verified!"

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health', timeout=5)" || exit 1

CMD ["python", "run_web_app.py", "--host", "0.0.0.0", "--port", "8001", "--no-reload"]
