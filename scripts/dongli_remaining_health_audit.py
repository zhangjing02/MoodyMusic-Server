#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动力火车全专辑全曲目健康度与一致性全面审查脚本
"""
import requests
import json
import re

API_BASE = "https://m-api.changgepd.ccwu.cc"

ALBUM_IDS = [354, 353, 350, 349, 351, 348, 352, 1859, 345, 343]

SUSPECT_KEYWORDS = [
    "小安迪", "幼稚园杀手", "赵辰龙", "连麻", "法老", "Lil Jet", "Sasuke", 
    "周浠灵", "黑撒", "熊天平", "许茹芸", "萧煌奇", "张宇", "陈淑桦",
    "手牵手", "吴子健", "REmi", "郑中基"
]

all_results = {}

for aid in ALBUM_IDS:
    res = requests.get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}", timeout=10)
    if res.status_code != 200:
        continue
    data = res.json().get("data", {})
    album_info = data.get("album", {})
    songs = data.get("songs", [])
    album_title = album_info.get("title")

    song_audits = []
    for s in songs:
        sid = s.get("id")
        title = s.get("title")
        fpath = s.get("file_path")
        lpath = s.get("lrc_path")

        mp3_ok = False
        mp3_code = 0
        mp3_size = 0
        if fpath:
            try:
                hr = requests.head(fpath, timeout=5)
                mp3_code = hr.status_code
                mp3_size = int(hr.headers.get("Content-Length", 0))
                mp3_ok = (mp3_code == 200 and mp3_size > 500000)
            except Exception:
                pass

        lrc_ok = False
        lrc_suspect = []
        lrc_text = ""
        if lpath:
            try:
                lr = requests.get(lpath, timeout=5)
                if lr.status_code == 200:
                    lrc_ok = True
                    lrc_text = lr.text
                    for kw in SUSPECT_KEYWORDS:
                        if kw in lrc_text:
                            lrc_suspect.append(kw)
            except Exception:
                pass

        song_audits.append({
            "id": sid,
            "title": title,
            "track_index": s.get("track_index"),
            "mp3_ok": mp3_ok,
            "mp3_code": mp3_code,
            "mp3_size": mp3_size,
            "lrc_ok": lrc_ok,
            "lrc_suspect": lrc_suspect,
            "file_path": fpath,
            "lrc_path": lpath
        })

    all_results[aid] = {
        "title": album_title,
        "total": len(songs),
        "songs": song_audits
    }
    print(f"审查完成: [{aid}] {album_title} ({len(songs)} 首)")

with open("/tmp/dongli_audit_status.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print("全部审查完成，结果保存至 /tmp/dongli_audit_status.json")
