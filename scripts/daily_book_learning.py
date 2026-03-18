#!/usr/bin/env python3
"""
每日炒股书籍学习系统

功能：
1. 每日学习一本炒股经典书籍
2. 提取核心知识点
3. 存入书籍知识库
4. 转化为可验证规则
5. 加入规则验证池

书籍清单（按顺序学习）：
1. 《股票作手回忆录》
2. 《聪明的投资者》
3. 《笑傲股市》
4. 《日本蜡烛图技术》
5. 《趋势交易大师》
6. 《海龟交易法则》
7. 《股市趋势技术分析》
8. 《彼得·林奇的成功投资》
9. 《巴菲特致股东的信》
10. 《投资最重要的事》
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LEARNING_DIR = PROJECT_ROOT / "learning"
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

# 书籍清单
BOOK_LIST = [
    {
        "id": "book_001",
        "title": "股票作手回忆录",
        "author": "埃德温·勒菲弗",
        "key_points": [
            {
                "content": "价格总是沿最小阻力线运动",
                "category": "趋势",
                "testable_rule": "突破 20 日高点后，价格继续上涨概率>55%"
            },
            {
                "content": "关键点突破后加仓",
                "category": "仓位管理",
                "testable_rule": "突破关键点后加仓，盈亏比>1.5"
            },
            {
                "content": "不要与趋势对抗",
                "category": "趋势",
                "testable_rule": "顺势交易成功率>逆势交易成功率"
            },
            {
                "content": "亏损时不要加仓",
                "category": "风控",
                "testable_rule": "亏损加仓策略最终亏损>不亏损加仓"
            },
            {
                "content": "耐心等待关键点",
                "category": "入场",
                "testable_rule": "等待关键点突破比提前入场收益更高"
            }
        ]
    },
    {
        "id": "book_002",
        "title": "聪明的投资者",
        "author": "本杰明·格雷厄姆",
        "key_points": [
            {
                "content": "安全边际原则",
                "category": "估值",
                "testable_rule": "PB<1 的股票长期收益>市场平均"
            },
            {
                "content": "市场先生理论",
                "category": "心态",
                "testable_rule": "逆向投资策略在波动市场中收益更高"
            },
            {
                "content": "分散投资",
                "category": "仓位管理",
                "testable_rule": "持有 10-20 只股票风险收益比最优"
            }
        ]
    },
    {
        "id": "book_003",
        "title": "笑傲股市",
        "author": "威廉·欧奈尔",
        "key_points": [
            {
                "content": "CAN SLIM 选股法",
                "category": "选股",
                "testable_rule": "符合 CAN SLIM 标准的股票年化收益>20%"
            },
            {
                "content": "杯柄形态突破",
                "category": "技术形态",
                "testable_rule": "杯柄形态突破后 5 日上涨概率>60%"
            },
            {
                "content": "止损 8% 原则",
                "category": "风控",
                "testable_rule": "8% 止损策略最大回撤<15%"
            }
        ]
    }
    # 更多书籍后续添加
]


class BookLearning:
    """书籍学习系统"""
    
    def __init__(self):
        self.book_db_file = LEARNING_DIR / "book_knowledge.json"
        self.validation_pool_file = LEARNING_DIR / "rule_validation_pool.json"
        self.progress_file = LEARNING_DIR / "book_learning_progress.json"
        
        self._ensure_dirs()
        self._load_data()
    
    def _ensure_dirs(self):
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load_data(self):
        """加载数据"""
        # 书籍知识库
        if self.book_db_file.exists():
            with open(self.book_db_file, 'r', encoding='utf-8') as f:
                self.book_db = json.load(f)
        else:
            self.book_db = {}
        
        # 规则验证池
        if self.validation_pool_file.exists():
            with open(self.validation_pool_file, 'r', encoding='utf-8') as f:
                self.validation_pool = json.load(f)
        else:
            self.validation_pool = {}
        
        # 学习进度
        if self.progress_file.exists():
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                self.progress = json.load(f)
        else:
            self.progress = {
                "current_book_index": 0,
                "books_completed": [],
                "last_learning_date": None
            }
    
    def _save_data(self):
        """保存数据"""
        with open(self.book_db_file, 'w', encoding='utf-8') as f:
            json.dump(self.book_db, f, ensure_ascii=False, indent=2)
        
        with open(self.validation_pool_file, 'w', encoding='utf-8') as f:
            json.dump(self.validation_pool, f, ensure_ascii=False, indent=2)
        
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, ensure_ascii=False, indent=2)
    
    def get_today_book(self) -> dict:
        """获取今日要学习的书籍"""
        index = self.progress["current_book_index"]
        
        # 如果已完成所有书籍，循环重新开始
        if index >= len(BOOK_LIST):
            index = 0
            self.progress["current_book_index"] = 0
            self.progress["books_completed"] = []
        
        return BOOK_LIST[index]
    
    def learn_book(self, book: dict) -> dict:
        """
        学习一本书
        
        返回：
        {
            "book_id": "...",
            "points_learned": 5,
            "rules_created": 2
        }
        """
        book_id = book["id"]
        
        # 检查是否已学过
        if book_id in self.book_db:
            return {
                "book_id": book_id,
                "points_learned": 0,
                "rules_created": 0,
                "message": "已学习过"
            }
        
        # 存入书籍知识库
        self.book_db[book_id] = {
            "title": book["title"],
            "author": book["author"],
            "learned_date": datetime.now().strftime("%Y-%m-%d"),
            "key_points": [
                {
                    "id": f"{book_id}.point_{i+1:03d}",
                    "content": point["content"],
                    "category": point["category"],
                    "testable_rule": point["testable_rule"],
                    "confidence": 0.5,  # 初始置信度（书本知识，未经验证）
                    "verified": False,
                    "created_at": datetime.now().isoformat()
                }
                for i, point in enumerate(book["key_points"])
            ]
        }
        
        # 选择 1-2 个知识点转化为验证规则
        rules_created = 0
        for i, point in enumerate(book["key_points"][:2]):  # 前 2 个
            rule_id = f"rule_{book_id}_{i+1}"
            
            self.validation_pool[rule_id] = {
                "source": f"{book_id}.point_{i+1:03d}",
                "source_book": book["title"],
                "rule": point["content"],
                "testable_form": point["testable_rule"],
                "category": point["category"],
                
                # 验证数据（初始）
                "backtest": {
                    "samples": 0,
                    "success_rate": 0.0,
                    "avg_profit": 0.0,
                    "avg_loss": 0.0,
                    "profit_factor": 0.0
                },
                "live_test": {
                    "samples": 0,
                    "success_rate": 0.0,
                    "started_at": datetime.now().isoformat()
                },
                
                # 状态
                "status": "validating",  # validating/proven/rejected
                "confidence": 0.5,  # 初始置信度
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            rules_created += 1
        
        # 更新进度
        self.progress["books_completed"].append(book_id)
        self.progress["current_book_index"] += 1
        self.progress["last_learning_date"] = datetime.now().strftime("%Y-%m-%d")
        
        return {
            "book_id": book_id,
            "title": book["title"],
            "points_learned": len(book["key_points"]),
            "rules_created": rules_created
        }
    
    def run(self) -> dict:
        """运行每日学习"""
        print("=" * 60)
        print(f"📚 每日炒股书籍学习 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        
        # 获取今日书籍
        book = self.get_today_book()
        print(f"\n📖 今日学习：《{book['title']}》- {book['author']}")
        
        # 学习
        result = self.learn_book(book)
        
        if result["points_learned"] > 0:
            print(f"\n✅ 学习完成:")
            print(f"   知识点：{result['points_learned']}个")
            print(f"   转化验证规则：{result['rules_created']}个")
            
            # 打印知识点
            print(f"\n📝 核心观点:")
            for point in self.book_db[result["book_id"]]["key_points"]:
                print(f"   • {point['content']} ({point['category']})")
            
            # 打印验证规则
            print(f"\n🧪 加入验证池:")
            for rule_id, rule in list(self.validation_pool.items())[-result['rules_created']:]:
                print(f"   • {rule['rule']}")
                print(f"     验证形式：{rule['testable_form']}")
        else:
            print(f"\n⚠️  {result['message']}")
        
        # 保存
        self._save_data()
        
        # 学习进度
        print(f"\n📊 学习进度:")
        print(f"   已学书籍：{len(self.progress['books_completed'])}/{len(BOOK_LIST)}")
        print(f"   验证池规则：{len(self.validation_pool)}条")
        
        # 下一本书
        next_index = self.progress["current_book_index"]
        if next_index < len(BOOK_LIST):
            next_book = BOOK_LIST[next_index]
            print(f"   明日预告：《{next_book['title']}》")
        else:
            print(f"   🎉 所有书籍已学完，明日开始第二轮！")
        
        print("\n" + "=" * 60)
        
        return result


def main():
    """主函数"""
    learning = BookLearning()
    learning.run()


if __name__ == "__main__":
    main()
