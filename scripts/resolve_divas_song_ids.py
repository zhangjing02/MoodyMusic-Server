#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速解析张韶涵 (83首)、林忆莲 (90首)、Twins (73首) 的准确 D1 Song ID
生成：full_divas_resolved.json
"""

import requests
import json
import time

WORKER = "https://m-api.changgepd.ccwu.cc"
PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}

def main():
    print("================================================================")
    print("🔍 正在拉取张韶涵、林忆莲、Twins 的所有专辑 ID 与曲目详情...")
    print("================================================================")

    resolved = []

    for art in ["张韶涵", "林忆莲", "Twins"]:
        r = requests.get(f"{WORKER}/api/search?q={art}", proxies=PROXIES)
        albums = r.json().get("data", {}).get("albums", [])
        print(f"\n▶ 歌手: 【{art}】 (匹配到 {len(albums)} 张专辑)")

        for alb in albums:
            aid = alb["id"]
            atitle = alb["title"]
            try:
                r_det = requests.get(
                    f"{WORKER}/api/admin/albums/detail",
                    params={"album_id": aid},
                    proxies=PROXIES,
                    timeout=10
                )
                det = r_det.json().get("data", {})
                songs = det.get("songs", [])
                unlit = [s for s in songs if not s.get("file_path") and s.get("is_lit") != 1]
                print(f"   💿 《{atitle}》 (ID: {aid}) - 发现 {len(unlit)} 首待采录曲目")

                for s in unlit:
                    sid = s["id"]
                    tit = s["title"]
                    search_t = tit
                    if len(tit) <= 2:
                        search_t = f"{tit} {art}"
                    
                    resolved.append({
                        "id": sid,
                        "artist": art,
                        "album": atitle,
                        "title": tit,
                        "search_title": search_t
                    })
            except Exception as e:
                print(f"   ❌ 获取专辑 {aid} 详情失败: {e}")

            time.sleep(0.05)

    print("\n================================================================")
    print(f"🎉 成功精准解析并绑定全部 {len(resolved)} 首三大天后歌手曲目！")
    print("================================================================\n")

    with open("full_divas_resolved.json", "w", encoding="utf-8") as f:
        json.dump(resolved, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
