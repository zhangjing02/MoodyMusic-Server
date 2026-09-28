#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查娃娃 1983 经典大碟《绿色的水滴》YouTube 音源
"""
import sys
import subprocess
import json

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

songs = [
    (30615, "绿色的水滴", 298635),
    (30616, "飞鸟", 298636),
    (30617, "从来都没有", 298637),
    (30618, "和你在一起", 298639),
    (30619, "该不该说", 298641),
    (30620, "表白", 298643),
    (30621, "ㄆㄧㄌㄧˋㄨˇHave Some Fun", 298645),
    (30622, "苏里、宝贝", 298647),
    (30623, "Music Box", 298649),
    (30624, "再见", 298651)
]

print("=== 开始检索《绿色的水滴》全专 YouTube 音源 ===")
results = []
for sid, title, n163 in songs:
    # 针对不同歌名微调搜索词
    search_q = f"娃娃 金智娟 {title}"
    if "Have Some Fun" in title:
        search_q = "娃娃 金智娟 Have Some Fun"
    elif "Music Box" in title:
        search_q = "娃娃 金智娟 绿色的水滴 Music Box"
        
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(id)s\t%(duration)s\t%(title)s\t%(channel)s",
        f"ytsearch3:{search_q}"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = res.stdout.strip().split('\n')
    print(f"\n🎵 [{sid}] {title}:")
    for l in lines:
        if l.strip():
            print(f"   {l.strip()}")
