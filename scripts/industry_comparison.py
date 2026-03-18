#!/usr/bin/env python3
"""
同行业对比分析工具
"""

import json
import urllib.request
from datetime import datetime
import os

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")

# 行业分组
INDUSTRY_GROUPS = {
    "铂族金属": ["sh.600459"],  # 贵研铂业
    "稀土": ["sh.600111", "sz.000831"],  # 北方稀土、五矿稀土
    "铁矿": ["sh.601121"],  # 宝地矿业
    "黄金": ["sh.600547", "sh.601899", "sz.002155"],  # 山东黄金、紫金矿业、湖南黄金
    "铜": ["sh.600362"],  # 江西铜业
    "化工": ["sz.002092"],  # 中泰化学
}

# 行业指数代码
INDUSTRY_INDICES = {
    "有色金属": "sh000819",
    "黄金": "sh931076",
    "稀土": "sh931077",
}

def get_realtime_data(codes):
    """批量获取实时股价"""
    results = {}
    
    try:
        # 转换代码格式
        code_list = []
        for code in codes:
            code_clean = code.replace(".", "")
            code_list.append(code_clean)
        
        url = f"http://qt.gtimg.cn/q={','.join(code_list)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            text = response.read().decode("gbk")
            
        for line in text.strip().split('\n'):
            if '~' not in line:
                continue
            
            parts = line.split('~')
            if len(parts) < 32:
                continue
            
            code = parts[2]
            results[code] = {
                'name': parts[1],
                'price': float(parts[3]),
                'yesterday': float(parts[4]),
                'high': float(parts[33]) if len(parts) > 33 else float(parts[3]),
                'low': float(parts[34]) if len(parts) > 34 else float(parts[3]),
                'volume': int(parts[6]) if parts[6].isdigit() else 0,
                'amount': float(parts[37]) if len(parts) > 37 and parts[37] else 0,
                'change_pct': float(parts[31]) if parts[31] and parts[31] != '-' else 0,
                'pe': float(parts[39]) if len(parts) > 39 and parts[39] and parts[39] != '-' else 0,
                'pb': float(parts[46]) if len(parts) > 46 and parts[46] and parts[46] != '-' else 0,
                'market_cap': float(parts[45]) if len(parts) > 45 and parts[45] else 0,
            }
    
    except Exception as e:
        print(f"获取实时数据失败: {e}")
    
    return results

def compare_industry(industry_name, stock_codes):
    """对比同行业股票"""
    all_codes = list(set(stock_codes))
    
    # 获取实时数据
    data = get_realtime_data(all_codes)
    
    if not data:
        return None
    
    # 整理对比数据
    comparison = {
        'industry': industry_name,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'stocks': []
    }
    
    for code in stock_codes:
        code_clean = code.split(".")[1]
        if code_clean in data:
            stock_data = data[code_clean]
            
            comparison['stocks'].append({
                'code': code,
                'name': stock_data['name'],
                'price': stock_data['price'],
                'change_pct': stock_data['change_pct'],
                'high': stock_data['high'],
                'low': stock_data['low'],
                'volume': stock_data['volume'],
                'amount': stock_data['amount'],
                'pe': stock_data['pe'],
                'pb': stock_data['pb'],
                'market_cap': stock_data['market_cap'],
            })
    
    # 计算行业平均
    if comparison['stocks']:
        avg_change = sum(s['change_pct'] for s in comparison['stocks']) / len(comparison['stocks'])
        avg_pe = sum(s['pe'] for s in comparison['stocks'] if s['pe'] > 0) / max(1, sum(1 for s in comparison['stocks'] if s['pe'] > 0))
        avg_pb = sum(s['pb'] for s in comparison['stocks'] if s['pb'] > 0) / max(1, sum(1 for s in comparison['stocks'] if s['pb'] > 0))
        
        comparison['avg_change_pct'] = round(avg_change, 2)
        comparison['avg_pe'] = round(avg_pe, 2)
        comparison['avg_pb'] = round(avg_pb, 2)
    
    return comparison

def analyze_all_industries():
    """分析所有行业"""
    results = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'industries': {}
    }
    
    for industry, codes in INDUSTRY_GROUPS.items():
        comparison = compare_industry(industry, codes)
        if comparison:
            results['industries'][industry] = comparison
    
    # 保存结果
    output_path = os.path.join(PROJECT_ROOT, "data", "industry_comparison.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 行业对比分析已保存: {output_path}")
    return results

def get_industry_ranking():
    """获取行业涨跌幅排名"""
    all_codes = []
    for codes in INDUSTRY_GROUPS.values():
        all_codes.extend(codes)
    
    data = get_realtime_data(all_codes)
    
    # 按行业统计
    industry_stats = {}
    for industry, codes in INDUSTRY_GROUPS.items():
        industry_changes = []
        for code in codes:
            code_clean = code.split(".")[1]
            if code_clean in data:
                industry_changes.append(data[code_clean]['change_pct'])
        
        if industry_changes:
            industry_stats[industry] = {
                'avg_change': round(sum(industry_changes) / len(industry_changes), 2),
                'stock_count': len(industry_changes),
                'best_stock': None,
                'worst_stock': None,
            }
    
    # 找出最佳/最差股票
    for industry, codes in INDUSTRY_GROUPS.items():
        best_change = -999
        worst_change = 999
        best_stock = None
        worst_stock = None
        
        for code in codes:
            code_clean = code.split(".")[1]
            if code_clean in data:
                change = data[code_clean]['change_pct']
                if change > best_change:
                    best_change = change
                    best_stock = {
                        'code': code,
                        'name': data[code_clean]['name'],
                        'change_pct': change
                    }
                if change < worst_change:
                    worst_change = change
                    worst_stock = {
                        'code': code,
                        'name': data[code_clean]['name'],
                        'change_pct': change
                    }
        
        if industry in industry_stats:
            industry_stats[industry]['best_stock'] = best_stock
            industry_stats[industry]['worst_stock'] = worst_stock
    
    # 按涨跌幅排序
    sorted_industries = sorted(
        industry_stats.items(),
        key=lambda x: x[1]['avg_change'],
        reverse=True
    )
    
    return {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ranking': [
            {
                'industry': ind,
                **stats
            }
            for ind, stats in sorted_industries
        ]
    }

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'ranking':
            result = get_industry_ranking()
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif sys.argv[1] == 'analyze':
            result = analyze_all_industries()
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 分析特定行业
            industry = sys.argv[1]
            codes = INDUSTRY_GROUPS.get(industry, [])
            if codes:
                result = compare_industry(industry, codes)
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"未知行业: {industry}")
    else:
        analyze_all_industries()
