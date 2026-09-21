#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出张韶涵 (83首)、林忆莲 (90首)、Twins (73首) 的全部曲目
生成：full_divas_targets.json
"""

import requests
import json

WORKER = "https://m-api.changgepd.ccwu.cc"
PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}

TARGET_DIVAS = ["张韶涵", "林忆莲", "Twins"]

def main():
    print("================================================================")
    print("📡 正在导出三大空白天后歌手 (张韶涵, 林忆莲, Twins) 的全量曲目清单...")
    print("================================================================")

    all_targets = []

    for art in TARGET_DIVAS:
        r = requests.get(f"{WORKER}/api/songs?artist={art}", proxies=PROXIES)
        artist_obj = r.json().get("data", [])[0]
        albums = artist_obj.get("albums", [])
        print(f"\n▶ 歌手: 【{art}】 (共 {len(albums)} 张专辑)")

        art_count = 0
        for alb in albums:
            atitle = alb["title"]
            songs = alb.get("songs", [])
            for s in songs:
                tit = s["title"]
                search_t = tit
                # 歌名微调优化
                if search_t in ["飞", "绝", "红", "风", "雨", "梦", "云", "海", "星", "爱"]:
                    search_t = f"{tit} {art}"
                all_targets.append({
                    "artist": art,
                    "album": atitle,
                    "title": tit,
                    "search_title": search_t,
                    "path": s.get("path")
                })
                art_count += 1

        print(f"   共收录 {art_count} 首曲目")

    # 去除已经有点亮的
    unlit_targets = [t for t in all_targets if not t.get("path")]

    print("\n================================================================")
    print(f"📊 三大歌手总曲目: {len(all_targets)} 首 | 待采录点亮: {len(unlit_targets)} 首")
    print("================================================================\n")

    with open("full_divas_targets.json", "w", encoding="utf-8") as f:
        json.dump(unlit_targets, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
