#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import json

API_BASE = "https://m-api.changgepd.ccwu.cc"

target_albums = [1859, 345, 343, 354, 353, 350, 349, 351, 348, 352]

all_data = {}
for aid in target_albums:
    res = requests.get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}", timeout=10)
    if res.status_code == 200:
        data = res.json().get("data", {})
        album_info = data.get("album", {})
        songs = data.get("songs", [])
        all_data[aid] = {
            "title": album_info.get("title"),
            "song_count": len(songs),
            "songs": [
                {
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "track_index": s.get("track_index"),
                    "file_path": s.get("file_path"),
                    "lrc_path": s.get("lrc_path")
                } for s in songs
            ]
        }
        print(f"[{aid}] {album_info.get('title')}: {len(songs)} tracks")
    else:
        print(f"Failed to fetch {aid}: {res.status_code}")

with open("/tmp/dongli_10_albums_overview.json", "w", encoding="utf-8") as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)
print("Dumped all 10 albums overview to /tmp/dongli_10_albums_overview.json")
