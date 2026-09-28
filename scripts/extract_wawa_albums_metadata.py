#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
娃娃 (金智娟) 全 8 张大碟网易云元数据全量提取与对齐脚本
"""
import sys
import json
import sqlite3
import requests

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

session = requests.Session()
session.trust_env = False
headers = {'User-Agent': 'Mozilla/5.0'}

ALBUM_MAPPING = [
    {"d1_album_id": 2234, "n163_album_id": 29627, "name": "绿色的水滴", "year": "1983"},
    {"d1_album_id": 2235, "n163_album_id": 29623, "name": "开心女孩", "year": "1987"},
    {"d1_album_id": 2236, "n163_album_id": 29617, "name": "甜蜜梦幻", "year": "1990"},
    {"d1_album_id": 2237, "n163_album_id": 29615, "name": "大雨", "year": "1991"},
    {"d1_album_id": 2238, "n163_album_id": 29612, "name": "四季", "year": "1992"},
    {"d1_album_id": 2239, "n163_album_id": 29610, "name": "我对爱情不灰心", "year": "1993"},
    {"d1_album_id": 2240, "n163_album_id": 29606, "name": "随风", "year": "1995"},
    {"d1_album_id": 2241, "n163_album_id": 29603, "name": "放了爱", "year": "1996"},
]

conn = sqlite3.connect('e:/Workspace/AI-Project/MoodyMusic-Workspace/backend/database/catalog_sync.db')
cur = conn.cursor()

full_catalog = []

for al in ALBUM_MAPPING:
    d1_id = al["d1_album_id"]
    n_id = al["n163_album_id"]
    name = al["name"]
    year = al["year"]

    print(f"\n==========================================")
    print(f"📦 正在提取: 《{name}》 (D1: {d1_id}, 163: {n_id})")
    
    # 查本地 D1 歌曲列表
    cur.execute("SELECT id, title, track_index FROM songs WHERE album_id = ? ORDER BY track_index", (d1_id,))
    d1_songs = cur.fetchall()
    
    # 查网易云专辑
    url = f"https://music.163.com/api/album/{n_id}"
    resp = session.get(url, headers=headers, timeout=10).json()
    album_info = resp.get('album', {})
    cover_pic = album_info.get('picUrl')
    n163_songs = album_info.get('songs', [])
    
    print(f"   D1 歌曲数: {len(d1_songs)} | 163 歌曲数: {len(n163_songs)}")
    print(f"   封面图: {cover_pic}")
    
    matched_songs = []
    for d_song in d1_songs:
        s_id, s_title, s_idx = d_song
        # 在 163 歌曲列表中匹配
        match = None
        for ns in n163_songs:
            ns_name = ns.get('name', '').strip()
            # 简繁或去除特殊标点对比
            if (s_title.lower() in ns_name.lower() or 
                ns_name.lower() in s_title.lower() or 
                s_title.replace(' ', '') == ns_name.replace(' ', '')):
                match = ns
                break
        
        # 如果还没匹配上，根据序号尝试或者模糊
        if not match and s_idx <= len(n163_songs):
            # 看看对应位置的歌名
            candidate = n163_songs[s_idx - 1]
            match = candidate
            print(f"   ⚠️ 模糊匹配 (按序号 #{s_idx}): D1 '{s_title}' <-> 163 '{match.get('name')}'")
        elif match:
            print(f"   ✅ 精确匹配 (#{s_idx}): D1 '{s_title}' <-> 163 '{match.get('name')}' (163 ID: {match.get('id')})")
        else:
            print(f"   ❌ 未能匹配: D1 '{s_title}' (#{s_idx})")
            
        matched_songs.append({
            "d1_song_id": s_id,
            "d1_title": s_title,
            "track_index": s_idx,
            "n163_song_id": match.get('id') if match else None,
            "n163_name": match.get('name') if match else None,
            "duration_ms": match.get('duration') if match else None,
        })
        
    full_catalog.append({
        "d1_album_id": d1_id,
        "n163_album_id": n_id,
        "album_name": name,
        "year": year,
        "cover_url": cover_pic,
        "songs": matched_songs
    })

out_path = 'e:/Workspace/AI-Project/MoodyMusic-Workspace/backend/scripts/wawa_catalog_aligned.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(full_catalog, f, ensure_ascii=False, indent=2)

print(f"\n💾 元数据已保存至 {out_path}！")
