#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查娃娃《大雨》专辑官方音源
"""
import subprocess
import json

songs = [
    "漂洋过海来看你",
    "想逃",
    "大雨",
    "梦恋",
    "在这个时间里",
    "你不是一个好情人",
    "GO GO 杰西",
    "我的朋友, 我的情人",
    "我怕冷",
    "旅店"
]

for s in songs:
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(id)s | %(title)s | %(channel)s",
        f"ytsearch1:娃娃 金智娟 {s} 滚石 官方"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"{s}: {res.stdout.strip()}")
