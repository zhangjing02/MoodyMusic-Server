#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查娃娃《甜蜜梦幻》(Wonderful Tonight) 10 首英文曲目官方独立 Topic
"""
import sys
import subprocess

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

songs = [
    (30635, "Crying In The Rain"),
    (30636, "Sad Movies (Always Make Me Cry)"),
    (30637, "Suspicion"),
    (30638, "Rhythm Of The Rain"),
    (30639, "Which Way You're Goin' Billy"),
    (30640, "Wonderful Tonight"),
    (30641, "Rain Rain Go Away"),
    (30642, "Chotto Matte Kudasai"),
    (30643, "Laughter In The Rain"),
    (30644, "On The Radio")
]

for sid, title in songs:
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(id)s | %(duration)s | %(title)s",
        f"ytsearch2:娃娃 {title} 甜蜜梦幻"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"=== [{sid}] {title} ===")
    for l in res.stdout.strip().split('\n'):
        if l.strip():
            print(f"   {l.strip()}")
