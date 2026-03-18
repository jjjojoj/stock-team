#!/bin/bash
# 全自动股票交易系统 - 启动脚本

set -e

PROJECT_ROOT="$HOME/.openclaw/workspace/china-stock-team"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"

echo "======================================================================"
echo "🚀 全自动股票交易系统"
echo "======================================================================"
echo ""

# 检查虚拟环境
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ 虚拟环境不存在，请先运行："
    echo "   cd $PROJECT_ROOT"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install baostock pandas"
    exit 1
fi

# 功能菜单
show_menu() {
    echo "请选择功能："
    echo ""
    echo "  1) 📊 综合仪表盘（查看所有关键信息）"
    echo "  2) 🔍 股票筛选（基本面+技术面）"
    echo "  3) 📈 商品价格跟踪（铜/铝/锂/稀土）"
    echo "  4) ⚠️  风险评估（多维度风险）"
    echo "  5) 📰 新闻监控（事件影响分析）"
    echo "  6) 👀 实时盯盘（持仓+自选股）"
    echo "  7) 📝 生成研究报告（个股深度分析）"
    echo "  8) 🧠 学习引擎（查看规则/复盘）"
    echo "  9) 🤖 启动全自动系统（后台运行）"
    echo "  10) 📅 每日扫描（手动触发）"
    echo ""
    echo "  0) 退出"
    echo ""
    read -p "请输入选项: " choice
}

# 主循环
while true; do
    show_menu
    
    case $choice in
        1)
            echo ""
            echo "📊 启动综合仪表盘..."
            $VENV_PYTHON "$PROJECT_ROOT/scripts/dashboard.py"
            ;;
        2)
            echo ""
            echo "🔍 启动股票筛选..."
            $VENV_PYTHON "$PROJECT_ROOT/scripts/selector_v3.py" top 5
            ;;
        3)
            echo ""
            echo "📈 查看商品价格..."
            $VENV_PYTHON "$PROJECT_ROOT/scripts/commodity_tracker.py" prices
            ;;
        4)
            echo ""
            echo "⚠️  生成风险评估..."
            $VENV_PYTHON "$PROJECT_ROOT/scripts/risk_assessment.py" report
            ;;
        5)
            echo ""
            echo "📰 测试新闻监控..."
            $VENV_PYTHON "$PROJECT_ROOT/scripts/news_monitor.py" test
            ;;
        6)
            echo ""
            echo "👀 启动实时盯盘..."
            $VENV_PYTHON "$PROJECT_ROOT/scripts/realtime_monitor.py" all
            ;;
        7)
            echo ""
            read -p "请输入股票代码（如 sh.600459）: " code
            echo "📝 生成研究报告..."
            $VENV_PYTHON "$PROJECT_ROOT/scripts/research_generator.py" "$code"
            ;;
        8)
            echo ""
            echo "🧠 学习引擎..."
            echo "  1) 查看激活规则"
            echo "  2) 每周复盘"
            echo "  3) 测试成功案例"
            echo "  4) 测试失败案例"
            read -p "请选择: " learn_choice
            
            case $learn_choice in
                1) $VENV_PYTHON "$PROJECT_ROOT/scripts/learning_engine.py" rules ;;
                2) $VENV_PYTHON "$PROJECT_ROOT/scripts/learning_engine.py" review ;;
                3) $VENV_PYTHON "$PROJECT_ROOT/scripts/learning_engine.py" test_success ;;
                4) $VENV_PYTHON "$PROJECT_ROOT/scripts/learning_engine.py" test_failure ;;
                *) echo "无效选项" ;;
            esac
            ;;
        9)
            echo ""
            echo "🤖 启动全自动系统..."
            echo "⚠️  注意：系统将在后台运行"
            echo "   日志文件：$PROJECT_ROOT/logs/"
            echo ""
            read -p "确认启动？(y/n): " confirm
            
            if [ "$confirm" = "y" ]; then
                nohup $VENV_PYTHON "$PROJECT_ROOT/scripts/auto_trader.py" start > "$PROJECT_ROOT/logs/auto_trader.log" 2>&1 &
                echo "✅ 系统已启动，PID: $!"
                echo "   查看日志：tail -f $PROJECT_ROOT/logs/auto_trader.log"
            fi
            ;;
        10)
            echo ""
            echo "📅 运行每日扫描..."
            $VENV_PYTHON "$PROJECT_ROOT/scripts/daily_scan.py" test
            ;;
        0)
            echo ""
            echo "👋 再见！"
            exit 0
            ;;
        *)
            echo ""
            echo "❌ 无效选项，请重新选择"
            ;;
    esac
    
    echo ""
    read -p "按回车继续..."
    echo ""
done
