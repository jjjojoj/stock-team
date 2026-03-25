# Phase 7: 面板清理、README 更新与仓库瘦身

日期：2026-03-25

## 这轮目标

1. 把监控面板刷干净
2. 更新 GitHub README
3. 记录本轮收尾动作
4. 删除明显多余或不相关的仓库杂项文件

## 面板处理

文件：

- `web/enhanced_cron_handler.py`
- `tests/test_enhanced_cron_handler.py`

改动：

- 如果任务已经切换到 `delivery.mode = none`
- 且任务配置更新时间晚于上次运行时间
- 则旧的 `error` 状态视为历史残留，不再当成当前故障

面板表现：

- 历史旧状态显示为 `ok / history_cleared`
- 正在执行的任务显示为 `running`

本地验证结果：

- `warning_count = 0`
- `error_count = 0`

## README 更新

文件：

- `README.md`
- `README_v3.md`

更新内容：

- 改成与当前主线一致的说明
- 删除 v2 时代遗留脚本和旧 cron 说明
- 明确 OpenClaw cron 是唯一控制面
- 明确脚本自发 webhook 的通知机制
- 更新主要工作流、关键脚本、看板入口、测试命令

## 仓库清理

本轮清理原则：

- 删除明显的缓存、编译产物、桌面垃圾文件
- 删除重复/临时脚本
- 删除临时报告目录
- 不删除核心业务代码、数据库、学习资产和实盘配置

新增忽略规则：

- `.gitignore`

忽略项包括：

- `.DS_Store`
- `__pycache__/`
- `*.pyc`
- `logs/dashboard_v3.log`
- `reports/`
- `outputs/reports/`
- 若干运行时日报/搜索/复盘输出

## 备注

这轮清理主要是“让仓库状态更像产品仓库，而不是运行目录快照”。
