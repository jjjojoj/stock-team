#!/usr/bin/env python3
"""
完整选股工具 - 基于投资框架
添加 PB、市值、成长性等筛选条件
"""

import sys
import os

# 添加虚拟环境路径
VENV_PATH = os.path.expanduser("~/.openclaw/workspace/china-stock-team/venv/lib/python3.14/site-packages")
sys.path.insert(0, VENV_PATH)

import baostock as bs
import pandas as pd
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 股票池（有色金属 + 芯片）
STOCK_POOL = {
    "有色金属": {
        "铜": ["sh.601168", "sh.600362", "sz.000878"],
        "铝": ["sh.601600", "sz.002532", "sz.000807"],
        "锂": ["sz.002466", "sz.002460", "sz.000792"],
        "稀土": ["sh.600111", "sz.000831"],
        "其他": ["sh.600459", "sz.000758", "sh.601121"],
    },
    "芯片": {
        "制造": ["sh.688981", "sh.688396"],
        "设计": ["sz.300661"],
        "设备": ["sh.688012", "sh.688037"],
    }
}

# 实控人信息
CONTROLLERS = {
    "sh.601168": ("西部矿业", "青海国资委"),
    "sh.600362": ("江西铜业", "江西国资委"),
    "sz.000878": ("云南铜业", "央企"),
    "sh.601600": ("中国铝业", "央企"),
    "sz.002532": ("天山铝业", "民企"),
    "sz.000807": ("云铝股份", "央企"),
    "sz.002466": ("天齐锂业", "民企"),
    "sz.002460": ("赣锋锂业", "民企"),
    "sz.000792": ("盐湖股份", "青海国资委"),
    "sh.600111": ("北方稀土", "央企"),
    "sz.000831": ("五矿稀土", "央企"),
    "sh.600459": ("贵研铂业", "央企"),
    "sz.000758": ("中色股份", "央企"),
    "sh.601121": ("宝地矿业", "新疆国资委"),
    "sh.688981": ("中芯国际", "央企"),
    "sh.688396": ("华润微", "央企"),
    "sz.300661": ("圣邦股份", "民企"),
    "sh.688012": ("中微公司", "国资"),
    "sh.688037": ("芯源微", "国资"),
}

# 总股本（亿股，手动维护）
TOTAL_SHARES = {
    "sh.601168": 23.83,  # 西部矿业
    "sh.600362": 34.58,  # 江西铜业
    "sz.000878": 16.68,  # 云南铜业
    "sh.601600": 170.23, # 中国铝业
    "sz.002532": 46.59,  # 天山铝业
    "sz.000807": 34.12,  # 云铝股份
    "sz.002466": 16.44,  # 天齐锂业
    "sz.002460": 20.19,  # 赣锋锂业
    "sz.000792": 54.33,  # 盐湖股份
    "sh.600111": 36.05,  # 北方稀土
    "sz.000831": 9.82,   # 五矿稀土
    "sh.600459": 6.77,   # 贵研铂业
    "sz.000758": 19.59,  # 中色股份
    "sh.601121": 8.80,   # 宝地矿业
    "sh.688981": 19.38,  # 中芯国际（A股）
    "sh.688396": 11.89,  # 华润微
    "sz.300661": 2.10,   # 圣邦股份
    "sh.688012": 5.40,   # 中微公司
    "sh.688037": 1.26,   # 芯源微
}

def login():
    lg = bs.login()
    if lg.error_code != '0':
        raise Exception(f"登录失败: {lg.error_msg}")

def logout():
    bs.logout()

def get_stock_data(code: str) -> Optional[Dict]:
    """获取股票完整数据"""
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # 1. 获取行情数据
        rs = bs.query_history_k_data_plus(
            code,
            'date,code,open,high,low,close,volume,amount',
            start_date=start_date,
            end_date=end_date,
            frequency='d',
            adjustflag='2'
        )
        
        if rs.error_code != '0' or not rs.next():
            return None
        
        data = []
        while rs.next():
            data.append(rs.get_row_data())
        
        if not data:
            return None
        
        laverify = data[-1]
        prev = data[-2] if len(data) > 1 else laverify
        
        close_price = float(laverify[5])
        
        # 2. 计算市值
        total_shares = TOTAL_SHARES.get(code, 10)  # 默认10亿股
        market_cap = close_price * total_shares  # 亿元
        
        # 3. 获取基本面数据
        pe_ratio, pb_ratio, roe, net_profit_growth = get_fundamental_data(code)
        
        return {
            "code": code,
            "name": CONTROLLERS.get(code, ("未知", "未知"))[0],
            "controller": CONTROLLERS.get(code, ("未知", "未知"))[1],
            "date": laverify[0],
            "close": close_price,
            "volume": float(laverify[6]),
            "amount": float(laverify[7]),
            "change_pct": ((close_price - float(prev[5])) / float(prev[5]) * 100) if float(prev[5]) > 0 else 0,
            "market_cap": market_cap,
            "pe": pe_ratio,
            "pb": pb_ratio,
            "roe": roe,
            "net_profit_growth": net_profit_growth,
        }
    except Exception as e:
        return None

def get_fundamental_data(code: str) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    获取基本面数据
    返回: (PE, PB, ROE, 净利润增长率)
    """
    try:
        # 获取最近一期财报数据
        # baostock 的 query_growth_data 和 query_balance_data
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        # 获取成长能力数据
        rs_growth = bs.query_growth_data(
            code=code,
            start_date=start_date,
            end_date=end_date,
            frequency='report'
        )
        
        net_profit_growth = None
        if rs_growth.error_code == '0':
            growth_data = []
            while rs_growth.next():
                growth_data.append(rs_growth.get_row_data())
            if growth_data:
                # YOYNetProfit - 净利润同比增长率
                try:
                    net_profit_growth = float(growth_data[0][10]) if growth_data[0][10] else None
                except:
                    pass
        
        # 获取盈利能力数据
        rs_profit = bs.query_profit_data(
            code=code,
            start_date=start_date,
            end_date=end_date,
            frequency='report'
        )
        
        roe = None
        pe_ratio = None
        pb_ratio = None
        
        if rs_profit.error_code == '0':
            profit_data = []
            while rs_profit.next():
                profit_data.append(rs_profit.get_row_data())
            if profit_data:
                # roeAvg - 加权净资产收益率
                try:
                    roe = float(profit_data[0][7]) if profit_data[0][7] else None
                except:
                    pass
        
        # PE/PB 需要从估值数据获取
        # baostock 没有直接的估值接口，这里用简化计算
        # PE = 股价 / 每股收益
        # PB = 股价 / 每股净资产
        
        return pe_ratio, pb_ratio, roe, net_profit_growth
        
    except Exception as e:
        return None, None, None, None

def apply_framework_filters(stock: Dict) -> Dict:
    """
    应用投资框架筛选条件
    寒武纪八条 + Mr Dang 资源股标准
    """
    score = 0
    hard_pass = True  # 硬筛选是否通过
    reasons = []
    
    # ========== 硬筛选（必须全部满足）==========
    
    # 1. 实控人：只买央企/省国资委/市国资委
    if stock["controller"] in ["央企", "省国资委", "市国资委", "国资", "青海国资委", "江西国资委", "新疆国资委"]:
        score += 15
        reasons.append("✅ 实控人: " + stock["controller"])
    else:
        hard_pass = False
        reasons.append(f"❌ 实控人: {stock['controller']}（不符合）")
    
    # 2. 市值 < 200亿（寒武纪规则8）
    if stock["market_cap"] < 200:
        score += 15
        reasons.append(f"✅ 市值: {stock['market_cap']:.1f}亿")
    elif stock["market_cap"] < 300:
        score += 5
        reasons.append(f"⚠️ 市值: {stock['market_cap']:.1f}亿（稍大）")
    else:
        hard_pass = False
        reasons.append(f"❌ 市值: {stock['market_cap']:.1f}亿（过大）")
    
    # ========== 软筛选（加分项）==========
    
    # 3. PB 估值（Mr Dang: 15PE可接受，20PE谨慎，30PE跑路）
    # 资源股PB更重要
    if stock["pb"]:
        if stock["pb"] < 1.0:
            score += 20
            reasons.append(f"✅ PB: {stock['pb']:.2f}（破净）")
        elif stock["pb"] < 1.5:
            score += 15
            reasons.append(f"✅ PB: {stock['pb']:.2f}（低估）")
        elif stock["pb"] < 2.5:
            score += 10
            reasons.append(f"⚠️ PB: {stock['pb']:.2f}")
        elif stock["pb"] < 3.5:
            score += 5
            reasons.append(f"⚠️ PB: {stock['pb']:.2f}（偏高）")
        else:
            hard_pass = False
            reasons.append(f"❌ PB: {stock['pb']:.2f}（过高）")
    else:
        reasons.append("⚠️ PB: 数据缺失")
    
    # 4. ROE（寒武纪：业绩3-5倍增长）
    if stock["roe"]:
        if stock["roe"] > 15:
            score += 15
            reasons.append(f"✅ ROE: {stock['roe']:.1f}%")
        elif stock["roe"] > 10:
            score += 10
            reasons.append(f"⚠️ ROE: {stock['roe']:.1f}%")
        else:
            reasons.append(f"⚠️ ROE: {stock['roe']:.1f}%（偏低）")
    else:
        reasons.append("⚠️ ROE: 数据缺失")
    
    # 5. 净利润增长
    if stock["net_profit_growth"]:
        if stock["net_profit_growth"] > 300:  # 3倍
            score += 20
            reasons.append(f"✅ 净利润增长: {stock['net_profit_growth']:.1f}%（爆发）")
        elif stock["net_profit_growth"] > 50:
            score += 15
            reasons.append(f"✅ 净利润增长: {stock['net_profit_growth']:.1f}%")
        elif stock["net_profit_growth"] > 0:
            score += 5
            reasons.append(f"⚠️ 净利润增长: {stock['net_profit_growth']:.1f}%")
        else:
            reasons.append(f"⚠️ 净利润增长: {stock['net_profit_growth']:.1f}%（负增长）")
    else:
        reasons.append("⚠️ 净利润增长: 数据缺失")
    
    stock["hard_pass"] = hard_pass
    stock["score"] = score
    stock["reasons"] = reasons
    
    return stock

def scan_pool_detailed():
    """详细扫描股票池"""
    print("=" * 70)
    print("股票池深度扫描 - 基于投资框架")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    
    login()
    
    results = []
    
    for category, subcats in STOCK_POOL.items():
        print(f"\n【{category}】")
        print("=" * 70)
        
        for subcat, codes in subcats.items():
            print(f"\n  ▶ {subcat}:")
            
            for code in codes:
                data = get_stock_data(code)
                
                if not data:
                    print(f"    ❌ {code}: 数据获取失败")
                    continue
                
                # 应用筛选
                data = apply_framework_filters(data)
                
                # 显示结果
                status = "✅" if data["hard_pass"] else "❌"
                print(f"\n    {status} {data['name']} ({data['code']})")
                print(f"       收盘价: ¥{data['close']:.2f} | 涨跌: {data['change_pct']:+.2f}%")
                print(f"       市值: {data['market_cap']:.1f}亿")
                
                for reason in data["reasons"]:
                    print(f"       {reason}")
                
                print(f"       📊 综合评分: {data['score']}/100")
                
                if data["hard_pass"]:
                    results.append(data)
    
    logout()
    
    return results

def get_top_picks_detailed(n: int = 5):
    """获取最值得关注的股票（详细版）"""
    results = scan_pool_detailed()
    
    # 只保留通过硬筛选的
    passed = [s for s in results if s["hard_pass"]]
    
    # 按分数排序
    passed.sort(key=lambda x: x["score"], reverse=True)
    
    print("\n" + "=" * 70)
    print(f"🎯 最值得关注的 {min(n, len(passed))} 只股票（通过硬筛选）")
    print("=" * 70)
    
    for i, stock in enumerate(passed[:n], 1):
        print(f"\n【第 {i} 名】{stock['name']} ({stock['code']})")
        print(f"  收盘价: ¥{stock['close']:.2f} | 涨跌: {stock['change_pct']:+.2f}%")
        print(f"  市值: {stock['market_cap']:.1f}亿")
        print(f"  综合评分: {stock['score']}/100")
        print("  筛选结果:")
        for reason in stock["reasons"]:
            print(f"    {reason}")
    
    # 统计
    print("\n" + "=" * 70)
    print("📊 筛选统计")
    print("=" * 70)
    print(f"股票池总数: {len(results)}")
    print(f"通过硬筛选: {len(passed)}")
    print(f"通过率: {len(passed)/len(results)*100:.1f}%" if results else "N/A")
    
    return passed[:n]

def export_to_json(filename: str = "scan_result.json"):
    """导出扫描结果到 JSON"""
    results = scan_pool_detailed()
    
    # 转换为可序列化格式
    output = []
    for stock in results:
        output.append({
            "code": stock["code"],
            "name": stock["name"],
            "controller": stock["controller"],
            "close": stock["close"],
            "change_pct": stock["change_pct"],
            "market_cap": stock["market_cap"],
            "score": stock["score"],
            "hard_pass": stock["hard_pass"],
            "reasons": stock["reasons"],
        })
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 结果已导出到: {filename}")
    
    return output

def main():
    if len(sys.argv) < 2:
        print("用法: python3 selector_v2.py <命令> [参数]")
        print("命令:")
        print("  scan       扫描股票池（详细版）")
        print("  top [n]    显示最值得关注的 n 只股票（默认5）")
        print("  export     导出扫描结果到 JSON")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "scan":
        scan_pool_detailed()
    
    elif command == "top":
        n = int(sys.argv[2]) if len(sys.argv) >= 3 else 5
        get_top_picks_detailed(n)
    
    elif command == "export":
        export_to_json()
    
    else:
        print("未知命令")
        sys.exit(1)

if __name__ == "__main__":
    main()
