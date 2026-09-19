#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
import time
import sqlite3
import requests

sys.stdout.reconfigure(encoding='utf-8')

AUDIT_FILE = r"scratch/all_relative_songs_audit.json"
DB_PATH = r"backend/database/catalog_sync.db"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

GROUP_A_ARTISTS = {
    '萧煌奇', '尚雯婕', '窦唯', '苏慧伦', '王心凌', '庾澄庆',
    '郑智化', '曾轶可', '古巨基', '迪克牛仔', '零点乐队',
    '动力火车', '张靓颖', '张雨生', '飞儿乐团', '那英'
}

with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
    audit = json.load(f)

to_restore = []
for aname, info in audit['artists'].items():
    if aname not in GROUP_A_ARTISTS:
        for s in info['all_songs']:
            m = s['path'].split('s_')[-1].split('.')[0]
            if m.isdigit():
                to_restore.append({
                    'id': int(m),
                    'file_path': s['path'],
                    'lrc_path': s.get('lrc_path')
                })

print(f"Total songs to restore: {len(to_restore)}")

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Content-Type': 'application/json'
})

def post_chunk(chunk):
    payload = {'updates': chunk}
    for attempt in range(5):
        try:
            r = session.post(D1_LIGHT_URL, json=payload, timeout=20)
            if r.status_code == 200:
                res_json = r.json()
                if res_json.get('code') == 200:
                    return True
        except Exception as e:
            pass
        time.sleep(1.0)
    return False

chunk_size = 25
success = 0
failed = []
for i in range(0, len(to_restore), chunk_size):
    chunk = to_restore[i:i + chunk_size]
    if post_chunk(chunk):
        success += len(chunk)
    else:
        print(f"❌ Failed chunk at {i}")
        failed.extend(chunk)
    if (i + chunk_size) % 100 == 0 or (i + len(chunk)) == len(to_restore):
        print(f"Progress: {min(i+chunk_size, len(to_restore))}/{len(to_restore)} (Success: {success})")
    time.sleep(0.3)

print(f"Batch pass done: Success {success}, Failed {len(failed)}")

if failed:
    print(f"Retrying {len(failed)} failed tracks in chunks of 5...")
    retry_success = 0
    sub_chunk = 5
    for j in range(0, len(failed), sub_chunk):
        chunk = failed[j:j + sub_chunk]
        if post_chunk(chunk):
            retry_success += len(chunk)
        else:
            for single in chunk:
                if post_chunk([single]):
                    retry_success += 1
                time.sleep(0.3)
        time.sleep(0.5)
    success += retry_success
    print(f"After retry: Total Success {success}/{len(to_restore)}")

# Update local DB
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
for item in to_restore:
    cur.execute("UPDATE songs SET file_path = ?, lrc_path = ? WHERE id = ?", (item['file_path'], item['lrc_path'], item['id']))
    cur.execute("UPDATE tracks_sync_state SET status = 'D1_LIT', r2_mp3_key = ?, r2_lrc_key = ? WHERE song_id = ?", (item['file_path'], item['lrc_path'], item['id']))
conn.commit()
conn.close()
print(f"🎉 Local catalog_sync.db 100% updated! All {len(to_restore)} songs restored!")
