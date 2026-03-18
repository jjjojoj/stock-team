"""
股票团队知识库
使用向量存储管理学习内容、历史决策、规则等
"""

import os
import sys
import json
import pickle
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# 添加虚拟环境路径
VENV_PATH = os.path.expanduser("~/.openclaw/workspace/china-stock-team/venv/lib/python3.14/site-packages")
sys.path.insert(0, VENV_PATH)

# 尝试导入 numpy
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge" / "vectors"
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class KnowledgeItem:
    """知识条目"""
    id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class KnowledgeBase:
    """
    股票团队知识库
    
    功能：
    - 存储学习内容
    - 存储历史决策
    - 存储交易规则
    - 语义搜索（简单实现，基于关键词匹配）
    - 向量搜索（如果有 numpy）
    """
    
    def __init__(self, name: str = "stock_team"):
        self.name = name
        self.db_path = KNOWLEDGE_DIR / f"{name}.json"
        self.vectors_path = KNOWLEDGE_DIR / f"{name}_vectors.pkl"
        
        # 加载数据
        self.items: Dict[str, KnowledgeItem] = {}
        self._load()
    
    def _load(self):
        """加载知识库"""
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item_id, item_data in data.items():
                        self.items[item_id] = KnowledgeItem(**item_data)
            except Exception as e:
                print(f"加载知识库失败: {e}")
                self.items = {}
    
    def _save(self):
        """保存知识库"""
        try:
            data = {k: asdict(v) for k, v in self.items.items()}
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存知识库失败: {e}")
    
    def _generate_id(self, content: str) -> str:
        """生成唯一 ID"""
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _simple_embedding(self, text: str) -> List[float]:
        """
        简单的文本嵌入（基于字符频率）
        如果有 numpy，可以使用更高级的嵌入
        """
        if not HAS_NUMPY:
            return []
        
        # 简单的词袋模型
        # 使用字符和常见词的频率作为特征
        features = [0.0] * 256
        
        for char in text.lower():
            code = ord(char) % 256
            features[code] += 1.0
        
        # 归一化
        total = sum(features)
        if total > 0:
            features = [f / total for f in features]
        
        return features
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        if not HAS_NUMPY or not a or not b:
            return 0.0
        
        a_arr = np.array(a)
        b_arr = np.array(b)
        
        dot = np.dot(a_arr, b_arr)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)
    
    def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        generate_embedding: bool = True
    ) -> str:
        """
        添加知识条目
        
        Args:
            content: 知识内容
            metadata: 元数据（如类型、来源、相关股票等）
            generate_embedding: 是否生成嵌入向量
        
        Returns:
            条目 ID
        """
        item_id = self._generate_id(content)
        
        # 检查是否已存在
        if item_id in self.items:
            return item_id
        
        # 生成嵌入
        embedding = None
        if generate_embedding and HAS_NUMPY:
            embedding = self._simple_embedding(content)
        
        # 创建条目
        item = KnowledgeItem(
            id=item_id,
            content=content,
            metadata=metadata or {},
            embedding=embedding,
        )
        
        self.items[item_id] = item
        self._save()
        
        return item_id
    
    def get(self, item_id: str) -> Optional[KnowledgeItem]:
        """获取知识条目"""
        return self.items.get(item_id)
    
    def delete(self, item_id: str) -> bool:
        """删除知识条目"""
        if item_id in self.items:
            del self.items[item_id]
            self._save()
            return True
        return False
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[KnowledgeItem, float]]:
        """
        搜索知识库
        
        Args:
            query: 查询文本
            top_k: 返回数量
            metadata_filter: 元数据过滤条件
        
        Returns:
            [(知识条目, 相似度分数)]
        """
        results = []
        
        # 生成查询嵌入
        query_embedding = self._simple_embedding(query) if HAS_NUMPY else []
        
        for item in self.items.values():
            # 元数据过滤
            if metadata_filter:
                match = all(
                    item.metadata.get(k) == v
                    for k, v in metadata_filter.items()
                )
                if not match:
                    continue
            
            # 计算相似度
            if query_embedding and item.embedding:
                score = self._cosine_similarity(query_embedding, item.embedding)
            else:
                # 降级到关键词匹配
                score = self._keyword_match_score(query, item.content)
            
            results.append((item, score))
        
        # 排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:top_k]
    
    def _keyword_match_score(self, query: str, content: str) -> float:
        """关键词匹配分数"""
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        
        if not query_words:
            return 0.0
        
        common = query_words & content_words
        return len(common) / len(query_words)
    
    def search_by_type(
        self,
        query: str,
        knowledge_type: str,
        top_k: int = 5
    ) -> List[Tuple[KnowledgeItem, float]]:
        """按类型搜索"""
        return self.search(
            query,
            top_k=top_k,
            metadata_filter={"type": knowledge_type}
        )
    
    def get_all_by_type(self, knowledge_type: str) -> List[KnowledgeItem]:
        """获取某类型的所有知识"""
        return [
            item for item in self.items.values()
            if item.metadata.get("type") == knowledge_type
        ]
    
    def count(self) -> int:
        """获取知识条目数量"""
        return len(self.items)
    
    def clear(self):
        """清空知识库"""
        self.items = {}
        self._save()


# ============================================================
# 股票团队专用知识库
# ============================================================

class StockTeamKnowledgeBase(KnowledgeBase):
    """股票团队专用知识库"""
    
    # 知识类型
    LESSON = "lesson"           # 教训
    RULE = "rule"               # 规则
    DECISION = "decision"       # 决策
    PREDICTION = "prediction"   # 预测
    ANALYSIS = "analysis"       # 分析
    NEWS_IMPACT = "news_impact" # 新闻影响
    
    def add_lesson(
        self,
        content: str,
        stock: Optional[str] = None,
        date: Optional[str] = None,
        result: Optional[str] = None  # success/failure
    ) -> str:
        """添加教训"""
        return self.add(
            content,
            metadata={
                "type": self.LESSON,
                "stock": stock,
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "result": result,
            }
        )
    
    def add_rule(
        self,
        rule_name: str,
        rule_content: str,
        category: str = "general",
        priority: int = 5
    ) -> str:
        """添加规则"""
        return self.add(
            f"{rule_name}: {rule_content}",
            metadata={
                "type": self.RULE,
                "name": rule_name,
                "category": category,
                "priority": priority,
                "success_count": 0,
                "failure_count": 0,
            }
        )
    
    def add_decision(
        self,
        stock: str,
        action: str,  # buy/sell/hold
        reason: str,
        price: float,
        quantity: int
    ) -> str:
        """添加决策记录"""
        return self.add(
            f"{stock} {action}: {reason}",
            metadata={
                "type": self.DECISION,
                "stock": stock,
                "action": action,
                "reason": reason,
                "price": price,
                "quantity": quantity,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )
    
    def add_prediction(
        self,
        stock: str,
        direction: str,  # up/down/neutral
        confidence: float,
        target_price: Optional[float] = None,
        time_horizon: str = "1d",  # 1d/1w/1m
        rationale: str = ""
    ) -> str:
        """添加预测"""
        return self.add(
            f"{stock} 预测{direction} (置信度: {confidence}%)",
            metadata={
                "type": self.PREDICTION,
                "stock": stock,
                "direction": direction,
                "confidence": confidence,
                "target_price": target_price,
                "time_horizon": time_horizon,
                "rationale": rationale,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "verified": False,
                "correct": None,
            }
        )
    
    def search_lessons(self, query: str, top_k: int = 5) -> List[Tuple[KnowledgeItem, float]]:
        """搜索教训"""
        return self.search_by_type(query, self.LESSON, top_k)
    
    def search_rules(self, query: str, top_k: int = 5) -> List[Tuple[KnowledgeItem, float]]:
        """搜索规则"""
        return self.search_by_type(query, self.RULE, top_k)
    
    def search_similar_situations(self, query: str, top_k: int = 5) -> List[Tuple[KnowledgeItem, float]]:
        """搜索相似情况（包括教训、决策、分析）"""
        # 搜索多种类型
        results = []
        
        for type_name in [self.LESSON, self.DECISION, self.ANALYSIS]:
            type_results = self.search_by_type(query, type_name, top_k)
            results.extend(type_results)
        
        # 重新排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:top_k]
    
    def get_all_rules(self) -> List[KnowledgeItem]:
        """获取所有规则"""
        return self.get_all_by_type(self.RULE)
    
    def get_recent_predictions(self, days: int = 7) -> List[KnowledgeItem]:
        """获取最近的预测"""
        cutoff = datetime.now().strftime("%Y-%m-%d")
        predictions = self.get_all_by_type(self.PREDICTION)
        
        # 简单过滤（实际应该解析日期）
        return predictions[:20]  # 返回最近 20 条


# ============================================================
# 全局知识库实例
# ============================================================

_kb_instance: Optional[StockTeamKnowledgeBase] = None


def get_knowledge_base() -> StockTeamKnowledgeBase:
    """获取全局知识库实例"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = StockTeamKnowledgeBase("stock_team")
    return _kb_instance
