#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 全库骨架与点亮率地毯式审计探针
======================================
从 D1 提取所有歌手、专辑与曲目状态，精准识别出：
1. 重点关注歌手（飞儿乐团、那英、古巨基）的缺失专辑与缺失曲目明细；
2. 全库所有歌手的点亮率梯队分布，找出半点亮/严重缺失歌手清单。
"""

import requests
import json
import time

API_BASE = "https://m-api.changgepd.ccwu.cc"

def main():
    print("🔍 启动全库歌手骨架与点亮率地毯式扫描...")
    start_time = time.time()

    # 1. 获取全库所有歌手列表
    # 通过 /api/skeleton 接口获取所有已入库的 artists
    r_skel = requests.get(f"{API_BASE}/api/skeleton", timeout=20)
    if not r_skel.ok:
        print("❌ 获取骨架失败:", r_skel.status_code, r_skel.text)
        return

    artists = r_skel.json().get("data", {}).get("artists", [])
    print(f"📦 发现总计 {len(artists)} 位歌手")

    stats = []
    
    # 针对每位歌手，调用 /api/songs?artistId=db_xxx 或 /api/admin/albums/search 获取详情
    for idx, a in enumerate(artists, 1):
        art_id = a["id"].replace("db_", "")
        art_name = a["name"]
        
        # 获取该歌手全部专辑
        try:
            r_alb = requests.get(f"{API_BASE}/api/admin/albums/search", params={"artist_id": art_id, "limit": 100}, timeout=15)
            albums = r_alb.json().get("data", {}).get("albums", []) if r_alb.ok else []
        except Exception:
            albums = []

        total_songs = 0
        lit_songs = 0
        album_details = []

        for alb in albums:
            alb_id = alb["id"]
            alb_title = alb["title"]
            try:
                r_detail = requests.get(f"{API_BASE}/api/admin/albums/detail", params={"album_id": alb_id}, timeout=10)
                songs = r_detail.json().get("data", {}).get("songs", []) if r_detail.ok else []
            except Exception:
                songs = []

            a_tot = len(songs)
            a_lit = sum(1 for s in songs if s.get("file_path"))
            total_songs += a_tot
            lit_songs += a_lit

            missing_songs = [s["title"] for s in songs if not s.get("file_path")]
            album_details.append({
                "album_id": alb_id,
                "album_title": alb_title,
                "total": a_tot,
                "lit": a_lit,
                "missing_count": a_tot - a_lit,
                "missing_titles": missing_songs
            })

        pct = (lit_songs / total_songs * 100) if total_songs > 0 else 0
        stats.append({
            "artist_id": art_id,
            "artist_name": art_name,
            "album_count": len(albums),
            "total_songs": total_songs,
            "lit_songs": lit_songs,
            "unlit_songs": total_songs - lit_songs,
            "pct": pct,
            "albums": album_details
        })

    elapsed = time.time() - start_time
    print(f"⏱️ 扫描完成，耗时: {elapsed:.1f} 秒\n")

    # 保存全量扫描结果
    out_file = "MoodyMusic-Server/scripts/configs/catalog_audit_result.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"💾 全量扫描结果已写入: {out_file}")

    # 打印分析报告
    # 1. 重点歌手 (飞儿乐团、那英、古巨基)
    priority_names = ["飞儿乐团", "F.I.R.", "F.I.R. 飞儿乐团", "那英", "古巨基"]
    print("=" * 80)
    print("🎯 用户点名重点攻坚歌手状态：")
    print("=" * 80)
    for item in stats:
        if any(p in item["artist_name"] for p in priority_names):
            print(f"🎤 【{item['artist_name']}】 (ID: {item['artist_id']})")
            print(f"   📊 专辑总数: {item['album_count']} | 歌曲总数: {item['total_songs']} | 已点亮: {item['lit_songs']} | 缺失: {item['unlit_songs']} ({item['pct']:.1f}%)")
            for alb in item["albums"]:
                tag = "✅ 满" if alb["missing_count"] == 0 else f"⚠️ 缺 {alb['missing_count']} 首"
                print(f"     - 《{alb['album_title']}》 ({alb['lit']}/{alb['total']}) {tag}")
            print("-" * 50)

    # 2. 其他缺失较严重的歌手列表 (点亮率 < 80% 且歌曲总数 >= 10)
    print("\n" + "=" * 80)
    print("📋 全库其他点亮率严重不足的歌手排行 (点亮率 < 80% 且总曲目 >= 10)：")
    print("=" * 80)
    deficits = [s for s in stats if s["pct"] < 80.0 and s["total_songs"] >= 10]
    deficits.sort(key=lambda x: (x["pct"], -x["unlit_songs"]))

    for s in deficits:
        print(f"  • 【{s['artist_name']}】(ID: {s['artist_id']}): 点亮率 {s['pct']:.1f}% ({s['lit_songs']}/{s['total_songs']} 首，缺 {s['unlit_songs']} 首，共 {s['album_count']} 张专辑)")

if __name__ == "__main__":
    main()
