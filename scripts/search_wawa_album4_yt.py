#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查娃娃 1991 传世经典大碟《大雨》10 首曲目官方高清音源
"""
import sys
import subprocess

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

tracks = [
    (31040, "漂洋过海来看你"),
    (31041, "想逃"),
    (31042, "大雨"),
    (31043, "梦恋"),
    (31044, "在这个时间里"),
    (31045, "你不是一个好情人"),
    (31046, "GO GO 杰西"),
    (31047, "我的朋友, 我的情人"),
    (31048, "我怕冷"),
    (31049, "旅店"),
]

for sid, title in tracks:
    q = f"娃娃 金智娟 大雨 {title} 滚石"
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(id)s | %(duration)s | %(title)s | %(channel)s",
        f"ytsearch2:{q}"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"=== [{sid}] {title} ===")
    for l in res.stdout.strip().split('\n'):
        if l.strip():
            print(f"   {l.strip()}")
