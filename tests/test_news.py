#!/usr/bin/env python3
"""测试新闻搜索适配器"""

import os
import sys
import asyncio

# 设置 API Key
os.environ['GOOGLE_API_KEY'] = 'AIzaSyAeanU5JkS5AWsMBHonJvRqRDsgt9M61n4'

# 添加项目路径
sys.path.insert(0, '/Users/joe/.openclaw/workspace/china-stock-team')

from adapters.news_adapter import NewsSearchAdapter, NewsSource

print('📰 测试 Google Gemini Search...')
print()

adapter = NewsSearchAdapter(primary=NewsSource.GOOGLE_GEMINI)
print(f'✅ 可用新闻源: {adapter.get_available_sources()}')
print()

async def test():
    print('正在搜索: 贵州茅台 最新消息...')
    news = await adapter.search_news('贵州茅台 股票 最新消息', limit=3)
    print(f'找到 {len(news)} 条新闻')
    print()
    for i, item in enumerate(news, 1):
        print(f'{i}. {item.title}')
        print(f'   来源: {item.source}')
        if item.content:
            print(f'   摘要: {item.content[:80]}...')
        print()
    return news

news = asyncio.run(test())
print('🎉 测试完成！')
