#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面透视 Cloudflare D1 当前 158 位歌手的专辑点亮状态：
1. 找出所有“稀疏残缺”（0 < lit < total）的专辑
2. 找出所有“全黑未点亮”（lit == 0）但属于核心知名歌手的代表作专辑
3. 统计各核心歌手的总体点亮情况
"""

import requests
import json

print("Fetching D1 songs data...", flush=True)
sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0"})
resp = sess.get("https://m-api.changgepd.ccwu.cc/api/songs", timeout=30)
data = resp.json().get("data", [])

print(f"Total artists: {len(data)}")

CORE_SUPERSTARS = [
    "周杰伦", "林俊杰", "孙燕姿", "王力宏", "陶喆", "陈奕迅", "王菲", "张惠妹",
    "Beyond", "伍佰", "汪峰", "刘德华", "张学友", "郭富城", "黎明", "梁静茹",
    "莫文蔚", "田馥甄", "SHE", "S.H.E", "五月天", "朴树", "许嵩", "薛之谦",
    "毛不易", "李健", "赵雷", "周深", "郁可唯", "张敬轩", "容祖儿", "杨千嬅",
    "古巨基", "张震岳", "陈绮贞", "蔡健雅", "戴佩妮", "张韶涵", "羽泉", "动力火车",
    "任贤齐", "齐秦", "童安格", "姜育恒", "黄品源", "杜德伟", "庾澄庆", "张宇",
    "郑中基", "李宗盛", "罗大佑", "苏慧伦", "崔健", "迪克牛仔", "郑智化", "曾轶可"
]

all_sparse_albums = []
all_zero_albums_core = []
artist_summaries = []

for art in data:
    aname = art.get("name", "").strip()
    albums = art.get("albums", [])
    
    total_songs = 0
    lit_songs = 0
    
    is_core = any(c.lower() in aname.lower() for c in CORE_SUPERSTARS)
    
    sparse_in_art = []
    zero_in_art = []
    full_in_art = []
    
    for alb in albums:
        atitle = alb.get("title", "").strip()
        songs = alb.get("songs", [])
        tot = len(songs)
        if tot == 0:
            continue
        lit = sum(1 for s in songs if s.get("path"))
        unlit = tot - lit
        
        total_songs += tot
        lit_songs += lit
        
        unlit_titles = [s.get("title") for s in songs if not s.get("path")]
        
        if 0 < lit < tot:
            sparse_in_art.append({
                "album": atitle,
                "total": tot,
                "lit": lit,
                "unlit": unlit,
                "pct": round(lit / tot * 100, 1),
                "unlit_titles": unlit_titles
            })
            all_sparse_albums.append({
                "artist": aname,
                "album": atitle,
                "total": tot,
                "lit": lit,
                "unlit": unlit,
                "pct": round(lit / tot * 100, 1),
                "unlit_titles": unlit_titles,
                "is_core": is_core
            })
        elif lit == 0:
            zero_in_art.append({
                "album": atitle,
                "total": tot
            })
            if is_core:
                all_zero_albums_core.append({
                    "artist": aname,
                    "album": atitle,
                    "total": tot,
                    "titles": unlit_titles
                })
        else:
            full_in_art.append(atitle)
            
    pct = round(lit_songs / total_songs * 100, 1) if total_songs > 0 else 0
    if total_songs > 0:
        artist_summaries.append({
            "artist": aname,
            "total_songs": total_songs,
            "lit_songs": lit_songs,
            "unlit_songs": total_songs - lit_songs,
            "pct": pct,
            "total_albums": len(albums),
            "full_albums": len(full_in_art),
            "sparse_albums": len(sparse_in_art),
            "zero_albums": len(zero_in_art),
            "is_core": is_core
        })

print(f"\n=======================================================")
print(f"📊 全库审计完成:")
print(f"   • 全库稀疏残缺专辑（部分置灰）: {len(all_sparse_albums)} 张")
print(f"   • 核心知名歌手稀疏专辑: {sum(1 for a in all_sparse_albums if a['is_core'])} 张")
print(f"   • 核心知名歌手全黑未点亮专辑: {len(all_zero_albums_core)} 张")
print(f"=======================================================\n")

# 1. 核心歌手的稀疏残缺专辑（按缺歌数从小到大排序）
core_sparse = [a for a in all_sparse_albums if a["is_core"]]
core_sparse.sort(key=lambda x: (x["unlit"], -x["total"]))

print("🔥 【优先攻坚清单 1】：核心歌手稀疏专辑（仅缺 1~3 首即可达成满专）")
for a in core_sparse:
    if a["unlit"] <= 3:
        titles = ", ".join(a["unlit_titles"][:3])
        print(f"  • [{a['artist']}] 《{a['album']}》: {a['lit']}/{a['total']} (仅缺 {a['unlit']} 首: {titles})")

print("\n⚠️ 【稀疏专辑清单 2】：核心歌手缺 4 首及以上的专辑")
for a in core_sparse:
    if a["unlit"] > 3:
        titles = ", ".join(a["unlit_titles"][:3]) + f" 等{a['unlit']}首"
        print(f"  • [{a['artist']}] 《{a['album']}》: {a['lit']}/{a['total']} (缺 {a['unlit']} 首: {titles})")

# 2. 核心知名歌手的整体点亮情况排查
print("\n👑 【核心天王天后整体点亮现状】:")
core_summaries = [s for s in artist_summaries if s["is_core"]]
core_summaries.sort(key=lambda x: (x["pct"], -x["total_songs"]))
for s in core_summaries:
    print(f"  • {s['artist']:<8}: 点亮 {s['lit_songs']:>3}/{s['total_songs']:<3} ({s['pct']:>5.1f}%) | 满专:{s['full_albums']:>2} | 稀疏:{s['sparse_albums']:>2} | 全黑:{s['zero_albums']:>2}")

# 保存详细报告
with open("reports/comprehensive_unlit_audit.json", "w", encoding="utf-8") as f:
    json.dump({
        "sparse_albums": all_sparse_albums,
        "core_zero_albums": all_zero_albums_core,
        "artist_summaries": artist_summaries
    }, f, ensure_ascii=False, indent=2)

print("\n✅ 详细审计结果已写入 reports/comprehensive_unlit_audit.json")
