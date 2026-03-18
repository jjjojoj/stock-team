#!/usr/bin/env python3
"""
发送绩效汇报到飞书
"""

import sys
import os
sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/china-stock-team/scripts"))

from feishu_notifier import send_feishu_message

def main():
    # 读取绩效汇报内容
    report_file = os.path.expanduser("~/.openclaw/workspace/china-stock-team/logs/feishu_performance.txt")
    
    if not os.path.exists(report_file):
        print("❌ 绩效汇报文件不存在")
        return False
    
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 发送飞书消息
    success = send_feishu_message(
        title="📊 每日绩效汇报",
        content=content,
        level='info'
    )
    
    if success:
        print("✅ 绩效汇报已发送到飞书")
    else:
        print("❌ 绩效汇报发送失败")
    
    return success

if __name__ == "__main__":
    main()