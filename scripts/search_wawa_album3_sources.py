#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查娃娃 1990 经典大碟《甜蜜梦幻》音源 (YouTube / B站)
"""
import sys
import subprocess
import requests

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 1. 探查 YouTube 是否有全专整轨或官方 Topic
cmd = [
    "yt-dlp",
    "--skip-download",
    "--print", "%(id)s | %(duration)s | %(title)s | %(channel)s",
    "ytsearch5:娃娃 金智娟 甜蜜梦幻"
]
res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
print("=== YouTube 搜索: 娃娃 甜蜜梦幻 ===")
print(res.stdout.strip())

# 2. 探查 B站
session = requests.Session()
session.trust_env = False
r = session.get("https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=%E5%A8%83%E5%A8%83+%E7%94%9C%E8%9C%9C%E6%A2%A6%E5%B9%BB", headers={'User-Agent': 'Mozilla/5.0'}).json()
print("\n=== B站搜索: 娃娃 甜蜜梦幻 ===")
for v in r.get('data', {}).get('result', [])[:4]:
    print(v.get('bvid'), v.get('title'), v.get('duration'))
