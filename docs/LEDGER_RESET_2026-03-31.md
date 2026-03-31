# 模拟账本重置记录

日期：2026-03-31

## 背景

股票团队的历史资金记录出现了明显断层：

- `config/portfolio.json` 中的现金值与 Dashboard / 飞书通知不一致
- `account`、`trades`、`positions`、`simulated_orders`、`simulated_fills` 之间缺少完整可审计链
- 旧账无法可靠解释“20 万如何变成其他数值”

因此，自 `2026-03-31` 起，模拟交易账本按新的基线重新开始。

## 新基线

- 基线日期：`2026-03-31`
- 初始资金：`¥200,000`
- 当前持仓：`0`
- 当前现金：`¥200,000`
- 总收益：`0`

## 处理方式

- 旧账本运行态数据已在本地归档到 `data/ledger_archives/`
- 实时账本已重置为新的 `account` 快照
- `trades`、`simulated_orders`、`simulated_fills`、`positions` 的实时数据已清空
- `data/trade_history.json` 已清空
- `config/portfolio.json` 已改为新的模拟基线配置

## 约定

从本次重置开始：

- 资产展示以实时账本为准
- `portfolio.json` 仅保留基线配置与当前摘要，不再作为可随意篡改的收益来源
- 若未来再次需要重置，可运行：

```bash
python3 scripts/reset_ledger.py --capital 200000
```
