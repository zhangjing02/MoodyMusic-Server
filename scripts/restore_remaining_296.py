#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
复原第一存储桶中剩余被置灰的 296 首真实资产（五月天 102首、Beyond 80首、信乐团 71首、蔡依林 43首）
"""

import json
import time
import requests

D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
ASSETS_PATH = "reports/bucket01_verified_assets.json"

sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0"})

data = json.load(open(ASSETS_PATH))
found = [s for s in data["found_songs"] if s["artist"] != "周杰伦"]

resp = sess.get(D1_SONGS_URL, timeout=30)
d1_artists = resp.json().get("data", [])

lit_keys = set()
for art in d1_artists:
    aname = art.get("name", "").strip()
    for alb in art.get("albums", []):
        atitle = alb.get("title", "").strip()
        for s in alb.get("songs", []):
            stitle = s.get("title", "").strip()
            if s.get("path"):
                lit_keys.add((aname, atitle, stitle))

unlit_to_restore = []
for s in found:
    key = (s["artist"].strip(), s["album"].strip(), s["title"].strip())
    if key not in lit_keys:
        unlit_to_restore.append(s)

print(f"Total unlit songs to restore: {len(unlit_to_restore)}")

updates = []
for s in unlit_to_restore:
    u = {
        "id": s["id"],
        "file_path": s["file_path"],
        "is_lit": 1
    }
    if s.get("lrc_path"):
        u["lrc_path"] = s["lrc_path"]
    updates.append(u)

chunk_size = 50
success_cnt = 0

print(f"Sending {len(updates)} updates in chunks of {chunk_size}...")
for i in range(0, len(updates), chunk_size):
    chunk = updates[i:i + chunk_size]
    for retry in range(3):
        try:
            r = sess.post(D1_LIGHT_URL, json={"updates": chunk}, timeout=25)
            if r.status_code == 200:
                success_cnt += len(chunk)
                print(f"  ✅ Restored chunk [{min(i + chunk_size, len(updates))}/{len(updates)}] (Total: {success_cnt})")
                break
            else:
                print(f"  ⚠️ Error {r.status_code}: {r.text}")
        except Exception as e:
            print(f"  ⚠️ Exception: {e}")
            time.sleep(1)

print(f"\nFinished restoring! Total successfully relit: {success_cnt} / {len(updates)}")
