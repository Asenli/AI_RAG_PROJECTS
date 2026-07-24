#!/bin/bash
# ============================================================
# 食安团餐售后智能助手 — 一键启动 (Linux 服务器)
# 用法: bash start.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  食安团餐售后智能助手 — 启动中...${NC}"
echo -e "${CYAN}========================================${NC}"

# ===== 1. 加载 .env =====
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${GREEN}[1/4] 加载 .env 环境变量${NC}"
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
else
    echo -e "${YELLOW}[1/4] 未找到 .env 文件，请确保环境变量已设置${NC}"
fi

# 检查必要的 API Key
for var in DEEPSEEK_API_KEY SILICONFLOW_API_KEY; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}  ⚠️  环境变量 $var 未设置!${NC}"
    else
        echo -e "  ✅ $var=${!var:0:12}..."
    fi
done

# ===== 2. 安装依赖 =====
echo -e "${GREEN}[2/4] 安装后端依赖...${NC}"
cd "$SCRIPT_DIR/backend"
pip install -r requirements.txt -q 2>&1 | tail -1
echo -e "  ✅ 后端依赖就绪"

# ===== 3. 启动后端 =====
echo -e "${GREEN}[3/4] 启动 FastAPI 后端...${NC}"

# 先杀掉旧进程
if [ -f "$SCRIPT_DIR/backend.pid" ]; then
    OLD_PID=$(cat "$SCRIPT_DIR/backend.pid")
    kill $OLD_PID 2>/dev/null && echo "  已停止旧进程 PID=$OLD_PID" || true
    rm -f "$SCRIPT_DIR/backend.pid"
fi
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

nohup uvicorn app.main:app --host 0.0.0.0 --port 5002 \
    > "$SCRIPT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$SCRIPT_DIR/backend.pid"
sleep 2

if kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "  ✅ 后端已启动 PID=$BACKEND_PID"
    echo -e "  API 文档: http://$(hostname -I | awk '{print $1}'):5002/docs"
else
    echo -e "${RED}  ❌ 后端启动失败，查看日志: cat $SCRIPT_DIR/backend.log${NC}"
fi

# ===== 4. 启动前端 =====
echo -e "${GREEN}[4/4] 启动 Vue 前端...${NC}"

cd "$SCRIPT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    echo "  安装前端依赖..."
    npm install --silent 2>&1 | tail -1
fi

# 杀掉旧前端进程
if [ -f "$SCRIPT_DIR/frontend.pid" ]; then
    OLD_PID=$(cat "$SCRIPT_DIR/frontend.pid")
    kill $OLD_PID 2>/dev/null || true
    rm -f "$SCRIPT_DIR/frontend.pid"
fi
pkill -f "vite" 2>/dev/null || true
sleep 1

nohup npx vite --host 0.0.0.0 --port 5173 \
    > "$SCRIPT_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$SCRIPT_DIR/frontend.pid"
sleep 3

if kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "  ✅ 前端已启动 PID=$FRONTEND_PID"
else
    echo -e "${YELLOW}  ⚠️  前端启动检查未通过，查看: cat $SCRIPT_DIR/frontend.log${NC}"
fi

# ===== 完成 =====
SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}  启动完成!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "  前端:       ${GREEN}http://${SERVER_IP}:5173${NC}"
echo -e "  后端 API:   ${GREEN}http://${SERVER_IP}:5002${NC}"
echo -e "  API 文档:   ${GREEN}http://${SERVER_IP}:5002/docs${NC}"
echo ""
echo -e "${YELLOW}管理命令:${NC}"
echo -e "  查看后端日志:  tail -f $SCRIPT_DIR/backend.log"
echo -e "  查看前端日志:  tail -f $SCRIPT_DIR/frontend.log"
echo -e "  停止后端:      kill \$(cat $SCRIPT_DIR/backend.pid)"
echo -e "  停止前端:      kill \$(cat $SCRIPT_DIR/frontend.pid)"
echo ""
