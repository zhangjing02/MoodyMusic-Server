#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

queries = [
    ('动力火车 逆流 Topic', 25796, '逆流'),
    ('动力火车 我这个你不爱的人 Topic', 25795, '我这个你不爱的人'),
    ('王菲 花事了 Topic', 24170, '花事了'),
    ('王菲 MV Topic', 24168, 'MV'),
    ('古巨基 顺风车 Topic', 7480, '顺风车'),
    ('阿杜 没什么好怕 Topic', 59, '没什么好怕')
]

for q, sid, target_title in queries:
    cmd = [
        'yt-dlp', '--proxy', 'http://127.0.0.1:10090',
        '--js-runtimes', 'node',
        '--dump-json', '--no-playlist', f'ytsearch2:{q}'
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25, encoding='utf-8', errors='ignore')
        found = False
        for line in proc.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                v = json.loads(line)
                title = v.get('title', '')
                channel = v.get('channel', '') or v.get('uploader', '')
                dur = v.get('duration', 0)
                vid = v.get('id', '')
                print(f"SID: {sid:<5} | Target: {target_title:<10} | Found: 《{title}》 | Ch: {channel} | Dur: {dur}s | vid: {vid}")
                found = True
            except Exception:
                pass
        if not found:
            print(f"SID: {sid:<5} | Target: {target_title:<10} | NOT FOUND")
    except Exception as e:
        print(f"SID: {sid:<5} | Error: {e}")
