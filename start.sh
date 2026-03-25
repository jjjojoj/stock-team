#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_SCRIPT="$PROJECT_ROOT/scripts/bootstrap_openclaw.sh"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"

print_header() {
    echo "============================================================"
    echo "China Stock Team"
    echo "OpenClaw-ready local launcher"
    echo "============================================================"
    echo
}

ensure_python() {
    if [ ! -x "$VENV_PYTHON" ]; then
        echo "本地虚拟环境尚未准备好。"
        echo "建议先运行：bash scripts/bootstrap_openclaw.sh"
        return 1
    fi
    return 0
}

show_menu() {
    echo "请选择操作："
    echo
    echo "  1) 初始化本地环境"
    echo "  2) 启动监控面板 (8082)"
    echo "  3) 动态选股"
    echo "  4) 生成早盘预测"
    echo "  5) 规则验证报告"
    echo "  6) 飞书测试消息"
    echo "  7) 查看 OpenClaw cron 状态"
    echo "  8) 查看 OpenClaw 一句话部署说明"
    echo
    echo "  0) 退出"
    echo
    read -r -p "请输入选项: " choice
}

show_deploy_prompt() {
    sed -n '1,220p' "$PROJECT_ROOT/OPENCLAW_DEPLOY.md"
}

while true; do
    print_header
    show_menu

    case "$choice" in
        1)
            bash "$BOOTSTRAP_SCRIPT"
            ;;
        2)
            ensure_python || continue
            "$VENV_PYTHON" "$PROJECT_ROOT/web/dashboard_v3.py"
            ;;
        3)
            ensure_python || continue
            "$VENV_PYTHON" "$PROJECT_ROOT/scripts/selector.py" top 5
            ;;
        4)
            ensure_python || continue
            "$VENV_PYTHON" "$PROJECT_ROOT/scripts/ai_predictor.py" generate
            ;;
        5)
            ensure_python || continue
            "$VENV_PYTHON" "$PROJECT_ROOT/scripts/rule_validator.py" report
            ;;
        6)
            ensure_python || continue
            "$VENV_PYTHON" "$PROJECT_ROOT/scripts/feishu_notifier.py" --test
            ;;
        7)
            if command -v openclaw >/dev/null 2>&1; then
                openclaw cron list --json
            else
                echo "当前环境未找到 openclaw 命令。"
            fi
            ;;
        8)
            show_deploy_prompt
            ;;
        0)
            exit 0
            ;;
        *)
            echo "无效选项。"
            ;;
    esac

    echo
    read -r -p "按回车继续..." _
done
