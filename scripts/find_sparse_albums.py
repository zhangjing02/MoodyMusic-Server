#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全库稀稀拉拉残缺专辑深度扫描
找出知名歌手中只差 1~4 首就能达成 100% 满专的经典大碟
"""

import requests
import json

url = "https://m-api.changgepd.ccwu.cc/api/songs"
print("正在从边缘 API 获取最新全库曲目状态...")
try:
    r = requests.get(url, timeout=30)
    data = r.json().get("data", [])
except Exception as e:
    print(f"Direct failed: {e}, using local proxy...")
    r = requests.get(url, proxies={"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}, timeout=30)
    data = r.json().get("data", [])

print(f"全库歌手总数: {len(data)}")

def is_song_lit(s):
    p = s.get("path")
    return p is not None and str(p).strip() != "" and str(p).strip().lower() != "none"

sparse_summary = []

for art in data:
    art_name = art.get("name")
    albums = art.get("albums", [])
    
    art_sparse_albums = []
    art_tot = 0
    art_lit = 0
    
    for alb in albums:
        alb_title = alb.get("title")
        songs = alb.get("songs", [])
        alb_tot = len(songs)
        if alb_tot == 0:
            continue
        alb_lit = sum(1 for s in songs if is_song_lit(s))
        alb_unlit = alb_tot - alb_lit
        art_tot += alb_tot
        art_lit += alb_lit
        
        # 典型稀稀拉拉定义:
        # 1. 专辑总曲目 >= 3
        # 2. 已经点亮 >= 1 首
        # 3. 欠缺 1 到 4 首 (或者未点亮比例 <= 40%)，即将达成满专的大碟
        if alb_tot >= 3 and alb_lit > 0 and 1 <= alb_unlit <= 4:
            unlit_songs = [{"id": s.get("id"), "title": s.get("title")} for s in songs if not is_song_lit(s)]
            art_sparse_albums.append({
                "album": alb_title,
                "total": alb_tot,
                "lit": alb_lit,
                "unlit": alb_unlit,
                "unlit_songs": unlit_songs
            })
            
    if art_sparse_albums:
        total_unlit_needed = sum(x["unlit"] for x in art_sparse_albums)
        sparse_summary.append({
            "artist": art_name,
            "sparse_album_count": len(art_sparse_albums),
            "total_unlit_needed": total_unlit_needed,
            "albums": art_sparse_albums,
            "total_songs": art_tot,
            "lit_songs": art_lit,
            "overall_lit_pct": round(art_lit / art_tot * 100, 1) if art_tot else 0
        })

# 排序: 综合排序（只差几首就能满专的知名歌手）
sparse_summary.sort(key=lambda x: (x["sparse_album_count"], -x["total_unlit_needed"]), reverse=True)

print(f"\n找到具有稀稀拉拉残缺专辑的歌手数: {len(sparse_summary)}")
print("=" * 100)
print(f"{'序号':<4} | {'歌手名称':<12} | {'残缺专辑数':<10} | {'仅需补齐首数':<12} | {'歌手整体点亮率':<14} | 重点待补大碟示例")
print("-" * 100)

for i, item in enumerate(sparse_summary[:30], 1):
    ex = item["albums"][0]
    song_names = "、".join([s["title"] for s in ex["unlit_songs"][:3]])
    ex_str = f"《{ex['album']}》(仅差{ex['unlit']}首: {song_names})"
    print(f"{i:>4} | {item['artist']:<12} | {item['sparse_album_count']:^10} | {item['total_unlit_needed']:^12} | {item['overall_lit_pct']:>6.1f}% ({item['lit_songs']}/{item['total_songs']}) | {ex_str}")

# 保存为 json 供后续多 agent 调度使用
with open("sparse_albums_catalog.json", "w", encoding="utf-8") as f:
    json.dump(sparse_summary, f, ensure_ascii=False, indent=2)
print("\n完整清单已保存至 sparse_albums_catalog.json")
