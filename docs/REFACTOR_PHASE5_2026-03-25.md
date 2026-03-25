# Phase 5 监控与新闻流修复记录（2026-03-25）

## 本轮问题

用户反馈两类问题：

1. 监控面板里的“实时新闻流”方向和力度看起来不对。
2. Cron 面板里多项任务显示为红色失败：
   - 早上AI预测生成
   - 午盘反思
   - 选股层 - 动态标准选股
   - 每日预测复盘
   - 规则验证（每日）
   - 每日炒股书籍学习

---

## 根因排查结果

### 1. 实时新闻流问题

发现有三层原因：

- `news_labels` 里混入了低质量样本：
  - 无时间
  - 无来源
  - 置信度低
  - 标题模板化（如“公司发布重大利好消息”）
- 面板之前直接按 `news_labels` 原始结果倒序展示，没有做质量过滤、方向归一和力度归一。
- `news_labels` 的结构化新闻本身比较旧，最新高质量记录主要停在 `2026-03-13` 到 `2026-03-16`；而最近的联网搜索结果实际保存在 `data/daily_search/*.json`，没有被面板当作回退源使用。

### 2. Cron 失败问题

排查 `openclaw cron list --json` 后发现：

- 面板里部分“红色失败”任务的真实 `lastError` 是 `Message failed`
- 这类任务并不一定是脚本执行失败，更常见的是：
  - 脚本已执行
  - 最后通知/投递阶段失败

也就是说，之前面板把“脚本失败”和“消息发送失败”混成了同一个红色 `error`。

### 3. 真正的脚本级问题

手动执行后确认：

- `midday_review.py`：可正常执行
- `daily_review_closed_loop.py report`：可正常执行
- `rule_validator.py validate`：可正常执行
- `daily_book_learning.py`：可正常执行

真正存在脚本级故障的是：

- `ai_predictor.py brief`
  - 根因：`data/news_cache.json` 是空文件，`json.load()` 直接报错
- `selector.py top 5`
  - 根因：当前运行环境 `python3 = 3.13`
  - 代码却硬编码导入 `venv/lib/python3.14/site-packages`
  - 导致 `numpy/pandas` 二进制扩展版本不匹配，脚本直接崩溃

---

## 代码修复

### 1. `scripts/news_trigger.py`

- 为新闻缓存增加默认结构
- 空文件或损坏 JSON 时自动重置
- 不再因为 `news_cache.json` 空内容把 `ai_predictor.py` 卡死

### 2. `scripts/news_fetcher.py`

- 补上缺失的 `json` 导入
- 读取空缓存时安全回退

### 3. `scripts/ai_predictor.py`

- 不再写死 `python3.14/site-packages`
- 改为按当前 Python 版本动态选择虚拟环境 site-packages
- 在当前 `python3.13` 环境下会优雅降级，而不是尝试加载不兼容的 `3.14` 包

### 4. `scripts/selector.py`

- 不再强依赖多数据源适配器成功初始化
- 当 `baostock/pandas/numpy` 环境不可用时，自动降级为轻量模式
- 轻量模式下使用腾讯行情接口获取实时价格，并继续结合本地基本面数据完成选股

### 5. `web/enhanced_cron_handler.py`

- 新增 `derive_display_status()`
- 当 OpenClaw 返回 `Message failed` 时：
  - 原始状态仍保留为 `error`
  - 面板展示状态改为 `warning`
  - 文案改为“脚本可能已执行，通知发送失败”

### 6. `web/dashboard_v3.py`

- 新增新闻质量过滤逻辑
- 新增方向/力度归一字段：
  - `direction_label`
  - `direction_icon`
  - `strength_label`
- 新增 `daily_search` 回退新闻源
- 新闻流现在优先显示：
  1. 高质量结构化新闻
  2. 最近 `daily_search` 联网搜索热点
- 最终按“时间新鲜度 + 紧急度 + 影响分数”排序
- Cron 卡片支持展示 `status_detail`

### 7. 测试

- 更新 [tests/test_dashboard_v3.py](/Users/joe/.openclaw/workspace/china-stock-team/tests/test_dashboard_v3.py)
- 新增 [tests/test_enhanced_cron_handler.py](/Users/joe/.openclaw/workspace/china-stock-team/tests/test_enhanced_cron_handler.py)

---

## 验证结果

### 脚本验证

- `python3 scripts/ai_predictor.py brief`：已恢复，可正常运行
- `python3 scripts/selector.py top 5`：已恢复，可在轻量模式下正常运行
- `python3 scripts/midday_review.py`：正常
- `python3 scripts/daily_review_closed_loop.py report`：正常
- `python3 scripts/rule_validator.py validate`：正常
- `python3 scripts/daily_book_learning.py`：正常
- `python3 scripts/daily_web_search.py`：已补跑，生成 `data/daily_search/20260325.json`

### 测试验证

```bash
python3 -m unittest tests.test_dashboard_v3 tests.test_enhanced_cron_handler tests.test_prediction_utils tests.test_storage_sync tests.test_rule_storage
```

结果：`Ran 12 tests ... OK`

### 面板验证

- `http://127.0.0.1:8082/api/openclaw_cron`
  - “午盘反思 / 动态选股 / 每日预测复盘 / 规则验证 / 每日书籍学习” 已显示为 `warning`
  - “早上AI预测生成” 当前为 `ok`
- `http://127.0.0.1:8082/api/news-summary`
  - 已能返回 `2026-03-25` 的搜索热点新闻
  - 方向和力度字段已可用

---

## 结论

本轮之后：

- 面板里的红色失败不再混淆“脚本失败”和“通知失败”
- `ai_predictor.py` 与 `selector.py` 的真实脚本级故障已修掉
- 新闻流不再被低质量旧样本主导，并且能回退展示最近联网搜索结果

仍然存在的现实约束：

- `news_labels` 的结构化新闻写入链路仍偏弱，真正长期方案还是把 `daily_web_search` 或新闻采集结果更稳定地接入结构化标签表，而不只靠 dashboard 回退逻辑兜底
