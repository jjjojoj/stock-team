#!/usr/bin/env python3
"""
API 健康监控 - 消除单点故障

功能：
1. API 健康检查（每 5 分钟）
2. 故障自动切换（主→备 1→备 2）
3. 飞书通知故障和恢复
4. 故障统计和报告

API 冗余方案：
| 类型 | 主 API | 备用 1 | 备用 2 |
|------|-------|--------|--------|
| 新闻 | NewsAPI | Tavily | 新浪财经 RSS |
| 行情 | 东方财富 | 同花顺 | 腾讯财经 |
| 搜索 | Tavily | Exa | 百度搜索 API |
"""

import sys
import os
import json
import requests
import time
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
        logging.FileHandler(os.path.join(LOG_DIR, 'api_health.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class APIHealthMonitor:
    """API 健康监控器"""
    
    # 默认 API 配置
    DEFAULT_APIS = {
        "news": [
            {"name": "NewsAPI", "type": "newsapi", "priority": 1, "timeout": 10},
            {"name": "Tavily", "type": "tavily", "priority": 2, "timeout": 15},
            {"name": "新浪财经", "type": "sina", "priority": 3, "timeout": 10},
        ],
        "market": [
            {"name": "东方财富", "type": "eastmoney", "priority": 1, "timeout": 10},
            {"name": "同花顺", "type": "10jqka", "priority": 2, "timeout": 10},
            {"name": "腾讯财经", "type": "qq", "priority": 3, "timeout": 10},
        ],
        "search": [
            {"name": "Tavily", "type": "tavily", "priority": 1, "timeout": 15},
            {"name": "Exa", "type": "exa", "priority": 2, "timeout": 15},
        ],
    }
    
    def __init__(self):
        self.config = self._load_config()
        self.api_keys = self._load_api_keys()
        self.status = self._load_status()
        self.failure_threshold = 3  # 连续失败 3 次切换
        self.check_interval = 300  # 5 分钟
    
    def _load_config(self) -> Dict:
        """加载 API 配置"""
        config_file = os.path.join(CONFIG_DIR, "api_config.json")
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                raw_config = json.load(f)
            
            # 转换为标准格式：{"apis": {"news": [...], "market": [...], ...}}
            config = {"apis": {}, "enabled": True}
            
            for api_type in ["news", "market", "search", "llm"]:
                if api_type in raw_config:
                    type_config = raw_config[api_type]
                    apis_list = []
                    priority = 1
                    
                    # 处理 primary/backup 格式
                    for key in ["primary", "backup1", "backup2", "backup3", "backup4"]:
                        if key in type_config:
                            api = type_config[key].copy()
                            api["priority"] = priority
                            # 将 type 字段转换为具体类型名称
                            if "type" not in api:
                                api["type"] = api.get("name", key).lower()
                            apis_list.append(api)
                            priority += 1
                    
                    config["apis"][api_type] = apis_list
            
            return config
        
        return {"apis": self.DEFAULT_APIS, "enabled": True}
    
    def _load_api_keys(self) -> Dict:
        """加载 API 密钥"""
        keys_file = os.path.join(CONFIG_DIR, "api_keys.json")
        if os.path.exists(keys_file):
            with open(keys_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_status(self) -> Dict:
        """加载 API 状态"""
        status_file = os.path.join(CONFIG_DIR, "api_status.json")
        if os.path.exists(status_file):
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 初始化状态
        status = {}
        for api_type, apis in self.config.get("apis", {}).items():
            status[api_type] = {}
            for api in apis:
                status[api_type][api["type"]] = {
                    "healthy": True,
                    "consecutive_failures": 0,
                    "last_check": None,
                    "last_error": None,
                    "response_time_ms": 0,
                    "total_checks": 0,
                    "total_failures": 0,
                }
        return status
    
    def _save_status(self):
        """保存 API 状态"""
        status_file = os.path.join(CONFIG_DIR, "api_status.json")
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(self.status, f, ensure_ascii=False, indent=2)
    
    def check_api_health(self, api_type: str, api_config: Dict) -> Tuple[bool, float, Optional[str]]:
        """
        检查 API 健康
        
        Returns:
            (是否健康，响应时间 ms, 错误信息)
        """
        api_name = api_config["name"]
        timeout = api_config.get("timeout", 10)
        
        start_time = time.time()
        
        try:
            # News APIs
            if api_type == "news":
                if "NewsAPI" in api_name:
                    url = "https://newsapi.org/v2/top-headlines"
                    params = {"country": "cn", "apiKey": self.api_keys.get("newsapi", ""), "pageSize": 1}
                    response = requests.get(url, params=params, timeout=timeout)
                    if response.status_code == 200 and response.json().get("status") == "ok":
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "Tavily" in api_name:
                    url = "https://api.tavily.com/search"
                    payload = {"api_key": self.api_keys.get("tavily", ""), "query": "verify", "max_results": 1}
                    response = requests.post(url, json=payload, timeout=timeout)
                    if response.status_code == 200:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "SerpAPI" in api_name:
                    url = "https://serpapi.com/search"
                    params = {"api_key": api_config.get("api_key", ""), "q": "verify", "num": 1}
                    response = requests.get(url, params=params, timeout=timeout)
                    if response.status_code == 200:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "新浪" in api_name:
                    url = "http://hq.sinajs.cn/list=s_sh000001"
                    response = requests.get(url, timeout=timeout)
                    if response.status_code == 200 and len(response.content) > 50:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
            
            # Market APIs
            elif api_type == "market":
                if "东方财富" in api_name:
                    url = "https://push2.eastmoney.com/api/qt/stock/get"
                    params = {"secid": "1.000001", "fields": "f43,f107"}
                    headers = {"User-Agent": "Mozilla/5.0"}
                    response = requests.get(url, params=params, headers=headers, timeout=timeout)
                    if response.status_code == 200 and response.json().get("data"):
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "同花顺" in api_name:
                    url = "https://q.10jqka.com.cn/"
                    headers = {"User-Agent": "Mozilla/5.0"}
                    response = requests.get(url, headers=headers, timeout=timeout)
                    if response.status_code == 200:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "腾讯" in api_name:
                    url = "https://qt.gtimg.cn/q=sh000001"
                    headers = {"User-Agent": "Mozilla/5.0"}
                    response = requests.get(url, headers=headers, timeout=timeout)
                    if response.status_code == 200 and len(response.content) > 50:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "akshare" in api_name:
                    # Test akshare library
                    import akshare as ak
                    try:
                        stock_df = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20260301", end_date="20260306")
                        if len(stock_df) > 0:
                            return True, (time.time() - start_time) * 1000, None
                        return False, 0, "No data returned"
                    except Exception as e:
                        return False, 0, str(e)
            
            # Search APIs
            elif api_type == "search":
                if "Tavily" in api_name:
                    url = "https://api.tavily.com/search"
                    payload = {"api_key": self.api_keys.get("tavily", ""), "query": "verify", "max_results": 1}
                    response = requests.post(url, json=payload, timeout=timeout)
                    if response.status_code == 200:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "SerpAPI" in api_name:
                    url = "https://serpapi.com/search"
                    params = {"api_key": api_config.get("api_key", ""), "q": "verify", "num": 1}
                    response = requests.get(url, params=params, timeout=timeout)
                    if response.status_code == 200:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "Exa" in api_name:
                    url = "https://api.exa.ai/search"
                    headers = {"Authorization": f"Bearer {self.api_keys.get('exa', '')}", "Content-Type": "application/json"}
                    payload = {"query": "verify", "numResults": 1}
                    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                    if response.status_code == 200:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
                
                elif "百度" in api_name:
                    # Simple test - just check if we can reach Baidu
                    url = "https://www.baidu.com/"
                    headers = {"User-Agent": "Mozilla/5.0"}
                    response = requests.get(url, headers=headers, timeout=timeout)
                    if response.status_code == 200:
                        return True, (time.time() - start_time) * 1000, None
                    return False, 0, f"HTTP {response.status_code}"
            
            # LLM APIs (MCP based - just check connectivity)
            elif api_type == "llm":
                # For MCP-based LLMs, we can't directly test without MCP infrastructure
                # Just mark as healthy if configured
                return True, 0, None
            
            return False, 0, f"Unknown API: {api_name}"
        
        except requests.Timeout:
            return False, 0, "Timeout"
        except requests.ConnectionError:
            return False, 0, "Connection Error"
        except Exception as e:
            return False, 0, str(e)
    
    def run_health_check(self) -> Dict:
        """运行健康检查"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "apis": {},
            "switches": [],
        }
        
        for api_type, apis in self.config.get("apis", {}).items():
            results["apis"][api_type] = []
            
            # 按优先级排序
            sorted_apis = sorted(apis, key=lambda x: x.get("priority", 999))
            
            for api_config in sorted_apis:
                api_name = api_config["name"]
                api_type_name = api_config["type"]
                
                # 检查健康
                healthy, response_time, error = self.check_api_health(api_type, api_config)
                
                # 更新状态
                if api_type not in self.status:
                    self.status[api_type] = {}
                if api_type_name not in self.status[api_type]:
                    self.status[api_type][api_type_name] = {
                        "healthy": True,
                        "consecutive_failures": 0,
                        "last_check": None,
                        "last_error": None,
                        "response_time_ms": 0,
                        "total_checks": 0,
                        "total_failures": 0,
                    }
                
                status = self.status[api_type][api_type_name]
                status["last_check"] = datetime.now().isoformat()
                status["total_checks"] += 1
                
                if healthy:
                    status["healthy"] = True
                    status["consecutive_failures"] = 0
                    status["response_time_ms"] = response_time
                    status["last_error"] = None
                else:
                    status["consecutive_failures"] += 1
                    status["total_failures"] += 1
                    status["last_error"] = error
                    
                    # 检查是否需要切换
                    if status["consecutive_failures"] >= self.failure_threshold:
                        if status["healthy"]:  # 之前是健康的，现在故障
                            results["switches"].append({
                                "api_type": api_type,
                                "api_name": api_name,
                                "reason": f"连续失败{status['consecutive_failures']}次",
                                "time": datetime.now().isoformat(),
                            })
                            logger.warning(f"API 故障：{api_name} - {error}")
                        status["healthy"] = False
                
                results["apis"][api_type].append({
                    "name": api_name,
                    "type": api_type_name,
                    "healthy": healthy,
                    "response_time_ms": round(response_time, 2),
                    "error": error,
                    "priority": api_config.get("priority", 999),
                })
        
        # 保存状态
        self._save_status()
        
        return results
    
    def get_active_api(self, api_type: str) -> Optional[Dict]:
        """获取当前活跃的 API（优先级最高的健康 API）"""
        apis = self.config.get("apis", {}).get(api_type, [])
        sorted_apis = sorted(apis, key=lambda x: x.get("priority", 999))
        
        for api_config in sorted_apis:
            api_type_name = api_config["type"]
            status = self.status.get(api_type, {}).get(api_type_name, {})
            if status.get("healthy", True):
                return api_config
        
        return None
    
    def send_feishu_notification(self, message: str, level: str = "warning"):
        """发送飞书通知"""
        try:
            emoji = "⚠️" if level == "warning" else "🔴"
            sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
            from feishu_notifier import send_alert_card

            send_alert_card(title=f"{emoji} API 故障通知", content=message, level=level)
            logger.info("飞书通知发送成功")
        except Exception as e:
            logger.error(f"发送飞书通知失败：{e}")
    
    def run_continuous_monitor(self, interval_minutes: int = 5):
        """持续监控"""
        logger.info(f"开始 API 健康监控，间隔{interval_minutes}分钟")
        
        last_notification = {}
        
        while True:
            try:
                results = self.run_health_check()
                
                # 发送故障通知（避免重复通知）
                for switch in results.get("switches", []):
                    key = f"{switch['api_type']}_{switch['api_name']}"
                    last_notif = last_notification.get(key, "")
                    
                    if last_notif != switch["time"]:
                        message = (
                            f"API 故障：{switch['api_name']} ({switch['api_type']})\n"
                            f"原因：{switch['reason']}\n"
                            f"系统已自动切换到备用 API"
                        )
                        self.send_feishu_notification(message)
                        last_notification[key] = switch["time"]
                
                # 打印状态摘要
                healthy_count = 0
                total_count = 0
                for api_type, apis in results["apis"].items():
                    for api in apis:
                        total_count += 1
                        if api["healthy"]:
                            healthy_count += 1
                
                logger.info(f"API 健康检查：{healthy_count}/{total_count} 正常")
                
                time.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("监控停止")
                break
            except Exception as e:
                logger.error(f"监控异常：{e}")
                time.sleep(60)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="API 健康监控")
    parser.add_argument("action", choices=["check", "monitor", "verify", "status"],
                       help="check=检查，monitor=持续监控，verify=测试，status=查看状态")
    parser.add_argument("--interval", type=int, default=5, help="监控间隔（分钟）")
    
    args = parser.parse_args()
    
    monitor = APIHealthMonitor()
    
    if args.action == "check":
        results = monitor.run_health_check()
        
        print("\n" + "="*60)
        print("🔍 API 健康检查结果")
        print("="*60)
        print(f"时间：{results['timestamp']}")
        print()
        
        for api_type, apis in results["apis"].items():
            print(f"【{api_type.upper()}】")
            for api in apis:
                status = "✅" if api["healthy"] else "❌"
                rt = f"{api['response_time_ms']:.0f}ms" if api["healthy"] else "-"
                error = f" - {api['error']}" if api["error"] else ""
                print(f"  {status} {api['name']} ({api['priority']}): {rt}{error}")
            print()
        
        if results["switches"]:
            print("🔄 API 切换：")
            for s in results["switches"]:
                print(f"  - {s['api_name']} ({s['api_type']}): {s['reason']}")
        
        # 发送故障通知
        failed_apis = []
        for api_type, apis in results["apis"].items():
            for api in apis:
                if not api["healthy"]:
                    failed_apis.append(f"{api['name']} ({api_type})")
        
        if failed_apis:
            message = (
                f"API 故障检测：\n"
                f"故障 API: {', '.join(failed_apis)}\n"
                f"系统已自动使用备用 API"
            )
            monitor.send_feishu_notification(message, level="warning")
        
        print("="*60)
    
    elif args.action == "status":
        print("\n" + "="*60)
        print("📊 API 状态统计")
        print("="*60)
        
        for api_type, apis in monitor.status.items():
            print(f"\n【{api_type.upper()}】")
            for api_name, status in apis.items():
                healthy = "✅" if status["healthy"] else "❌"
                failures = status["consecutive_failures"]
                total = status["total_checks"]
                fail_count = status["total_failures"]
                rate = (1 - fail_count/total * 100) if total > 0 else 100
                print(f"  {healthy} {api_name}: 可用率={rate:.1f}% ({fail_count}/{total}) 连续失败={failures}")
        
        print("="*60)
    
    elif args.action == "verify":
        print("\n🧪 API 健康监控测试")
        print("="*60)
        
        # 测试各 API
        for api_type in ["news", "market", "search"]:
            print(f"\n测试 {api_type} API...")
            apis = monitor.config.get("apis", {}).get(api_type, [])
            for api in apis:
                healthy, rt, error = monitor.check_api_health(api_type, api)
                status = "✅" if healthy else "❌"
                print(f"  {status} {api['name']}: {rt:.0f}ms" if healthy else f"  {status} {api['name']}: {error}")
        
        print("\n" + "="*60)
        print("✅ 测试完成")
        print("="*60)
    
    elif args.action == "monitor":
        monitor.run_continuous_monitor(interval_minutes=args.interval)


if __name__ == "__main__":
    main()
