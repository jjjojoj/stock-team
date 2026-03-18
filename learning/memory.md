# AI 炒股团队 - 长期记忆（HOT 层）

> 出现 3 次相同模式 → 提升到 HOT 层，永久生效

---

## [2026-03-18] 收盘深度学习 ⭐

**时间**: 2026-03-18 15:31

**预测验证结果**:
- 验证: 13 个
- ✅ 正确: 11 (84.6%)
- 🔶 部分: 1
- ❌ 错误: 1
- 🔗 关联交易: 0 个

**规则准确率分析**:
- 表现最好的规则: break_ma20 (45.5%), dir_industry_cycle_high (40.9%)
- 表现最差的规则: industry_cycle_low, cycle_bottom_fishing, industry_cycle_up, positive_news (均为 0.0%)
- 需要重点关注: RSI超卖策略(rsi_oversold)只有33.3%准确率，样本量小但表现不佳

**关键教训**:
1. MA20突破策略(break_ma20)仍然是最可靠的信号之一
2. 行业周期高位方向性判断(dir_industry_cycle_high)有较好表现
3. 行业周期低位策略(industry_cycle_low)和底部钓鱼策略(cycle_bottom_fishing)完全失效，需要重新评估或移除
4. 正面新闻策略(positive_news)在当前市场环境下无效
5. 整体预测准确率提升至84.6%，但累计准确率仍为35.1%，说明近期模型有显著改进

**行动建议**:
- 增加break_ma20和dir_industry_cycle_high策略的权重
- 暂停使用industry_cycle_low、cycle_bottom_fishing、industry_cycle_up和positive_news策略
- 对rsi_oversold策略进行参数优化或条件限制