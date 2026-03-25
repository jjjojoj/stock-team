#!/usr/bin/env python3
"""
熔断机制 - 防止黑天鹅事件导致巨额亏损

功能：
1. 监控大盘指数（上证指数、深证成指）
2. 监控市场恐慌情绪（替代 VIX）
3. 监控个股异常波动
4. 触发条件时执行熔断操作
5. 发送飞书通知

触发条件：
- 大盘跌幅>5% → 停止买入
- 大盘跌幅>7% → 强制减仓至 30%
- 大盘跌幅>10% → 空仓观望
- 个股单日涨跌>7% → 人工审核
- 恐慌情绪高涨 → 预警
"""

import sys
import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

# 配置
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# 确保目录存在
os.makedirs(LOG_DIR, exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'circuit_breaker.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class CircuitBreaker:
    """熔断器"""
    
    # 熔断阈值
    THRESHOLDS = {
        "market_drop_level1": -5.0,   # 大盘跌 5% → 停止买入
        "market_drop_level2": -7.0,   # 大盘跌 7% → 减仓至 30%
        "market_drop_level3": -10.0,  # 大盘跌 10% → 空仓
        "stock_surge": 7.0,           # 个股涨 7% → 人工审核
        "stock_plummet": -7.0,        # 个股跌 7% → 人工审核
        "panic_high": 30.0,           # 恐慌指数>30 → 预警
    }
    
    # 熔断状态
    STATUS_NORMAL = "normal"          # 正常
    STATUS_WARNING = "warning"        # 预警（停止买入）
    STATUS_REDUCED = "reduced"        # 减仓（仓位≤30%）
    STATUS_EMPTY = "empty"            # 空仓
    
    def __init__(self):
        self.config = self._load_config()
        self.status = self.STATUS_NORMAL
        self.triggered_rules = []
        self.last_check = None
    
    def _load_config(self) -> Dict:
        """加载配置"""
        config_file = os.path.join(CONFIG_DIR, "circuit_breaker.json")
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "enabled": True,
            "feishu_webhook": None,  # 从 feishu_config.json 读取
            "monitor_indices": ["000001.SH", "399001.SZ"],  # 上证指数、深证成指
        }
    
    def get_market_data(self) -> Dict:
        """获取大盘数据"""
        try:
            # 使用东方财富 API 获取大盘指数
            indices = {
                "000001.SH": {"name": "上证指数", "price": 0, "change_pct": 0},
                "399001.SZ": {"name": "深证成指", "price": 0, "change_pct": 0},
            }
            
            # 获取上证指数
            try:
                url = "http://push2.eastmoney.com/api/qt/stock/get"
                params = {
                    "secid": "1.000001",
                    "fields": "f43,f107,f104,f105,f46,f44,f51,f168,f47,f164,f116,f60,f45,f52,f50,f48,f169,f117,f119,f115,f120,f121,f122,f135,f136,f137,f138,f139,f140,f141,f142,f143,f144,f145,f146,f147,f148,f149,f150,f151,f152,f153,f154,f155,f156,f157,f158,f159,f160,f161,f162,f163"
                }
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data"):
                        f43 = data["data"].get("f43")
                        f107 = data["data"].get("f107")
                        if f43 is not None:
                            indices["000001.SH"]["price"] = float(f43 / 100)
                        if f107 is not None:
                            indices["000001.SH"]["change_pct"] = float(f107)
            except Exception as e:
                logger.warning(f"获取上证指数失败：{e}")
            
            # 获取深证成指
            try:
                url = "http://push2.eastmoney.com/api/qt/stock/get"
                params = {"secid": "0.399001"}
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data"):
                        f43 = data["data"].get("f43")
                        f107 = data["data"].get("f107")
                        if f43 is not None:
                            indices["399001.SZ"]["price"] = float(f43 / 100)
                        if f107 is not None:
                            indices["399001.SZ"]["change_pct"] = float(f107)
            except Exception as e:
                logger.warning(f"获取深证成指失败：{e}")
            
            return indices
        except Exception as e:
            logger.error(f"获取大盘数据失败：{e}")
            return {}
    
    def get_panic_index(self) -> float:
        """
        获取恐慌指数（替代 VIX）
        
        中国没有官方 VIX，使用以下替代指标：
        1. 上证指数波动率
        2. 涨跌家数比
        3. 跌停家数
        """
        try:
            # 简化版：使用涨跌家数比作为恐慌指标
            url = "http://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": "1.000001",
                "fields": "f107,f108,f109,f110"
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    # 使用涨跌幅作为恐慌指标（简化）
                    change_pct = float(data["data"].get("f107", 0))
                    # 转换为恐慌指数（0-50）
                    # 跌幅越大，恐慌指数越高
                    panic = min(50, max(0, -change_pct * 3 + 15))
                    return panic
            
            return 15.0  # 默认值
        except Exception as e:
            logger.warning(f"获取恐慌指数失败：{e}")
            return 15.0
    
    def check_market_conditions(self) -> Tuple[str, List[str]]:
        """
        检查市场条件，返回熔断状态和触发规则
        
        Returns:
            (status, triggered_rules)
        """
        self.triggered_rules = []
        
        # 获取大盘数据
        indices = self.get_market_data()
        panic_index = self.get_panic_index()
        
        # 找出最大跌幅
        max_drop = 0
        for code, data in indices.items():
            drop = data.get("change_pct", 0)
            if drop < max_drop:
                max_drop = drop
        
        # 检查熔断条件
        if max_drop <= self.THRESHOLDS["market_drop_level3"]:
            self.status = self.STATUS_EMPTY
            self.triggered_rules.append(f"大盘暴跌{max_drop:.1f}% > {self.THRESHOLDS['market_drop_level3']}% → 空仓")
        elif max_drop <= self.THRESHOLDS["market_drop_level2"]:
            self.status = self.STATUS_REDUCED
            self.triggered_rules.append(f"大盘暴跌{max_drop:.1f}% > {self.THRESHOLDS['market_drop_level2']}% → 减仓至 30%")
        elif max_drop <= self.THRESHOLDS["market_drop_level1"]:
            self.status = self.STATUS_WARNING
            self.triggered_rules.append(f"大盘下跌{max_drop:.1f}% > {self.THRESHOLDS['market_drop_level1']}% → 停止买入")
        elif panic_index >= self.THRESHOLDS["panic_high"]:
            self.status = self.STATUS_WARNING
            self.triggered_rules.append(f"恐慌指数{panic_index:.1f} > {self.THRESHOLDS['panic_high']} → 预警")
        else:
            self.status = self.STATUS_NORMAL
        
        self.last_check = datetime.now()
        
        logger.info(f"熔断检查完成：状态={self.status}, 触发规则={len(self.triggered_rules)}")
        
        return self.status, self.triggered_rules
    
    def check_stock_abnormal(self, stock_code: str, stock_name: str, change_pct: float) -> bool:
        """
        检查个股异常波动
        
        Returns:
            是否需要人工审核
        """
        needs_review = False
        
        if change_pct >= self.THRESHOLDS["stock_surge"]:
            needs_review = True
            logger.warning(f"个股暴涨：{stock_name} ({stock_code}) +{change_pct:.1f}%")
        elif change_pct <= self.THRESHOLDS["stock_plummet"]:
            needs_review = True
            logger.warning(f"个股暴跌：{stock_name} ({stock_code}) {change_pct:.1f}%")
        
        return needs_review
    
    def should_buy(self) -> bool:
        """是否允许买入"""
        if not self.config.get("enabled", True):
            return True
        return self.status in [self.STATUS_NORMAL]
    
    def should_sell(self) -> bool:
        """是否允许卖出"""
        if not self.config.get("enabled", True):
            return True
        return self.status != self.STATUS_EMPTY
    
    def get_max_position(self) -> float:
        """获取最大仓位限制"""
        if self.status == self.STATUS_EMPTY:
            return 0.0
        elif self.status == self.STATUS_REDUCED:
            return 0.3
        elif self.status == self.STATUS_WARNING:
            return 0.5
        else:
            return 1.0
    
    def send_feishu_notification(self, message: str):
        """发送飞书通知"""
        try:
            sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
            from feishu_notifier import send_feishu_message

            if send_feishu_message(
                title="🚨 熔断机制预警",
                content=f"{message}\n\n时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                level="critical",
            ):
                logger.info("飞书通知发送成功")
            else:
                logger.error("飞书通知发送失败")
        except Exception as e:
            logger.error(f"发送飞书通知失败：{e}")
    
    def run_check(self, send_notification: bool = True) -> Dict:
        """
        运行熔断检查
        
        Returns:
            检查结果
        """
        status, rules = self.check_market_conditions()
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "triggered_rules": rules,
            "max_position": self.get_max_position(),
            "can_buy": self.should_buy(),
            "can_sell": self.should_sell(),
        }
        
        # 发送通知
        if send_notification and rules:
            message = "\n".join(rules)
            self.send_feishu_notification(message)
        
        return result
    
    def run_continuous_monitor(self, interval_minutes: int = 5):
        """
        持续监控（盘中运行）
        
        Args:
            interval_minutes: 检查间隔（分钟）
        """
        import time
        
        logger.info(f"开始持续监控，间隔{interval_minutes}分钟")
        
        while True:
            try:
                result = self.run_check(send_notification=True)
                
                # 只在状态变化时通知
                if result["triggered_rules"]:
                    logger.info(f"熔断状态：{result['status']}, 最大仓位：{result['max_position']*100:.0f}%")
                
                time.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("监控停止")
                break
            except Exception as e:
                logger.error(f"监控异常：{e}")
                time.sleep(60)  # 异常后等待 1 分钟


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="熔断机制")
    parser.add_argument("action", choices=["check", "monitor", "verify"],
                       help="check=检查一次，monitor=持续监控，verify=测试")
    parser.add_argument("--interval", type=int, default=5, help="监控间隔（分钟）")
    parser.add_argument("--no-notify", action="store_true", help="不发送通知")
    
    args = parser.parse_args()
    
    breaker = CircuitBreaker()
    
    if args.action == "check":
        # 检查一次
        result = breaker.run_check(send_notification=not args.no_notify)
        print("\n" + "="*60)
        print("🔍 熔断机制检查结果")
        print("="*60)
        print(f"状态：{result['status']}")
        print(f"最大仓位：{result['max_position']*100:.0f}%")
        print(f"允许买入：{result['can_buy']}")
        print(f"允许卖出：{result['can_sell']}")
        if result['triggered_rules']:
            print("\n触发规则：")
            for rule in result['triggered_rules']:
                print(f"  - {rule}")
        else:
            print("\n✅ 无触发规则，市场正常")
        print("="*60)
    
    elif args.action == "monitor":
        # 持续监控
        breaker.run_continuous_monitor(interval_minutes=args.interval)
    
    elif args.action == "verify":
        # 测试
        print("\n🧪 熔断机制测试")
        print("="*60)
        
        # 测试 1：获取大盘数据
        print("\n1. 测试获取大盘数据...")
        indices = breaker.get_market_data()
        for code, data in indices.items():
            print(f"   {code}: {data['name']} {data['price']:.2f} ({data['change_pct']:+.2f}%)")
        
        # 测试 2：获取恐慌指数
        print("\n2. 测试获取恐慌指数...")
        panic = breaker.get_panic_index()
        print(f"   恐慌指数：{panic:.1f}")
        
        # 测试 3：检查熔断条件
        print("\n3. 测试熔断检查...")
        result = breaker.run_check(send_notification=False)
        print(f"   状态：{result['status']}")
        print(f"   最大仓位：{result['max_position']*100:.0f}%")
        
        # 测试 4：个股异常检测
        print("\n4. 测试个股异常检测...")
        verify_stocks = [
            ("sh.600459", "贵研铂业", 8.5),
            ("sz.000758", "中色股份", -8.2),
            ("sh.600000", "浦发银行", 1.2),
        ]
        for code, name, change in verify_stocks:
            needs_review = breaker.check_stock_abnormal(code, name, change)
            status = "⚠️ 需审核" if needs_review else "✅ 正常"
            print(f"   {name} ({code}): {change:+.1f}% {status}")
        
        print("\n" + "="*60)
        print("✅ 测试完成")
        print("="*60)


if __name__ == "__main__":
    main()
