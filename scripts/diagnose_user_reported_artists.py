#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深入诊断用户汇报的 8 位歌手在 Cloudflare D1 生产库中的现状：
1. 范玮琪 (Fan Fan)
2. 林忆莲 (Sandy Lam)
3. 莫文蔚 (Karen Mok)
4. Twins
5. 萧亚轩 (Elva Hsiao)
6. 郁可唯 (Yisa Yu)
7. 张韶涵 (Angela Zhang)
8. 蔡琴 (Tsai Chin)
"""

import requests
import json
import urllib.parse
import re

WORKER_BASE = "https://m-api.changgepd.ccwu.cc"
PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}

TARGET_ARTISTS = [
    "范玮琪", "范瑋琪", "Christine Fan",
    "林忆莲", "林憶蓮", "Sandy Lam",
    "莫文蔚", "Karen Mok",
    "Twins", "twins",
    "萧亚轩", "蕭亞軒", "Elva Hsiao",
    "郁可唯", "Yisa Yu",
    "张韶涵", "張韶涵", "Angela Zhang",
    "蔡琴", "Tsai Chin"
]

def main():
    print("================================================================")
    print("📡 正在从 Cloudflare Worker 拉取全库 /api/skeleton 骨架数据...")
    print("================================================================")
    try:
        r = requests.get(f"{WORKER_BASE}/api/skeleton", proxies=PROXIES, timeout=30)
        data = r.json()
        artists = data.get("artists", []) if isinstance(data, dict) else data
        print(f"✅ 获取成功，当前全库总计歌手数: {len(artists)} 位\n")
    except Exception as e:
        print(f"❌ 获取 /api/skeleton 失败: {e}")
        return

    # 建立名字映射
    artist_map = {}
    for a in artists:
        name = a.get("name", "")
        artist_map[name] = a
        artist_map[name.lower()] = a

    print("================================================================")
    print("🔍 目标歌手骨架匹配诊断")
    print("================================================================\n")

    found_targets = {}
    for query in ["范玮琪", "林忆莲", "莫文蔚", "Twins", "萧亚轩", "郁可唯", "张韶涵", "蔡琴"]:
        matched_artist = None
        for a_name, a_obj in artist_map.items():
            if query in a_name or (query == "Twins" and "twins" in a_name.lower()):
                matched_artist = a_obj
                break
        found_targets[query] = matched_artist

    for query, a_obj in found_targets.items():
        if not a_obj:
            print(f"❌ 【{query}】: 在全库 158 位歌手中【完全不存在】！(未收录)")
        else:
            name = a_obj.get("name")
            albums = a_obj.get("albums", [])
            print(f"✅ 【{query}】(库内名称: '{name}'): 包含 {len(albums)} 张专辑")

    print("\n================================================================")
    print("📊 正在逐一深入探测各歌手的专辑、歌曲点亮状态与英文直译情况...")
    print("================================================================\n")

    report = {}

    for query, a_obj in found_targets.items():
        if not a_obj:
            report[query] = {"status": "NOT_FOUND"}
            continue

        real_name = a_obj.get("name")
        albums = a_obj.get("albums", [])
        
        artist_report = {
            "name": real_name,
            "albums_count": len(albums),
            "total_songs": 0,
            "lit_songs": 0,
            "unlit_songs": 0,
            "english_titled_songs": 0,
            "sparse_albums": [],
            "sample_english_songs": [],
            "albums_detail": []
        }

        for alb in albums:
            aid = alb.get("id")
            atitle = alb.get("title")
            
            try:
                # 获取专辑详情 (包含曲目列表)
                r_det = requests.get(
                    f"{WORKER_BASE}/api/admin/albums/detail?album_id={aid}",
                    proxies=PROXIES, timeout=15
                )
                det = r_det.json().get("data", {})
                songs = det.get("songs", [])
            except Exception as e:
                songs = []

            alb_total = len(songs)
            alb_lit = sum(1 for s in songs if s.get("is_lit") == 1 or s.get("file_path"))
            alb_unlit = alb_total - alb_lit

            artist_report["total_songs"] += alb_total
            artist_report["lit_songs"] += alb_lit
            artist_report["unlit_songs"] += alb_unlit

            # 统计纯英文歌名 (且不是纯标点)
            alb_eng_songs = []
            for s in songs:
                stit = s.get("title", "")
                # 判断是否几乎全为英文/ASCII，且没有中文字符
                has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', stit))
                has_alpha = bool(re.search(r'[a-zA-Z]', stit))
                if not has_chinese and has_alpha and len(stit.strip()) > 1:
                    artist_report["english_titled_songs"] += 1
                    alb_eng_songs.append({"id": s.get("id"), "title": stit, "is_lit": s.get("is_lit")})
                    if len(artist_report["sample_english_songs"]) < 10:
                        artist_report["sample_english_songs"].append({
                            "album": atitle,
                            "title": stit,
                            "is_lit": s.get("is_lit")
                        })

            alb_summary = {
                "id": aid,
                "title": atitle,
                "total": alb_total,
                "lit": alb_lit,
                "unlit": alb_unlit,
                "english_count": len(alb_eng_songs)
            }
            artist_report["albums_detail"].append(alb_summary)

            # 判断是否稀稀拉拉 (未满专但点亮了部分，或者差 1~4 首)
            if alb_total > 0 and 0 < alb_unlit <= 5:
                artist_report["sparse_albums"].append(alb_summary)

        report[query] = artist_report

        print(f"----------------------------------------------------------------")
        print(f"🎵 歌手: 【{real_name}】")
        print(f"   - 专辑总数: {artist_report['albums_count']} 张")
        print(f"   - 歌曲总数: {artist_report['total_songs']} 首 (已点亮: {artist_report['lit_songs']} | 未点亮: {artist_report['unlit_songs']})")
        print(f"   - 点亮率: {artist_report['lit_songs'] / max(1, artist_report['total_songs']) * 100:.1f}%")
        print(f"   - 纯英文/直译歌名曲目数: {artist_report['english_titled_songs']} 首 ({artist_report['english_titled_songs'] / max(1, artist_report['total_songs']) * 100:.1f}%)")
        if artist_report["sample_english_songs"]:
            print(f"   - 英文曲目样本: {[s['title'] for s in artist_report['sample_english_songs'][:5]]}")
        if artist_report["sparse_albums"]:
            print(f"   - 典型稀缺残缺专辑 (差 1~5 首): {[a['title'] + f' (差{a['unlit']}首)' for a in artist_report['sparse_albums'][:4]]}")

    with open("data/user_reported_artists_diagnosis.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n📄 完整诊断数据已保存至: data/user_reported_artists_diagnosis.json")

if __name__ == "__main__":
    main()
