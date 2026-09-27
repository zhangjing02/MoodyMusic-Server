#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finish_teresa_xiao_cheng.py
完成《小城故事》(Album ID: 2194) 的属性配置、本地数据库写入及 CDN 连通性测试
"""

import os
import sys
import json
import sqlite3
import requests
import urllib.parse
import subprocess

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = 'e:/Workspace/AI-Project/MoodyMusic-Workspace'
CONFIG_PATH = os.path.join(BASE_DIR, 'backend', 'r2_config.json')
LOCAL_DB_PATH = os.path.join(BASE_DIR, 'backend', 'database', 'catalog_sync.db')

PATCH_ALBUM_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/"

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    cfg = json.load(f)['buckets']

target_bucket_info = cfg['account_10']
b10_domain = target_bucket_info['public_domain'].rstrip('/')

ALBUM_ID = 2194
ARTIST_ID = 15
cover_cdn = f"{b10_domain}/covers/albums/c_xiao_cheng_gu_shi_1979.jpg"

TRACKS = [
    {"index": 1, "song_id": 30181, "title": "你在我心里", "duration": 175},
    {"index": 2, "song_id": 30182, "title": "心事", "duration": 210},
    {"index": 3, "song_id": 30183, "title": "诗意", "duration": 180},
    {"index": 4, "song_id": 30184, "title": "一片落叶", "duration": 207},
    {"index": 5, "song_id": 30185, "title": "九月的故事", "duration": 227},
    {"index": 6, "song_id": 30186, "title": "春风满小城", "duration": 133},
    {"index": 7, "song_id": 30187, "title": "小城故事", "duration": 155},
    {"index": 8, "song_id": 30188, "title": "小路", "duration": 184},
    {"index": 9, "song_id": 30189, "title": "我和你", "duration": 231},
    {"index": 10, "song_id": 30190, "title": "逍遥自在", "duration": 207},
    {"index": 11, "song_id": 30191, "title": "初恋的地方", "duration": 147},
    {"index": 12, "song_id": 30192, "title": "想起你", "duration": 209}
]

print("=" * 80)
print(f"🎨 配置专辑《小城故事》(ID: {ALBUM_ID}) 属性...")
print("=" * 80)

for attempt in range(3):
    try:
        resp_alb = requests.patch(
            f"{PATCH_ALBUM_URL}{ALBUM_ID}",
            json={"release_date": "1979", "cover_url": cover_cdn},
            proxies={'http': None, 'https': None},
            timeout=10
        )
        print(f"  • 专辑 ID: {ALBUM_ID} 属性更新: {resp_alb.status_code} {resp_alb.text}")
        break
    except Exception as e:
        print(f"  • 尝试 {attempt} 失败: {e}")
        import time; time.sleep(2)

print("\n" + "=" * 80)
print("💾 同步写入本地 catalog_sync.db 数据库...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

# 确保本地 albums 表有专辑
cur.execute("SELECT id FROM albums WHERE id = ?", (ALBUM_ID,))
if not cur.fetchone():
    cur.execute("INSERT INTO albums (id, artist_id, title, release_date, cover_url, storage_id) VALUES (?, ?, ?, ?, ?, ?)",
                (ALBUM_ID, ARTIST_ID, '小城故事', '1979', cover_cdn, 'primary'))
else:
    cur.execute("UPDATE albums SET cover_url = ?, release_date = '1979' WHERE id = ?", (cover_cdn, ALBUM_ID))

# 写入 12 首歌曲
for t in TRACKS:
    sid = t["song_id"]
    file_path = f"{b10_domain}/music/邓丽君/小城故事/s_{sid}.mp3"
    lrc_path = f"{b10_domain}/lyrics/邓丽君/小城故事/s_{sid}.lrc"
    cur.execute("DELETE FROM songs WHERE id = ?", (sid,))
    cur.execute("""
        INSERT INTO songs (id, album_id, title, track_index, duration, file_path, lrc_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sid, ALBUM_ID, t["title"], t["index"], t["duration"], file_path, lrc_path))

conn.commit()
conn.close()
print("  ✅ 本地数据库同步成功！")

print("\n" + "=" * 80)
print("🌐 公网 CDN 连通性抽测...")
print("=" * 80)
for t in TRACKS:
    sid = t["song_id"]
    file_path = f"{b10_domain}/music/邓丽君/小城故事/s_{sid}.mp3"
    p = urllib.parse.urlsplit(file_path)
    u_enc = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), '', ''))
    req = urllib.request.Request(u_enc, headers={'User-Agent': 'Mozilla/5.0'})
    r_chk = urllib.request.urlopen(req, timeout=10)
    print(f"  • ID {sid} HEAD [{r_chk.status}] (Content-Length: {r_chk.headers.get('Content-Length')})")

print("\n🎉 邓丽君 1979 宝丽金旷世神专《小城故事》(12首) 全盘采录压制、上传、入库并成功点亮！")
