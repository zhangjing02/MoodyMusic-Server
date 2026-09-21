#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断 Twins 专辑与曲目点亮现状
"""
import requests
import json
from urllib3.util import connection

_orig = connection.create_connection
def patched(address, *args, **kwargs):
    if address[0] == "m-api.changgepd.ccwu.cc":
        return _orig(("104.21.21.164", address[1]), *args, **kwargs)
    return _orig(address, *args, **kwargs)
connection.create_connection = patched

D1_URL = "https://m-api.changgepd.ccwu.cc/api/songs?artist=Twins"
r = requests.get(D1_URL, timeout=15)
data = r.json().get("data", [])

if not data:
    print("未找到 Twins 数据！")
    exit(0)

art = data[0]
albums = art.get("albums", [])

total_songs = 0
lit_songs = 0
unlit_songs = []

art_name = art.get('name')
print("=" * 80)
print(f"🎵 歌手: {art_name} (共 {len(albums)} 张专辑)")
print("=" * 80)
print(f"{'专辑名':<25} | {'曲目总数':>8} | {'已点亮':>6} | {'未点亮':>6} | {'点亮比例':>8}")
print("-" * 80)

for alb in albums:
    alb_title = alb.get("title", "未知专辑")
    songs = alb.get("songs", [])
    alb_total = len(songs)
    alb_lit = sum(1 for s in songs if s.get("path"))
    alb_unlit = alb_total - alb_lit
    
    total_songs += alb_total
    lit_songs += alb_lit
    
    pct = (alb_lit / alb_total * 100) if alb_total > 0 else 0
    flag = "✅ 100%" if alb_unlit == 0 else f"⚠️ 缺 {alb_unlit} 首"
    print(f"{alb_title[:23]:<25} | {alb_total:>8} | {alb_lit:>6} | {alb_unlit:>6} | {pct:>7.1f}% ({flag})")
    
    for s in songs:
        if not s.get("path"):
            unlit_songs.append({
                "album": alb_title,
                "title": s.get("title"),
                "id": s.get("id"),
                "track": s.get("TrackIndex")
            })

print("=" * 80)
pct_total = (lit_songs / total_songs * 100) if total_songs > 0 else 0
print(f"全集汇总: 共 {len(albums)} 张专辑 | {total_songs} 首歌曲 | 已点亮: {lit_songs} 首 ({pct_total:.1f}%) | 待点亮: {len(unlit_songs)} 首")
print(f"\n未点亮曲目清单 (全部 {len(unlit_songs)} 首):")
for idx, u in enumerate(unlit_songs, 1):
    print(f"  [{idx:02d}] 《{u['album']}》- 《{u['title']}》 (ID: {u['id']}, Track: {u['track']})")
