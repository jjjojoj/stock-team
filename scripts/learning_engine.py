#!/usr/bin/env python3
"""
学习引擎 v2 - 集成知识库
从成功/失败中学习，持续优化策略
使用 knowledge 模块的向量存储
"""

import sys
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re

# 添加项目路径
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

# 添加虚拟环境路径
VENV_PATH = os.path.join(PROJECT_ROOT, "venv/lib/python3.14/site-packages")
sys.path.insert(0, VENV_PATH)

# 导入知识库
from knowledge import get_knowledge_base

# 学习配置
LEARNING_CONFIG = {
    "promotion_threshold": 3,
    "demotion_days": 30,
    "archive_days": 90,
    "min_confidence": 0.7,
}

# 分层存储（保留原有的 markdown 文件作为备份）
LEARNING_DIR = os.path.join(PROJECT_ROOT, "learning")
MEMORY_TIERS = {
    "HOT": os.path.join(LEARNING_DIR, "memory.md"),
    "WARM": os.path.join(LEARNING_DIR, "patterns.md"),
    "COLD": os.path.join(LEARNING_DIR, "archive.md"),
}


class LearningEngineV2:
    """学习引擎 v2（使用知识库）"""
    
    def __init__(self):
        self.kb = get_knowledge_base()
        self._ensure_dirs()
        self._load_legacy_memory()
        
        print("✅ 学习引擎初始化完成")
        print(f"   知识条目数: {len(self.kb.items)}")
    
    def _ensure_dirs(self):
        """确保目录存在"""
        os.makedirs(LEARNING_DIR, exist_ok=True)
    
    def _load_legacy_memory(self):
        """加载旧的 markdown 记忆（兼容性）"""
        self.legacy_rules = []
        
        hot_file = MEMORY_TIERS["HOT"]
        if os.path.exists(hot_file):
            with open(hot_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for line in content.split('\n'):
                if line.startswith('- [ ]') or line.startswith('- [x]'):
                    match = re.match(r'- \[([ x])\] (.+?) \(出现次数: (\d+), 最后出现: (.+?)\)', line)
                    if match:
                        self.legacy_rules.append({
                            "active": match.group(1) == 'x',
                            "content": match.group(2),
                            "count": int(match.group(3)),
                            "last_seen": match.group(4),
                        })
    
    def record_success(self, trade_data: Dict):
        """记录成功案例到知识库"""
        content = f"""
股票: {trade_data.get('name', '')} ({trade_data.get('code', '')})
操作: {trade_data.get('action', '')}
价格: {trade_data.get('price', 0):.2f}
数量: {trade_data.get('shares', 0)}
理由: {trade_data.get('reason', '')}
结果: {trade_data.get('result', '')}
退出原因: {trade_data.get('exit_reason', '')}
"""
        
        self.kb.add_decision(
            content=content,
            metadata={
                "stock": trade_data.get("code", ""),
                "action": trade_data.get("action", ""),
                "result": "success",
                "profit_pct": trade_data.get("result", "0%"),
            }
        )
        
        self._record_legacy(trade_data, "success")
        print(f"✅ 记录成功案例: {trade_data.get('name', '')}")
    
    def record_failure(self, trade_data: Dict):
        """记录失败案例到知识库"""
        lesson = trade_data.get("lesson", "")
        content = f"""
股票: {trade_data.get('name', '')} ({trade_data.get('code', '')})
操作: {trade_data.get('action', '')}
价格: {trade_data.get('price', 0):.2f}
数量: {trade_data.get('shares', 0)}
理由: {trade_data.get('reason', '')}
结果: {trade_data.get('result', '')}
退出原因: {trade_data.get('exit_reason', '')}
教训: {lesson}
"""
        
        self.kb.add_lesson(
            content=content,
            metadata={
                "stock": trade_data.get("code", ""),
                "action": trade_data.get("action", ""),
                "result": "failure",
                "lesson": lesson,
            }
        )
        
        self._record_legacy(trade_data, "failure")
        print(f"❌ 记录失败案例: {trade_data.get('name', '')}")
        print(f"   教训: {lesson}")
    
    def _record_legacy(self, trade_data: Dict, result_type: str):
        """保存到旧的 markdown 文件（兼容性）"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        log_entry = f"\n### {timestamp} - {result_type.upper()}\n"
        log_entry += f"- 股票: {trade_data.get('name', '')} ({trade_data.get('code', '')})\n"
        log_entry += f"- 操作: {trade_data.get('action', '')} @ ¥{trade_data.get('price', 0):.2f}\n"
        log_entry += f"- 理由: {trade_data.get('reason', '')}\n"
        log_entry += f"- 结果: {trade_data.get('result', '')}\n"
        
        if result_type == "failure" and trade_data.get('lesson'):
            log_entry += f"- **教训**: {trade_data.get('lesson', '')}\n"
        
        with open(MEMORY_TIERS["HOT"], 'a', encoding='utf-8') as f:
            f.write(log_entry)
    
    def find_similar_situations(self, query: str, limit: int = 5) -> List:
        """搜索相似情况（使用知识库的语义搜索）"""
        results = self.kb.search(query, top_k=limit)
        
        print(f"\n🔍 搜索相似情况: '{query}'")
        print(f"   找到 {len(results)} 条相关记录")
        
        for i, (item, score) in enumerate(results, 1):
            item_type = item.metadata.get("type", "unknown")
            print(f"\n{i}. [{item_type}] 相似度: {score:.2f}")
            print(f"   内容: {item.content[:100]}...")
            if item.metadata:
                print(f"   股票: {item.metadata.get('stock', 'N/A')}")
        
        return results
    
    def check_before_trade(self, code: str, reason: str) -> Dict:
        """交易前检查，基于历史经验给出建议"""
        result = {
            "warnings": [],
            "similar_failures": [],
            "recommendation": "可以操作",
        }
        
        # 1. 搜索相似失败案例
        failures = self.kb.get_all_by_type("lesson")
        stock_failures = [f for f in failures if f.metadata.get("stock") == code]
        
        if stock_failures:
            result["similar_failures"] = stock_failures[:3]
            result["warnings"].append(f"该股票有 {len(stock_failures)} 次失败记录")
        
        # 2. 检查交易理由中的关键词
        warning_keywords = {
            "追高": "追高买入风险大，建议等待回调",
            "突破": "突破可能是假突破，注意止损",
            "涨停": "涨停板买入风险高",
            "暴涨": "暴涨后回调风险大",
        }
        
        for keyword, warning in warning_keywords.items():
            if keyword in reason:
                result["warnings"].append(warning)
        
        # 3. 搜索相似教训
        similar = self.kb.search(reason, top_k=3)
        failure_similar = [(item, score) for item, score in similar 
                          if item.metadata.get("type") == "lesson" and score > 0.7]
        
        if failure_similar:
            result["warnings"].append(f"发现 {len(failure_similar)} 个相似失败案例")
        
        # 4. 给出综合建议
        if len(result["warnings"]) >= 2:
            result["recommendation"] = "⚠️ 建议谨慎操作"
        elif len(result["warnings"]) == 1:
            result["recommendation"] = "注意风险"
        
        return result
    
    def get_active_rules(self) -> List[Dict]:
        """获取所有活跃规则"""
        rules = []
        
        # 从知识库获取规则
        kb_rules = self.kb.get_all_by_type("rule")
        for rule in kb_rules:
            rules.append({
                "content": rule.content,
                "active": True,
                "source": "knowledge_base",
                "count": rule.metadata.get("count", 1),
            })
        
        # 添加旧的规则（兼容性）
        for rule in self.legacy_rules:
            if rule["active"]:
                rules.append({
                    "content": rule["content"],
                    "active": True,
                    "source": "legacy",
                    "count": rule["count"],
                })
        
        return rules
    
    def add_rule(self, content: str, metadata: Optional[Dict] = None):
        """添加新规则到知识库"""
        self.kb.add_rule(
            content=content,
            metadata=metadata or {}
        )
        print(f"✅ 添加规则: {content}")
    
    def daily_review(self) -> Dict:
        """每日复盘"""
        print("\n📊 每日复盘")
        print("=" * 60)
        
        # 统计各类知识
        lessons = self.kb.get_all_by_type("lesson")
        rules = self.kb.get_all_by_type("rule")
        decisions = self.kb.get_all_by_type("decision")
        predictions = self.kb.get_all_by_type("prediction")
        
        print(f"教训: {len(lessons)} 条")
        print(f"规则: {len(rules)} 条")
        print(f"决策: {len(decisions)} 条")
        print(f"预测: {len(predictions)} 条")
        
        # 最近 7 天的教训
        recent_lessons = []
        for l in lessons:
            try:
                created = datetime.fromisoformat(l.created_at)
                if (datetime.now() - created).days < 7:
                    recent_lessons.append(l)
            except:
                pass
        
        if recent_lessons:
            print(f"\n⚠️ 最近 7 天的教训:")
            for lesson in recent_lessons:
                print(f"   - {lesson.content[:80]}...")
        
        return {
            "total_lessons": len(lessons),
            "total_rules": len(rules),
            "total_decisions": len(decisions),
            "recent_lessons": len(recent_lessons),
        }
    
    def export_to_markdown(self, output_path: str):
        """导出知识库到 markdown（用于备份）"""
        content = "# 知识库导出\n\n"
        content += f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        
        type_names = ["lesson", "rule", "decision", "prediction"]
        for type_name in type_names:
            items = self.kb.get_all_by_type(type_name)
            if items:
                content += f"## {type_name.upper()}\n\n"
                for item in items:
                    content += f"### {item.created_at}\n"
                    content += f"{item.content}\n\n"
                    if item.metadata:
                        content += f"元数据: {json.dumps(item.metadata, ensure_ascii=False)}\n\n"
                    content += "---\n\n"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 导出完成: {output_path}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="学习引擎 v2")
    parser.add_argument("action", choices=[
        "review", "search", "add_rule", "check", "export"
    ], help="操作类型")
    parser.add_argument("arg", nargs="?", help="参数")
    parser.add_argument("--code", help="股票代码（用于 check）")
    parser.add_argument("--reason", help="交易理由（用于 check）")
    
    args = parser.parse_args()
    
    engine = LearningEngineV2()
    
    if args.action == "review":
        engine.daily_review()
    elif args.action == "search":
        if not args.arg:
            print("❌ 请指定搜索关键词")
            return
        engine.find_similar_situations(args.arg)
    elif args.action == "add_rule":
        if not args.arg:
            print("❌ 请指定规则内容")
            return
        engine.add_rule(args.arg)
    elif args.action == "check":
        code = args.code or "sh.600519"
        reason = args.reason or "技术面金叉"
        result = engine.check_before_trade(code, reason)
        
        print(f"\n🔍 交易前检查: {code}")
        print(f"理由: {reason}")
        print(f"\n⚠️ 警告 ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"   - {w}")
        print(f"\n💡 建议: {result['recommendation']}")
    elif args.action == "export":
        output = args.arg or os.path.join(LEARNING_DIR, "knowledge_export.md")
        engine.export_to_markdown(output)


if __name__ == "__main__":
    main()
