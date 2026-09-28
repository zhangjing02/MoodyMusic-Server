#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查娃娃 1996 收官大碟《放了爱》(10首曲目) 音源
"""
import sys
import subprocess

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

songs = [
    (31083, "放了爱"),
    (31084, "七情六欲"),
    (31085, "我是飞鸟你是天"),
    (31086, "算了"),
    (31087, "呼吸"),
    (31088, "祈祷"),
    (31089, "真爱宣言"),
    (31090, "说清楚"),
    (31091, "嫉妒"),
    (31092, "坦白"),
]

for sid, title in songs:
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(id)s | %(duration)s | %(title)s | %(channel)s",
        f"ytsearch2:娃娃 金智娟 放了爱 {title}"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"=== [{sid}] {title} ===")
    for l in res.stdout.strip().split('\n'):
        if l.strip():
            print(f"   {l.strip()}")
