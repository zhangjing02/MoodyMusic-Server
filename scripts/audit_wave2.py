#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import requests

with open("MoodyMusic-Server/scripts/configs/second_wave_targets.json", "r", encoding="utf-8") as f:
    targets = json.load(f)

artists = {}
for item in targets:
    art = item["artist_name"]
    alb = item["album_title"]
    aid = item["album_id"]
    sid = item["song_id"]
    title = item["title"]
    if art not in artists:
        artists[art] = {}
    if alb not in artists[art]:
        artists[art][alb] = {"album_id": aid, "songs": []}
    artists[art][alb]["songs"].append({"song_id": sid, "title": title})

API_BASE = "https://m-api.changgepd.ccwu.cc"

print("🔍 开始全面核查第二波 7 位歌手在 D1 上的点亮情况...\n")

total_all = 0
lit_all = 0

for art, albums in artists.items():
    art_total = 0
    art_lit = 0
    art_full_albums = 0
    print(f"🎤 歌手: 【{art}】 (共 {len(albums)} 张专辑)")
    
    for alb_title, alb_info in albums.items():
        aid = alb_info["album_id"]
        songs = alb_info["songs"]
        a_total = len(songs)
        
        try:
            r = requests.get(f"{API_BASE}/api/admin/albums/detail", params={"album_id": aid}, timeout=10)
            if r.ok:
                d1_songs = {s["id"]: s for s in r.json().get("data", {}).get("songs", [])}
                a_lit = sum(1 for s in songs if d1_songs.get(s["song_id"], {}).get("file_path"))
                missing = [s["title"] for s in songs if not d1_songs.get(s["song_id"], {}).get("file_path")]
            else:
                a_lit = 0
                missing = ["(请求失败)"]
        except Exception as e:
            a_lit = 0
            missing = [str(e)]
            
        art_total += a_total
        art_lit += a_lit
        is_full = (a_lit == a_total)
        if is_full:
            art_full_albums += 1
            status_tag = "✅ 满贯"
        else:
            missing_str = ", ".join(missing[:3])
            status_tag = f"⚠️ 未满 (缺 {a_total - a_lit} 首: {missing_str})"
            
        print(f"   - 《{alb_title}》: {a_lit}/{a_total} 首点亮 {status_tag}")
        
    pct = (art_lit / art_total * 100) if art_total > 0 else 0
    total_all += art_total
    lit_all += art_lit
    print(f"👉 【{art}】总结: {art_lit}/{art_total} 首已点亮 ({pct:.1f}%), 满贯专辑: {art_full_albums}/{len(albums)}\n" + "-"*50)

all_pct = (lit_all / total_all * 100) if total_all > 0 else 0
print(f"\n🏆 第二波全员总计: {lit_all}/{total_all} 首已点亮 ({all_pct:.1f}%)")
