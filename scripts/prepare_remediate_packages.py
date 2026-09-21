#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精选攻坚目标：将“稀稀拉拉置灰几首”的知名专辑打包分组
"""

import json

with open("sparse_albums_catalog.json", "r", encoding="utf-8") as f:
    catalog = json.load(f)

# 精选首批高价值满专攻坚目标
priority_artists = ["Beyond", "萧亚轩", "方大同", "苏慧伦", "任贤齐", "张信哲", "李玟", "黎明", "周华健"]

pkg_targets = []
album_summary = []

for item in catalog:
    art = item["artist"]
    if art in priority_artists:
        for alb in item["albums"]:
            # 只选差 1~3 首歌的极品专辑
            if 1 <= alb["unlit"] <= 3:
                album_summary.append({
                    "artist": art,
                    "album": alb["album"],
                    "total": alb["total"],
                    "lit": alb["lit"],
                    "unlit": alb["unlit"],
                    "songs": alb["unlit_songs"]
                })
                for s in alb["unlit_songs"]:
                    pkg_targets.append({
                        "id": s["id"],
                        "artist": art,
                        "album": alb["album"],
                        "title": s["title"],
                        "search_title": s["title"]
                    })

print(f"=== 首批精选攻坚目标盘点 ===")
print(f"涉及专辑数: {len(album_summary)} 张")
print(f"待补曲目总数: {len(pkg_targets)} 首\n")

print(f"{'歌手':<10} | {'专辑名称':<25} | 进度 | 待补曲目")
print("-" * 80)
for a in album_summary:
    song_names = "、".join([s["title"] for s in a["songs"]])
    alb_display = a['album'][:20]
    print(f"{a['artist']:<10} | 《{alb_display}》 | {a['lit']}/{a['total']} | {song_names}")

# 分成两个均衡的并行工作包:
# Package A: 摇滚与流行天王天后 (Beyond, 萧亚轩, 方大同, 苏慧伦, 任贤齐)
# Package B: 情歌天王与国民金曲 (张信哲, 李玟, 黎明, 周华健)

pkg_a = [t for t in pkg_targets if t["artist"] in ["Beyond", "萧亚轩", "方大同", "苏慧伦", "任贤齐"]]
pkg_b = [t for t in pkg_targets if t["artist"] in ["张信哲", "李玟", "黎明", "周华健"]]

print(f"\n工作包 A 待采录曲目: {len(pkg_a)} 首 (摇滚天团与流行金曲)")
print(f"工作包 B 待采录曲目: {len(pkg_b)} 首 (情歌王子与国民经典)")

with open("sparse_pkg_a.json", "w", encoding="utf-8") as f:
    json.dump(pkg_a, f, ensure_ascii=False, indent=2)

with open("sparse_pkg_b.json", "w", encoding="utf-8") as f:
    json.dump(pkg_b, f, ensure_ascii=False, indent=2)
