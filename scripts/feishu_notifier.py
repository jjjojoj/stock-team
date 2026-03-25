#!/usr/bin/env python3
"""
飞书通知集成

统一约束：
1. 股票 cron 任务统一走 webhook
2. 卡片优先，超长时自动裁剪
3. 卡片失败时回退到文本消息，避免整条任务因为消息格式失败
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 飞书官方内容平台提到自定义机器人消息体 JSON 建议不超过 30 KB。
# 这里保守一些，避免卡片超长触发 webhook 拒绝。
SAFE_JSON_BYTES = 28_000
CARD_BLOCK_CHARS = 900
CARD_MAX_BLOCKS = 10
TITLE_MAX_CHARS = 60


def _feishu_config_paths() -> List[Path]:
    """Return tracked defaults first, then ignored local overrides."""
    config_dir = PROJECT_ROOT / "config"
    return [
        config_dir / "feishu_config.json",
        config_dir / "feishu_config.local.json",
    ]


def load_feishu_config() -> Dict:
    """加载飞书配置，允许本地私有文件覆盖仓库模板。"""
    config: Dict = {}
    for config_file in _feishu_config_paths():
        if not config_file.exists():
            continue
        with config_file.open("r", encoding="utf-8") as handle:
            config.update(json.load(handle))
    return config


def get_default_webhook_url() -> Optional[str]:
    """读取默认 webhook。环境变量优先于本地配置。"""
    env_webhook = os.getenv("FEISHU_WEBHOOK_URL") or os.getenv("STOCK_TEAM_FEISHU_WEBHOOK_URL")
    if env_webhook:
        return env_webhook.strip()

    config = load_feishu_config()
    return config.get("webhook_url") or config.get("webhook")


def _normalize_text(content: object) -> str:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or "（空消息）"


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return "…"
    return text[: max_chars - 1].rstrip() + "…"


def _split_markdown_blocks(content: str) -> List[str]:
    """按段落/行切块，兼顾可读性和卡片长度。"""
    paragraphs = [part.strip() for part in _normalize_text(content).split("\n\n") if part.strip()]
    if not paragraphs:
        return ["（空消息）"]

    blocks: List[str] = []
    for paragraph in paragraphs:
        lines = paragraph.splitlines() or [paragraph]
        current = ""
        for line in lines:
            candidate = line if not current else f"{current}\n{line}"
            if len(candidate) <= CARD_BLOCK_CHARS:
                current = candidate
                continue

            if current:
                blocks.append(current)
                current = ""

            remainder = line
            while len(remainder) > CARD_BLOCK_CHARS:
                blocks.append(_truncate_text(remainder[:CARD_BLOCK_CHARS], CARD_BLOCK_CHARS))
                remainder = remainder[CARD_BLOCK_CHARS:]
            current = remainder

        if current:
            blocks.append(current)

    if len(blocks) > CARD_MAX_BLOCKS:
        kept = blocks[: CARD_MAX_BLOCKS - 1]
        kept.append(f"内容较长，已截断其余 {len(blocks) - len(kept)} 段。")
        blocks = kept

    return blocks


def _card_template(level: str) -> str:
    colors = {
        "info": "blue",
        "success": "green",
        "warning": "yellow",
        "high": "orange",
        "critical": "red",
        "medium": "yellow",
    }
    return colors.get(level, "blue")


def _build_card_payload(title: str, content: str, level: str) -> Dict:
    blocks = _split_markdown_blocks(content)
    footer = f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | stock-team webhook"

    while True:
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": block,
                },
            }
            for block in blocks
        ]
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": footer,
                    }
                ],
            }
        )

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": _truncate_text(_normalize_text(title), TITLE_MAX_CHARS),
                    },
                    "template": _card_template(level),
                },
                "elements": elements,
            },
        }

        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= SAFE_JSON_BYTES:
            return payload

        if len(blocks) > 1:
            blocks = blocks[:-1]
            if not blocks[-1].endswith("内容已自动截断。"):
                blocks[-1] = f"{_truncate_text(blocks[-1], CARD_BLOCK_CHARS - 12)}\n\n内容已自动截断。"
            continue

        blocks = [_truncate_text(blocks[0], max(CARD_BLOCK_CHARS // 2, 200))]


def _build_text_payload(title: str, content: str) -> Dict:
    footer = f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    text = f"{_normalize_text(title)}\n\n{_normalize_text(content)}\n\n{footer}"

    payload = {
        "msg_type": "text",
        "content": {
            "text": text,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    while len(encoded) > SAFE_JSON_BYTES:
        text = _truncate_text(text, max(len(text) - 500, 300))
        payload["content"]["text"] = text
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    return payload


def _post_webhook(payload: Dict, webhook_url: str) -> Tuple[bool, Dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode("utf-8")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"raw": raw}

    success = result.get("StatusCode") == 0 or result.get("code") == 0
    return success, result


def send_feishu_message(title, content, level="info", webhook_url=None):
    """发送飞书消息。默认卡片，失败时回退文本。"""
    webhook = webhook_url or get_default_webhook_url()
    if not webhook:
        print("⚠️ 飞书 webhook 未配置")
        return False

    card_payload = _build_card_payload(title, content, level)

    try:
        success, result = _post_webhook(card_payload, webhook)
        if success:
            print(f"✅ 飞书卡片发送成功: {title}")
            return True

        print(f"⚠️ 飞书卡片发送失败，准备回退文本: {result}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"⚠️ 飞书卡片 HTTPError，准备回退文本: {exc.code} {detail}")
    except Exception as exc:
        print(f"⚠️ 飞书卡片发送异常，准备回退文本: {exc}")

    try:
        text_payload = _build_text_payload(title, content)
        success, result = _post_webhook(text_payload, webhook)
        if success:
            print(f"✅ 飞书文本回退发送成功: {title}")
            return True

        print(f"❌ 飞书文本回退仍失败: {result}")
        return False
    except Exception as exc:
        print(f"❌ 发送飞书消息失败: {exc}")
        return False


def send_daily_report(portfolio, alerts):
    """发送每日报告。"""
    config = load_feishu_config()

    if not config.get("daily_report_enabled", True):
        return

    lines = [
        "📊 每日投资报告",
        "",
        "💰 资金状况",
        f"总资产: ¥{portfolio['total_capital']:,.0f}",
        f"持仓市值: ¥{portfolio['total_value']:,.2f}",
        f"总盈亏: ¥{portfolio['total_profit']:,.2f} ({portfolio['total_profit_pct']:+.2f}%)",
        "",
        "📈 持仓详情",
    ]

    for detail in portfolio.get("details", []):
        profit_icon = "🟢" if detail["profit"] >= 0 else "🔴"
        lines.append(f"{profit_icon} {detail['name']}: {detail['profit_pct']:+.2f}%")

    if alerts:
        lines.append("")
        lines.append(f"⚠️ 预警 ({len(alerts)}条)")
        for alert in alerts[:5]:
            lines.append(f"• {alert['message']}")

    send_feishu_message(
        title="📈 每日投资报告",
        content="\n".join(lines),
        level="info",
    )


def send_trade_notification(action, code, name, shares, price, profit=None):
    """发送交易通知。"""
    if action == "BUY":
        content = (
            f"买入 {name} ({code})\n"
            f"数量: {shares}股\n"
            f"价格: ¥{price:.2f}\n"
            f"金额: ¥{shares * price:,.2f}"
        )
        level = "info"
    else:
        profit_text = f"\n盈亏: ¥{profit:,.2f}" if profit is not None else ""
        content = (
            f"卖出 {name} ({code})\n"
            f"数量: {shares}股\n"
            f"价格: ¥{price:.2f}{profit_text}"
        )
        level = "success" if profit is None or profit >= 0 else "warning"

    send_feishu_message(
        title=f"{'🛒' if action == 'BUY' else '💰'} 交易通知",
        content=content,
        level=level,
    )


def send_alert_notification(alert):
    """发送预警通知。"""
    send_feishu_message(
        title=f"⚠️ 股票预警 - {alert['name']}",
        content=alert["message"],
        level=alert["level"],
    )


def load_positions():
    """加载持仓数据。"""
    positions_file = PROJECT_ROOT / "config" / "positions.json"
    if positions_file.exists():
        with positions_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def load_portfolio():
    """加载资金数据。"""
    portfolio_file = PROJECT_ROOT / "config" / "portfolio.json"
    if portfolio_file.exists():
        with portfolio_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def get_realtime_price(code: str) -> Optional[float]:
    """获取实时价格（简化版）。"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from adapters import get_data_manager

        manager = get_data_manager()
        price = manager.get_realtime_price(code)
        if price:
            return float(price.price)
    except Exception:
        pass
    return None


def generate_portfolio_report(report_type: str) -> Dict:
    """生成持仓汇报。"""
    positions = load_positions()
    portfolio = load_portfolio()

    total_capital = portfolio.get("total_capital", 200000)
    available_cash = portfolio.get("available_cash", total_capital)

    position_details = []
    total_value = 0.0
    total_profit = 0.0

    for code, pos in positions.items():
        current_price = get_realtime_price(code)
        cost_price = pos.get("cost_price", 0)
        shares = pos.get("shares", 0)

        if current_price:
            market_value = shares * current_price
            profit = shares * (current_price - cost_price)
            profit_pct = (current_price / cost_price - 1) * 100 if cost_price > 0 else 0
        else:
            market_value = shares * cost_price
            profit = 0
            profit_pct = 0

        total_value += market_value
        total_profit += profit

        position_details.append(
            {
                "name": pos.get("name", code),
                "code": code,
                "shares": shares,
                "cost_price": cost_price,
                "current_price": current_price,
                "market_value": market_value,
                "profit": profit,
                "profit_pct": profit_pct,
            }
        )

    total_assets = available_cash + total_value
    total_profit_pct = (total_profit / total_value * 100) if total_value > 0 else 0

    return {
        "total_capital": total_capital,
        "available_cash": available_cash,
        "total_value": total_value,
        "total_profit": total_profit,
        "total_profit_pct": total_profit_pct,
        "total_assets": total_assets,
        "positions": position_details,
    }


def format_report(report_type: str, portfolio: Dict) -> Tuple[str, str, str]:
    """格式化持仓报告。"""
    time_str = datetime.now().strftime("%H:%M")
    type_config = {
        "morning": ("🌅 早盘持仓汇报", "早盘"),
        "noon_close": ("🕛 午盘收盘汇报", "午盘收盘"),
        "noon_open": ("🕐 午盘开盘汇报", "午盘开盘"),
        "close": ("🌙 收盘汇总汇报", "收盘汇总"),
    }

    title, _ = type_config.get(report_type, ("📊 持仓汇报", "持仓"))

    lines = [
        f"📅 时间: {datetime.now().strftime('%Y-%m-%d')} {time_str}",
        "",
        "💰 资金状况",
        f"总资产: ¥{portfolio['total_assets']:,.2f}",
        f"可用现金: ¥{portfolio['available_cash']:,.2f}",
        f"持仓市值: ¥{portfolio['total_value']:,.2f}",
        f"总盈亏: ¥{portfolio['total_profit']:,.2f} ({portfolio['total_profit_pct']:+.2f}%)",
        "",
        f"📈 持仓详情 ({len(portfolio['positions'])}只)",
    ]

    for pos in portfolio["positions"]:
        emoji = "🟢" if pos["profit"] >= 0 else "🔴"
        current_price = pos["current_price"] if pos["current_price"] is not None else pos["cost_price"]
        lines.append(f"{emoji} {pos['name']} ({pos['code']})")
        lines.append(
            f"持仓: {pos['shares']}股 | 成本: ¥{pos['cost_price']:.2f} → 现价: ¥{current_price:.2f}"
        )
        lines.append(
            f"市值: ¥{pos['market_value']:,.2f} | 盈亏: ¥{pos['profit']:,.2f} ({pos['profit_pct']:+.2f}%)"
        )
        lines.append("")

    content = "\n".join(lines).strip()
    level = "success" if portfolio["total_profit"] >= 0 else "warning"
    return title, content, level


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="飞书通知集成")
    parser.add_argument(
        "--report",
        choices=["morning", "noon_close", "noon_open", "close"],
        help="生成持仓汇报",
    )
    parser.add_argument("--test", action="store_true", help="发送测试消息")

    args = parser.parse_args()

    if args.report:
        portfolio_data = generate_portfolio_report(args.report)
        title, content, level = format_report(args.report, portfolio_data)
        send_feishu_message(title=title, content=content, level=level)
    elif args.test:
        send_feishu_message(
            title="🧪 测试消息",
            content="这是一条测试卡片，用于验证飞书 webhook 与卡片发送链路。",
            level="info",
        )
    else:
        print("用法:")
        print("  python feishu_notifier.py --report morning      早盘持仓汇报")
        print("  python feishu_notifier.py --report noon_close   午盘收盘汇报")
        print("  python feishu_notifier.py --report noon_open    午盘开盘汇报")
        print("  python feishu_notifier.py --report close        收盘汇总汇报")
        print("  python feishu_notifier.py --test                发送测试消息")
