#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查娃娃 (金智娟) 第一专《绿色的水滴》与第四专《大雨》YouTube 官方/高品质音源
"""
import sys
import json
import subprocess

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

test_songs = [
    ("娃娃", "绿色的水滴"),
    ("娃娃", "飞鸟"),
    ("娃娃", "漂洋过海来看你"),
    ("娃娃", "大雨"),
    ("娃娃", "春之祭"),
    ("娃娃", "如今才是唯一"),
    ("娃娃", "后悔"),
    ("娃娃", "放了爱"),
]

for ar, title in test_songs:
    query = f"ytsearch3:{ar} {title} 滚石 官方"
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(id)s | %(title)s | %(duration)s | %(channel)s",
        query
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        print(f"=== 搜索: {ar} - {title} ===")
        print(res.stdout.strip())
    except Exception as e:
        print(f"Error {ar} {title}: {e}")
