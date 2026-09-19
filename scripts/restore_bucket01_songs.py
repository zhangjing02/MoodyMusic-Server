#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
恢复 Bucket 01 历史所有曲目的点亮状态 (1,623 首)
"""
import sys
import json
import time
import sqlite3
import subprocess

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
            # s['path'] is like 'music/周杰伦/Jay/s_23291.mp3'
            # Extract id
            m = s['path'].split('s_')[-1].split('.')[0]
            if m.isdigit():
                sid = int(m)
                to_restore.append({
                    'id': sid,
                    'file_path': s['path'],
                    'lrc_path': s.get('lrc_path')
                })

print(f"Total songs to restore to Bucket 01: {len(to_restore)}")

def execute_curl_post(url: str, payload: dict) -> bool:
    data_json = json.dumps(payload, ensure_ascii=False)
    for retry in range(3):
        try:
            res = subprocess.run([
                'curl.exe', '-s', '--noproxy', '*', '-X', 'POST', url,
                '-H', 'Content-Type: application/json',
                '-d', data_json
            ], capture_output=True, text=True, encoding='utf-8', timeout=20)
            if '"code":200' in res.stdout or '"code": 200' in res.stdout:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

chunk_size = 50
success_cnt = 0
for i in range(0, len(to_restore), chunk_size):
    chunk = to_restore[i:i + chunk_size]
    payload = {
        "updates": chunk
    }
    if execute_curl_post(D1_LIGHT_URL, payload):
        success_cnt += len(chunk)
        print(f"  • Restored [{i+len(chunk)}/{len(to_restore)}] (Total success: {success_cnt})")
    else:
        print(f"  ❌ Failed chunk at {i}")

print(f"\nSuccessfully restored {success_cnt} / {len(to_restore)} songs to D1!")

# Update local DB
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
for item in to_restore:
    cur.execute("UPDATE songs SET file_path = ?, lrc_path = ? WHERE id = ?", (item['file_path'], item['lrc_path'], item['id']))
    cur.execute("UPDATE tracks_sync_state SET status = 'D1_LIT', r2_mp3_key = ?, r2_lrc_key = ? WHERE song_id = ?", (item['file_path'], item['lrc_path'], item['id']))
conn.commit()
conn.close()
print("Local catalog_sync.db updated!")
