#!/bin/bash
# FinRobot A股研究报告工作流 — 一键生成摩根风格PDF
# 用法: ./finrobot_report.sh <ticker> <公司名> [peers...] [--theme ms|cicc|cms|dachen]

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 解析参数
if [ $# -lt 2 ]; then
    echo "用法: $0 <ticker> <公司名> [peer1 peer2 ...] [--theme ms]"
    echo ""
    echo "示例:"
    echo "  $0 300413.SZ \"芒果超媒\" 002027 300133 300027"
    echo "  $0 301062.SZ \"上海艾录\" 002831 002014 002228 --theme cicc"
    exit 1
fi

TICKER="$1"
COMPANY_NAME="$2"
shift 2

# 解析 peers 和 theme
PEERS=()
THEME="ms"

while [ $# -gt 0 ]; do
    case "$1" in
        --theme)
            THEME="$2"
            shift 2
            ;;
        *)
            PEERS+=("$1")
            shift
            ;;
    esac
done

echo -e "${GREEN}=== FinRobot A股研究报告工作流 ===${NC}"
echo "股票代码: $TICKER"
echo "公司名称: $COMPANY_NAME"
echo "同行公司: ${PEERS[*]:-自动查找}"
echo "PDF 主题: $THEME"
echo ""

# 路径
WORKSPACE="/home/guyii/clawd/code/FinRobot"
ANALYSIS_DIR="/app/skill_output/$(echo $TICKER | cut -d. -f1)/report/analysis"
OUTPUT_DIR="/tmp/finrobot_reports"
mkdir -p "$OUTPUT_DIR"

# 进入工作目录
cd "$WORKSPACE"

# ============================================================================
# Step 1: FinRobot 数据采集
# ============================================================================
echo -e "${YELLOW}[1/4] FinRobot 数据采集...${NC}"

PEERS_ARGS=""
if [ ${#PEERS[@]} -gt 0 ]; then
    PEERS_ARGS="--comparables ${PEERS[*]}"
fi

docker exec finrobot_run bash -c "
cd /app/finrobot_equity/core/src && \
python generate_financial_analysis.py \
  --company-ticker $TICKER \
  --company-name '$COMPANY_NAME' \
  --data-source ths \
  --years-limit 5 \
  --language zh \
  --generate-text-sections \
  --enable-sensitivity-analysis \
  --enable-catalyst-analysis \
  --config-file ../config/config.ini \
  --output-dir $ANALYSIS_DIR \
  $PEERS_ARGS
" 2>&1 | tail -20

echo -e "${GREEN}✅ FinRobot 数据采集完成${NC}"

# ============================================================================
# Step 2: 格式转换
# ============================================================================
echo -e "${YELLOW}[2/4] 格式转换 FinRobot → typeset...${NC}"

# 复制 analysis 目录到宿主机（避免容器内权限问题）
docker cp finrobot_run:$ANALYSIS_DIR /tmp/finrobot_analysis_$(echo $TICKER | cut -d. -f1)
LOCAL_ANALYSIS="/tmp/finrobot_analysis_$(echo $TICKER | cut -d. -f1)"

python3 scripts/finrobot_to_typeset.py \
  "$LOCAL_ANALYSIS" \
  "$COMPANY_NAME" \
  "$TICKER" \
  "$THEME" > /tmp/convert.log 2>&1

JSON_PATH=$(grep OUTPUT_PATH /tmp/convert.log | cut -d= -f2)

echo -e "${GREEN}✅ 格式转换完成: $JSON_PATH${NC}"

# ============================================================================
# Step 3: PDF 渲染
# ============================================================================
echo -e "${YELLOW}[3/4] typeset-engine 渲染 PDF ($THEME 主题)...${NC}"

PDF_OUTPUT="$OUTPUT_DIR/${TICKER}_${THEME}_report.pdf"

curl -s -X POST http://localhost:9091/render/pdf \
  -H "Content-Type: application/json" \
  -d @"$JSON_PATH" \
  -o "$PDF_OUTPUT"

PAGE_COUNT=$(python3 -c "from pypdf import PdfReader; print(len(PdfReader('$PDF_OUTPUT').pages))")
FILE_SIZE=$(du -h "$PDF_OUTPUT" | cut -f1)

echo -e "${GREEN}✅ PDF 生成完成: $PDF_OUTPUT${NC}"
echo "   页数: $PAGE_COUNT, 大小: $FILE_SIZE"

# ============================================================================
# Step 4: 发送到 Telegram
# ============================================================================
echo -e "${YELLOW}[4/4] 发送到 Telegram...${NC}"

CAPTION="📊 ${COMPANY_NAME}(${TICKER}) 研究报告 — ${THEME}风格 | FinRobot + typeset-engine | 含同行估值对比"

HTTPS_PROXY=http://127.0.0.1:7890 curl -s --max-time 60 \
  -F chat_id=60555976 \
  -F document=@"$PDF_OUTPUT" \
  -F caption="$CAPTION" \
  "https://api.telegram.org/bot8250723750:AAH0Yv0hj6CpHv9A0eyCa3vveQqg4ZSvhx4/sendDocument" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('✅ 发送成功' if r.get('ok') else f'❌ {r.get(\"description\", r)}')"

echo ""
echo -e "${GREEN}=== 工作流完成 ===${NC}"
echo "PDF 本地路径: $PDF_OUTPUT"
echo "JSON 数据: $JSON_PATH"
echo "Analysis 目录: $LOCAL_ANALYSIS"
