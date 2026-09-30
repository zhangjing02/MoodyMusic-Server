#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import urllib.parse
import requests

API_BASE = "https://m-api.changgepd.ccwu.cc"
PUBLIC_BASE = "https://pub-c570096b51724b82ab294c0381b0f1c3.r2.dev"
ARTIST = urllib.parse.quote("蒙面唱将猜猜猜")
ALBUM = urllib.parse.quote("第一季 (2015)")

session = requests.Session()
session.trust_env = False

song_ids = [27645, 27646, 27647, 27648, 27649, 27650, 31143, 31144, 31145, 31146, 31147, 31148]

updates = []
for sid in song_ids:
    mp3_url = f"{PUBLIC_BASE}/music/{ARTIST}/{ALBUM}/s_{sid}.mp3"
    lrc_url = f"{PUBLIC_BASE}/lyrics/{ARTIST}/{ALBUM}/s_{sid}.lrc"
    updates.append({
        "id": sid,
        "file_path": mp3_url,
        "lrc_path": lrc_url
    })

print(f"⚡ 提交 D1 batch-light (共 {len(updates)} 首)...")
for attempt in range(3):
    try:
        r = session.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": updates}, timeout=35)
        print("batch-light 响应:", r.status_code, r.text)
        if r.status_code == 200:
            break
    except Exception as e:
        print(f"尝试 {attempt+1} 异常: {e}")

print("\n" + "=" * 80)
print("🔍 终验第一季 12 首生产环境 HTTP HEAD...")
print("=" * 80)
all_pass = True
for u in updates:
    r_m = session.head(u["file_path"], timeout=10)
    r_l = session.head(u["lrc_path"], timeout=10)
    ok = (r_m.status_code == 200 and r_l.status_code == 200)
    print(f"ID {u['id']} | MP3: {r_m.status_code} ({r_m.headers.get('Content-Length')}B) | LRC: {r_l.status_code} ({r_l.headers.get('Content-Length')}B) | {'✅' if ok else '❌'}")
    if not ok:
        all_pass = False

print("\n结果:", "🎉 全部 100% PASS!" if all_pass else "❌ 有失败项")
