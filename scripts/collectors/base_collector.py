#!/usr/bin/env python3
"""
信息源收集器基类
定义所有收集器的通用接口和功能
"""

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class BaseCollector(ABC):
    """信息源收集器基类"""

    def __init__(self):
        """初始化收集器"""
        self.config = self._load_config()
        self.validation_pool_path = Path(__file__).parent.parent.parent / "learning" / "rule_validation_pool.json"
        self.stats = {
            "total_collected": 0,
            "total_added": 0,
            "total_skipped": 0,
            "last_run": None
        }

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        config_path = Path(__file__).parent.parent.parent / "config" / "knowledge_sources.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _load_validation_pool(self) -> Dict[str, Any]:
        """加载验证池"""
        if self.validation_pool_path.exists():
            with open(self.validation_pool_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_validation_pool(self, pool: Dict[str, Any]) -> None:
        """保存验证池"""
        with open(self.validation_pool_path, 'w', encoding='utf-8') as f:
            json.dump(pool, f, ensure_ascii=False, indent=2)

    def _generate_rule_id(self, prefix: str) -> str:
        """生成规则 ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{prefix}_{timestamp}"

    def _rule_exists(self, rule_text: str) -> bool:
        """检查规则是否已存在"""
        pool = self._load_validation_pool()
        for rule_data in pool.values():
            if rule_data.get("rule", "") == rule_text:
                return True
        return False

    def _add_to_validation_pool(self, item: Dict[str, Any]) -> bool:
        """
        添加条目到验证池

        Args:
            item: 包含 rule, source, source_tier, testable_form 等信息的字典

        Returns:
            bool: 是否成功添加
        """
        # 检查规则是否已存在
        if self._rule_exists(item.get("rule", "")):
            self.stats["total_skipped"] += 1
            return False

        # 生成规则 ID
        rule_id = self._generate_rule_id(item.get("source_tier", "unknown"))

        # 构建完整的规则对象
        rule_data = {
            "rule_id": rule_id,
            "rule": item.get("rule", ""),
            "testable_form": item.get("testable_form", ""),
            "category": item.get("category", "未分类"),
            "source": item.get("source", ""),
            "source_tier": item.get("source_tier", ""),
            "source_url": item.get("source_url", ""),
            "status": "validating",
            "confidence": item.get("confidence", 0.5),
            "confidence_threshold": item.get("confidence_threshold", 0.7),
            "tags": item.get("tags", []),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "backtest": {
                "samples": 0,
                "success_rate": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0
            },
            "live_test": self._get_live_test_config(item.get("source_tier", ""))
        }

        # 添加可选字段
        for key in ["source_book", "source_type", "source_id", "experience_based", "is_negative", "auto_generated"]:
            if key in item:
                rule_data[key] = item[key]

        # 加载验证池并添加新规则
        pool = self._load_validation_pool()
        pool[rule_id] = rule_data
        self._save_validation_pool(pool)

        self.stats["total_added"] += 1
        return True

    def _get_live_test_config(self, source_tier: str) -> Dict[str, Any]:
        """
        根据信息源 Tier 获取验证配置

        Args:
            source_tier: 信息源等级 (tier1, tier2, tier3)

        Returns:
            验证配置字典
        """
        configs = {
            "tier1": {
                "samples": 0,
                "success_rate": 0.0,
                "started_at": datetime.now().isoformat(),
                "required_samples": 3,
                "required_success_rate": 0.5
            },
            "tier2": {
                "samples": 0,
                "success_rate": 0.0,
                "started_at": datetime.now().isoformat(),
                "required_samples": 5,
                "required_success_rate": 0.6
            },
            "tier3": {
                "samples": 0,
                "success_rate": 0.0,
                "started_at": datetime.now().isoformat(),
                "required_samples": 10,
                "required_success_rate": 0.7
            }
        }
        return configs.get(source_tier, {
            "samples": 0,
            "success_rate": 0.0,
            "started_at": datetime.now().isoformat()
        })

    def log(self, message: str) -> None:
        """记录日志"""
        print(f"[{self.__class__.__name__}] {message}")

    @abstractmethod
    def collect_all(self) -> List[Dict[str, Any]]:
        """
        收集所有信息源内容

        Returns:
            收集到的信息条目列表
        """
        pass

    def collect_and_add(self) -> Dict[str, int]:
        """
        收集并添加到验证池

        Returns:
            统计信息字典
        """
        self.stats["total_collected"] = 0
        self.stats["total_added"] = 0
        self.stats["total_skipped"] = 0
        self.stats["last_run"] = datetime.now().isoformat()

        items = self.collect_all()
        self.stats["total_collected"] = len(items)

        self.log(f"Collected {len(items)} items")

        for item in items:
            if self._add_to_validation_pool(item):
                self.log(f"Added: {item.get('rule', '')[:50]}...")
            else:
                self.log(f"Skipped (duplicate): {item.get('rule', '')[:50]}...")

        self.log(f"Added {self.stats['total_added']}, Skipped {self.stats['total_skipped']}")

        return self.stats
