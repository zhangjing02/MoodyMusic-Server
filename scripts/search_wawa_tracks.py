#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
娃娃 (金智娟) 歌曲网易云 ID 与音源探查脚本
"""
import sys
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

tracks = [
    ("绿色的水滴", "绿色的水滴"),
    ("飞鸟", "绿色的水滴"),
    ("从来都没有", "绿色的水滴"),
    ("和你在一起", "绿色的水滴"),
    ("该不该说", "绿色的水滴"),
    ("表白", "绿色的水滴"),
    ("Have Some Fun", "绿色的水滴"),
    ("苏里、宝贝", "绿色的水滴"),
    ("Music Box", "绿色的水滴"),
    ("再见", "绿色的水滴"),
]

for title, album in tracks:
    url = f"https://music.163.com/api/search/get/web?csrf_token=hlpretag=&hlposttag=&s=娃娃 {title}&type=1&offset=0&total=true&limit=5"
    try:
        r = session.get(url, headers=headers, timeout=6)
        data = r.json()
        songs = data.get('result', {}).get('songs', [])
        print(f"=== 查询: 娃娃 - {title} ===")
        found = False
        for s in songs:
            al_name = s.get('album', {}).get('name', '')
            ar_names = '/'.join([a['name'] for a in s.get('artists', [])])
            if '娃娃' in ar_names or '金智娟' in ar_names:
                print(f"   [163 ID: {s['id']}] {s['name']} | 歌手: {ar_names} | 专辑: {al_name}")
                found = True
        if not found and songs:
            # print top 2 anyway
            for s in songs[:2]:
                al_name = s.get('album', {}).get('name', '')
                ar_names = '/'.join([a['name'] for a in s.get('artists', [])])
                print(f"   (候选) [163 ID: {s['id']}] {s['name']} | 歌手: {ar_names} | 专辑: {al_name}")
    except Exception as e:
        print(f"Error querying {title}: {e}")
