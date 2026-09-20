#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时扫描 Cloudflare D1 生产环境：
查找核心歌手和知名歌手中，依然处于“稀疏残缺置灰”状态的专辑。
"""

import requests
import json
import time

print("Fetching latest D1 catalog...", flush=True)
sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
for attempt in range(3):
    try:
        resp = sess.get("https://m-api.changgepd.ccwu.cc/api/songs", timeout=30)
        if resp.status_code == 200:
            break
    except Exception as e:
        print(f"Retry {attempt+1}: {e}")
        time.sleep(1)
data = resp.json().get("data", [])

print(f"Total artists in D1: {len(data)}")

CORE_ARTISTS = [
    "周杰伦", "陈奕迅", "林俊杰", "孙燕姿", "王菲", "张惠妹", "陶喆", "李宗盛", "罗大佑",
    "Beyond", "汪峰", "伍佰", "刘德华", "张学友", "郭富城", "黎明", "梁静茹", "莫文蔚",
    "萧敬腾", "潘玮柏", "王力宏", "邓紫棋", "朴树", "许嵩", "薛之谦", "毛不易", "赵雷",
    "李健", "周深", "郁可唯", "苏打绿", "张敬轩", "容祖儿", "杨千嬅", "古巨基", "陈绮贞",
    "张震岳", "蔡健雅", "戴佩妮", "张韶涵", "SHE", "S.H.E", "羽泉", "动力火车", "任贤齐",
    "齐秦", "童安格", "姜育恒", "黄品源", "杜德伟", "庾澄庆", "张宇", "郑中基"
]

results = []

for artist in data:
    aname = artist.get("name", "").strip()
    albums = artist.get("albums", [])
    
    for alb in albums:
        alb_name = alb.get("name", "").strip()
        songs = alb.get("songs", [])
        total = len(songs)
        if total == 0:
            continue
        lit = sum(1 for s in songs if s.get("is_lit") == 1 or s.get("is_lit") is True)
        unlit = total - lit
        
        if 0 < lit < total:  # 稀疏专辑 (部分点亮，部分置灰)
            unlit_songs = [s for s in songs if not (s.get("is_lit") == 1 or s.get("is_lit") is True)]
            is_core = any(c.lower() in aname.lower() for c in CORE_ARTISTS)
            results.append({
                "artist": aname,
                "album": alb_name,
                "total": total,
                "lit": lit,
                "unlit": unlit,
                "pct": round(lit / total * 100, 1),
                "unlit_titles": [s.get("title") for s in unlit_songs],
                "unlit_ids": [s.get("id") for s in unlit_songs],
                "is_core": is_core
            })

print(f"Total sparse albums across whole D1: {len(results)}")

core_sparse = [r for r in results if r["is_core"]]
print(f"Total sparse albums among Core Artists: {len(core_sparse)}")

# 按缺失数量从少到多排序（最容易补全满专的排前面，如缺1~3首的）
core_sparse.sort(key=lambda x: (x["unlit"], -x["total"]))

print("\n=== TOP 30 CORE ARTIST SPARSE ALBUMS (缺 1~3 首即可满专) ===")
for r in core_sparse[:30]:
    art = r["artist"]
    alb = r["album"]
    tot = r["total"]
    lit = r["lit"]
    unlit = r["unlit"]
    titles_str = ", ".join(r["unlit_titles"][:3])
    if len(r["unlit_titles"]) > 3:
        titles_str += f" 等共{unlit}首"
    print(f"[{art}] 《{alb}》: {lit}/{tot} (缺 {unlit} 首: {titles_str})")

with open("reports/current_core_sparse_albums.json", "w", encoding="utf-8") as f:
    json.dump(core_sparse, f, ensure_ascii=False, indent=2)
