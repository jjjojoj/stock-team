#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$PROJECT_ROOT/venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
REQ_FILE="$PROJECT_ROOT/requirements-openclaw.txt"

RUN_INSTALL=1
RUN_TESTS=1
START_DASHBOARD=0

usage() {
    cat <<'EOF'
用法:
  bash scripts/bootstrap_openclaw.sh [--skip-install] [--skip-tests] [--start-dashboard]

说明:
  --skip-install     跳过依赖安装
  --skip-tests       跳过单元测试
  --start-dashboard  初始化完成后后台启动 8082 面板
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-install)
            RUN_INSTALL=0
            ;;
        --skip-tests)
            RUN_TESTS=0
            ;;
        --start-dashboard)
            START_DASHBOARD=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

echo "==> Project root: $PROJECT_ROOT"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "==> 创建虚拟环境"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "==> 升级 pip"
"$VENV_PYTHON" -m pip install --upgrade pip

if [[ $RUN_INSTALL -eq 1 ]]; then
    echo "==> 安装依赖"
    "$VENV_PYTHON" -m pip install -r "$REQ_FILE"
fi

echo "==> 准备运行目录"
mkdir -p \
    "$PROJECT_ROOT/data/daily_search" \
    "$PROJECT_ROOT/data/reviews" \
    "$PROJECT_ROOT/logs" \
    "$PROJECT_ROOT/outputs/reports"

if [[ ! -f "$PROJECT_ROOT/config/feishu_config.local.json" && -f "$PROJECT_ROOT/config/feishu_config.local.example.json" ]]; then
    echo "==> 生成本地飞书配置模板"
    cp "$PROJECT_ROOT/config/feishu_config.local.example.json" "$PROJECT_ROOT/config/feishu_config.local.json"
fi

echo "==> 初始化数据库结构"
cd "$PROJECT_ROOT"
"$VENV_PYTHON" - <<'PY'
from core.storage import ensure_storage_tables
ensure_storage_tables()
print("storage tables ready")
PY

if [[ $RUN_TESTS -eq 1 ]]; then
    echo "==> 运行基础 smoke tests"
    "$VENV_PYTHON" -m unittest \
        tests.test_feishu_notifier \
        tests.test_enhanced_cron_handler \
        tests.test_dashboard_v3
fi

if [[ $START_DASHBOARD -eq 1 ]]; then
    echo "==> 后台启动 dashboard_v3"
    nohup "$VENV_PYTHON" "$PROJECT_ROOT/web/dashboard_v3.py" > "$PROJECT_ROOT/logs/dashboard_v3.log" 2>&1 &
    echo "dashboard started: http://127.0.0.1:8082"
fi

echo
echo "初始化完成。建议下一步："
echo "  1. 如需飞书通知，配置 FEISHU_WEBHOOK_URL 或 config/feishu_config.local.json"
echo "  2. 如需联网搜索，确认本地 API key 配置可用"
echo "  3. 启动面板: $VENV_PYTHON web/dashboard_v3.py"
echo "  4. 查看 OpenClaw 任务: openclaw cron list --json"
