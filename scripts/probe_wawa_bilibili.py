#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查 B站上娃娃 (金智娟) 8 张专辑的高清/无损抓轨视频源
"""
import sys
import re
import requests
import json

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

session = requests.Session()
session.trust_env = False
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

albums = [
    "绿色的水滴",
    "开心女孩 娃娃",
    "甜蜜梦幻 娃娃",
    "大雨 娃娃 专辑",
    "四季 娃娃 专辑",
    "我对爱情不灰心 娃娃",
    "随风 娃娃 专辑",
    "放了爱 娃娃 专辑"
]

for alb in albums:
    url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={alb}"
    try:
        r = session.get(url, headers=headers, timeout=6).json()
        results = r.get('data', {}).get('result', [])
        print(f"\n==========================================")
        print(f"🔍 搜索: {alb}")
        for v in results[:4]:
            title_clean = re.sub(r'<[^>]+>', '', v.get('title', ''))
            bvid = v.get('bvid')
            author = v.get('author')
            duration = v.get('duration')
            print(f"  [{bvid}] {title_clean} (UP: {author}, 时长: {duration})")
    except Exception as e:
        print(f"Error {alb}: {e}")
