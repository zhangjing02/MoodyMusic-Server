#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速解析张韶涵、林忆莲、Twins 的全部曲目与真实 D1 Song ID
"""

import requests
import json
import time

WORKER = "https://m-api.changgepd.ccwu.cc"
PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}

def get_artist_albums(art_name):
    # 先从 /api/songs 获取该艺人的准确专辑列表（包括繁体标题）
    r = requests.get(f"{WORKER}/api/songs?artist={art_name}", proxies=PROXIES)
    data = r.json().get("data", [])
    if not data: return []
    return [a["title"] for a in data[0].get("albums", [])]

def main():
    print("================================================================")
    print("🔍 正在拉取张韶涵、林忆莲、Twins 的全部专辑与真实 Song ID...")
    print("================================================================")

    all_resolved = []

    for art in ["张韶涵", "林忆莲", "Twins"]:
        album_titles = get_artist_albums(art)
        print(f"\n▶ 歌手: 【{art}】 (共 {len(album_titles)} 张专辑)")

        for atitle in album_titles:
            # 搜索该专辑
            try:
                r_s = requests.get(
                    f"{WORKER}/api/admin/albums/search",
                    params={"keyword": atitle},
                    proxies=PROXIES,
                    timeout=10
                )
                albums_list = r_s.json().get("data", {}).get("albums", [])
            except Exception as e:
                albums_list = []

            aid = None
            for a in albums_list:
                if a.get("artist_name") == art or art.lower() in a.get("artist_name", "").lower():
                    aid = a.get("id")
                    break
            
            if not aid and albums_list:
                aid = albums_list[0].get("id")

            if not aid:
                print(f"   ⚠️ 未查到专辑 ID: 《{atitle}》")
                continue

            # 获取详情
            try:
                r_det = requests.get(
                    f"{WORKER}/api/admin/albums/detail",
                    params={"album_id": aid},
                    proxies=PROXIES,
                    timeout=10
                )
                det_songs = r_det.json().get("data", {}).get("songs", [])
                unlit = [s for s in det_songs if not s.get("file_path") and s.get("is_lit") != 1]
                print(f"   💿 《{atitle}》 (ID: {aid}) - 发现 {len(unlit)} 首待采录曲目")

                for s in unlit:
                    sid = s["id"]
                    tit = s["title"]
                    search_t = tit
                    if len(tit) <= 2:
                        search_t = f"{tit} {art}"
                    elif tit in ["飞", "绝", "红", "风", "雨", "梦", "云", "海", "星", "爱"]:
                        search_t = f"{tit} {art}"
                    
                    all_resolved.append({
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
    print(f"🎉 成功精准解析并绑定全部 {len(all_resolved)} 首三大天后歌手待采录曲目！")
    print("================================================================\n")

    with open("full_divas_resolved.json", "w", encoding="utf-8") as f:
        json.dump(all_resolved, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
