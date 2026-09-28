#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查 B站 UP主 "沉默的表示TayoQ_" 的所有投稿，看是否有娃娃的其他专辑
"""
import sys
import requests

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

session = requests.Session()
session.trust_env = False
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 查 B站搜索 “金智娟 无损” 或 “娃娃 分轨”
queries = ["金智娟 无损", "娃娃 专辑 无损", "金智娟 专辑", "娃娃 大雨 无损"]
for q in queries:
    url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={q}"
    try:
        r = session.get(url, headers=headers, timeout=6).json()
        items = r.get('data', {}).get('result', [])
        print(f"\n=== 搜索: {q} ===")
        for it in items[:6]:
            title = it.get('title', '').replace('<em class="keyword">', '').replace('</em>', '')
            print(f"  [{it.get('bvid')}] {title} (时长: {it.get('duration')})")
    except Exception as e:
        print(f"Error {q}: {e}")
