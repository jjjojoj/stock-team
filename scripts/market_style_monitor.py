#!/usr/bin/env python3
"""
市场风格监控系统

功能：
1. 计算风格指数（价值/成长、大盘/小盘、周期/防御）
2. 识别当前市场风格
3. 风格切换检测
4. 通知和记录

风格定义：
| 风格 | 代表指数 | 特征 |
|------|---------|------|
| 价值 | 上证价值指数 | 低 PE、高股息 |
| 成长 | 创业板指 | 高增长、高估值 |
| 大盘 | 沪深 300 | 市值>500 亿 |
| 小盘 | 中证 1000 | 市值<200 亿 |
"""

import sys
import os
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

# 配置
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# 确保目录存在
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'market_style.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MarketStyleMonitor:
    """市场风格监控器"""
    
    # 风格指数代码（腾讯 API 格式）
    STYLE_INDICES = {
        "value": {"code": "sh000029", "name": "上证价值"},  # 价值
        "growth": {"code": "sz399006", "name": "创业板指"},  # 成长
        "large": {"code": "sh000300", "name": "沪深300"},  # 大盘
        "small": {"code": "sh000852", "name": "中证1000"},  # 小盘
        "cyclical": {"code": "sh000037", "name": "上证周期"},  # 周期
        "defensive": {"code": "sh000021", "name": "上证消费"},  # 防御
    }
    
    # 风格切换阈值
    SWITCH_THRESHOLD = 0.03  # 3% 变化
    SWITCH_DAYS = 5  # 连续 5 日
    
    def __init__(self):
        self.config = self._load_config()
        self.history = self._load_history()
    
    def _load_config(self) -> Dict:
        """加载配置"""
        config_file = os.path.join(CONFIG_DIR, "market_style.json")
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"enabled": True}
    
    def _load_history(self) -> Dict:
        """加载历史数据"""
        history_file = os.path.join(DATA_DIR, "market_style_history.json")
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return {
            "daily_ratios": [],
            "last_switch": None,
            "current_style": None,
        }
    
    def _save_history(self):
        """保存历史数据"""
        history_file = os.path.join(DATA_DIR, "market_style_history.json")
        # 只保留最近 90 天
        self.history["daily_ratios"] = self.history["daily_ratios"][-90:]
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
    
    def get_index_data(self, style_name: str) -> Optional[Dict]:
        """
        获取指数数据（使用腾讯 API + urllib）

        Args:
            style_name: 风格名称（如 value, growth）

        Returns:
            指数数据或 None
        """
        try:
            info = self.STYLE_INDICES.get(style_name)
            if not info:
                return None

            code = info["code"]
            url = f"http://qt.gtimg.cn/q={code}"

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                text = response.read().decode('gbk')

                # 解析格式：v_sh000300="1~沪深300~000300~4660.44~..."
                if '~' in text:
                    # 提取引号内的内容
                    start = text.find('"') + 1
                    end = text.rfind('"')
                    if start > 0 and end > start:
                        content = text[start:end]
                        parts = content.split('~')

                        if len(parts) >= 7:
                            try:
                                price = float(parts[3]) if parts[3] else 0
                                prev_close = float(parts[4]) if parts[4] else 0
                                change_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0

                                return {
                                    "code": code,
                                    "name": parts[1],
                                    "price": price,
                                    "change_pct": change_pct,
                                    "volume": float(parts[6]) if parts[6] else 0,
                                }
                            except (ValueError, TypeError):
                                logger.warning(f"解析指数数据失败：{style_name} - 数据格式异常")
                                return None
            return None
        except Exception as e:
            logger.error(f"获取指数数据失败：{style_name} - {e}")
            return None
    
    def calculate_style_ratios(self) -> Dict:
        """
        计算风格比率
        
        Returns:
            风格比率字典
        """
        ratios = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "value_growth": None,
            "large_small": None,
            "cyclical_defensive": None,
        }
        
        # 获取各指数数据
        indices = {}
        for style in self.STYLE_INDICES.keys():
            data = self.get_index_data(style)
            if data:
                indices[style] = data
        
        # 计算比率
        if "value" in indices and "growth" in indices:
            ratios["value_growth"] = indices["value"]["price"] / indices["growth"]["price"]
        
        if "large" in indices and "small" in indices:
            ratios["large_small"] = indices["large"]["price"] / indices["small"]["price"]
        
        if "cyclical" in indices and "defensive" in indices:
            ratios["cyclical_defensive"] = indices["cyclical"]["price"] / indices["defensive"]["price"]
        
        # 保存历史
        if any(ratios.values()):
            self.history["daily_ratios"].append(ratios)
            self._save_history()
        
        return ratios
    
    def identify_current_style(self) -> Dict:
        """
        识别当前市场风格
        
        Returns:
            当前市场风格
        """
        ratios = self.calculate_style_ratios()
        
        style = {
            "date": ratios["date"],
            "dimensions": {},
            "dominant_style": None,
        }
        
        # 价值 vs 成长
        if ratios["value_growth"]:
            if ratios["value_growth"] > 1.1:
                style["dimensions"]["value_growth"] = "value"
            elif ratios["value_growth"] < 0.9:
                style["dimensions"]["value_growth"] = "growth"
            else:
                style["dimensions"]["value_growth"] = "balanced"
        
        # 大盘 vs 小盘
        if ratios["large_small"]:
            if ratios["large_small"] > 1.1:
                style["dimensions"]["large_small"] = "large"
            elif ratios["large_small"] < 0.9:
                style["dimensions"]["large_small"] = "small"
            else:
                style["dimensions"]["large_small"] = "balanced"
        
        # 周期 vs 防御
        if ratios["cyclical_defensive"]:
            if ratios["cyclical_defensive"] > 1.1:
                style["dimensions"]["cyclical_defensive"] = "cyclical"
            elif ratios["cyclical_defensive"] < 0.9:
                style["dimensions"]["cyclical_defensive"] = "defensive"
            else:
                style["dimensions"]["cyclical_defensive"] = "balanced"
        
        # 确定主导风格
        dominant_count = {}
        for dim, s in style["dimensions"].items():
            if s != "balanced":
                dominant_count[s] = dominant_count.get(s, 0) + 1
        
        if dominant_count:
            style["dominant_style"] = max(dominant_count, key=dominant_count.get)
        
        # 保存到历史
        self.history["current_style"] = style
        self._save_history()
        
        return style
    
    def detect_style_switch(self) -> Optional[Dict]:
        """
        检测风格切换
        
        Returns:
            风格切换信息或 None
        """
        if len(self.history["daily_ratios"]) < self.SWITCH_DAYS:
            return None
        
        # 获取最近 N 天的比率
        recent = self.history["daily_ratios"][-self.SWITCH_DAYS:]
        older = self.history["daily_ratios"][-self.SWITCH_DAYS*2:-self.SWITCH_DAYS]
        
        if not older:
            return None
        
        # 计算变化
        switch = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "switches": [],
        }
        
        # 检查价值/成长切换
        if recent[0].get("value_growth") and older[0].get("value_growth"):
            recent_avg = sum(r.get("value_growth", 0) for r in recent) / len(recent)
            older_avg = sum(r.get("value_growth", 0) for r in older) / len(older)
            
            if older_avg > 0:
                change = (recent_avg - older_avg) / older_avg
                if abs(change) > self.SWITCH_THRESHOLD:
                    direction = "value" if change > 0 else "growth"
                    switch["switches"].append({
                        "dimension": "value_growth",
                        "direction": direction,
                        "change_pct": change * 100,
                    })
        
        # 检查大盘/小盘切换
        if recent[0].get("large_small") and older[0].get("large_small"):
            recent_avg = sum(r.get("large_small", 0) for r in recent) / len(recent)
            older_avg = sum(r.get("large_small", 0) for r in older) / len(older)
            
            if older_avg > 0:
                change = (recent_avg - older_avg) / older_avg
                if abs(change) > self.SWITCH_THRESHOLD:
                    direction = "large" if change > 0 else "small"
                    switch["switches"].append({
                        "dimension": "large_small",
                        "direction": direction,
                        "change_pct": change * 100,
                    })
        
        if switch["switches"]:
            self.history["last_switch"] = switch
            self._save_history()
            return switch
        
        return None
    
    def get_strategy_suggestion(self, style: Dict) -> Dict:
        """
        根据市场风格给出策略建议
        
        Args:
            style: 当前市场风格
        
        Returns:
            策略建议
        """
        suggestion = {
            "date": style["date"],
            "style": style,
            "suggestions": [],
        }
        
        dimensions = style.get("dimensions", {})
        
        # 价值风格
        if dimensions.get("value_growth") == "value":
            suggestion["suggestions"].append("✅ 价值风格占优：关注低 PE、高股息股票")
            suggestion["suggestions"].append("   选股规则：提高 PB、ROE 权重")
        elif dimensions.get("value_growth") == "growth":
            suggestion["suggestions"].append("✅ 成长风格占优：关注高增长股票")
            suggestion["suggestions"].append("   选股规则：提高营收增长、净利润增长权重")
        
        # 小盘风格
        if dimensions.get("large_small") == "small":
            suggestion["suggestions"].append("✅ 小盘风格占优：关注市值<200 亿股票")
        elif dimensions.get("large_small") == "large":
            suggestion["suggestions"].append("✅ 大盘风格占优：关注蓝筹股")
        
        # 周期风格
        if dimensions.get("cyclical_defensive") == "cyclical":
            suggestion["suggestions"].append("✅ 周期风格占优：关注周期股（有色、化工）")
        elif dimensions.get("cyclical_defensive") == "defensive":
            suggestion["suggestions"].append("✅ 防御风格占优：关注消费、医药")
        
        return suggestion
    
    def send_feishu_notification(self, message: str):
        """发送飞书通知"""
        try:
            feishu_config_file = os.path.join(CONFIG_DIR, "feishu_config.json")
            if not os.path.exists(feishu_config_file):
                return

            with open(feishu_config_file, 'r', encoding='utf-8') as f:
                feishu_config = json.load(f)

            webhook_url = feishu_config.get("webhook")
            if not webhook_url:
                return

            payload = {
                "msg_type": "text",
                "content": {
                    "text": f"📊 市场风格切换预警\n\n{message}\n\n时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            }

            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info("飞书通知发送成功")
        except Exception as e:
            logger.error(f"发送飞书通知失败：{e}")
    
    def run_check(self) -> Dict:
        """运行风格检查"""
        # 识别当前风格
        style = self.identify_current_style()
        
        # 检测切换
        switch = self.detect_style_switch()
        
        # 策略建议
        suggestion = self.get_strategy_suggestion(style)
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "style": style,
            "switch_detected": switch is not None,
            "switch_info": switch,
            "suggestion": suggestion,
        }
        
        # 发送切换通知
        if switch:
            message = "检测到市场风格切换：\n"
            for s in switch.get("switches", []):
                message += f"- {s['dimension']}: 转向{s['direction']} ({s['change_pct']:+.1f}%)\n"
            message += "\n建议调整选股策略"
            self.send_feishu_notification(message)
        
        return result


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="市场风格监控")
    parser.add_argument("action", choices=["check", "verify", "history"],
                       help="check=检查，verify=测试，history=查看历史")
    
    args = parser.parse_args()
    
    monitor = MarketStyleMonitor()
    
    if args.action == "check":
        result = monitor.run_check()
        
        print("\n" + "="*60)
        print("📊 市场风格检查结果")
        print("="*60)
        print(f"时间：{result['timestamp']}")
        print()
        
        style = result["style"]
        print("当前风格：")
        for dim, s in style.get("dimensions", {}).items():
            print(f"  {dim}: {s}")
        
        if style.get("dominant_style"):
            print(f"\n主导风格：{style['dominant_style']}")
        
        if result["switch_detected"]:
            print("\n🔄 检测到风格切换：")
            for s in result["switch_info"].get("switches", []):
                print(f"  - {s['dimension']}: 转向{s['direction']} ({s['change_pct']:+.1f}%)")
        
        print("\n策略建议：")
        for sug in result["suggestion"].get("suggestions", []):
            print(f"  {sug}")
        
        print("="*60)
    
    elif args.action == "verify":
        print("\n🧪 市场风格监控测试")
        print("="*60)
        
        # 测试获取指数数据
        print("\n1. 测试获取指数数据...")
        for style_name, info in monitor.STYLE_INDICES.items():
            data = monitor.get_index_data(style_name)
            if data:
                print(f"   {info['name']}: {data['price']:.2f} ({data['change_pct']:+.2f}%)")
            else:
                print(f"   {info['name']}: 获取失败")
        
        # 测试风格识别
        print("\n2. 测试风格识别...")
        style = monitor.identify_current_style()
        print(f"   主导风格：{style.get('dominant_style', 'N/A')}")
        
        print("\n" + "="*60)
        print("✅ 测试完成")
        print("="*60)
    
    elif args.action == "history":
        print("\n📊 市场风格历史")
        print("="*60)
        
        history = monitor.history.get("daily_ratios", [])[-10:]
        for day in history:
            print(f"{day['date']}: V/G={day.get('value_growth', 'N/A'):.3f} "
                  f"L/S={day.get('large_small', 'N/A'):.3f}")
        
        last_switch = monitor.history.get("last_switch")
        if last_switch:
            print(f"\n上次切换：{last_switch['date']}")
            for s in last_switch.get("switches", []):
                print(f"  - {s['dimension']}: {s['direction']}")
        
        print("="*60)


if __name__ == "__main__":
    main()
