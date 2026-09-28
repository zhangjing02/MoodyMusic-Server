#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检索娃娃 1987 经典大碟《开心女孩》YouTube / Bilibili 音源
"""
import sys
import subprocess
import json

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

tracks = [
    (30625, "千年的神话"),
    (30626, "只是啊!只是"),
    (30627, "PAINT YOUR PICTURE"),
    (30628, "新桃太郎电影音乐"),
    (30629, "为我停留"),
    (30630, "有谁能夠"),
    (30631, "情不自禁"),
    (30632, "距离"),
    (30633, "开心女孩"),
    (30634, "爱情哲学"),
]

for sid, title in tracks:
    q = f"娃娃 金智娟 开心女孩 {title}"
    if title == "开心女孩":
        q = "娃娃 金智娟 Happy Girl 开心女孩 官方"
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(id)s | %(duration)s | %(title)s | %(channel)s",
        f"ytsearch2:{q}"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"=== [{sid}] {title} ===")
    for line in res.stdout.strip().split('\n'):
        if line.strip():
            print(f"   {line.strip()}")
