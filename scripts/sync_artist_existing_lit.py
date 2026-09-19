#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import sqlite3
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
DB_PATH = os.path.join(WORKSPACE, "backend", "database", "catalog_sync.db")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

def sync_artist(artist: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT song_id, r2_mp3_key, r2_lrc_key
        FROM tracks_sync_state
        WHERE artist_name = ? AND status = 'D1_LIT' AND r2_mp3_key IS NOT NULL
    """, (artist,))
    rows = cur.fetchall()
    print(f"🔍 检查歌手【{artist}】已点亮曲目: tracks_sync_state 记录共 {len(rows)} 首")

    valid_updates = []
    
    def check_url(r):
        sid, mp3, lrc = r
        try:
            res = requests.head(mp3, timeout=5)
            if res.status_code == 200:
                return (sid, mp3, lrc)
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(check_url, rows)
        for res in results:
            if res:
                valid_updates.append(res)

    print(f"✅ R2 CDN 物理验证通过: {len(valid_updates)} / {len(rows)} 首")

    if not valid_updates:
        print("未发现有效曲目，退出。")
        conn.close()
        return

    # 1. 本地更新 songs 表
    cur.executemany("""
        UPDATE songs
        SET file_path = ?,
            lrc_path = ?
        WHERE id = ?
    """, [(mp3, lrc, sid) for sid, mp3, lrc in valid_updates])
    conn.commit()
    conn.close()
    print("💾 本地 catalog_sync.db `songs` 表已同步更新！")

    # 2. Cloudflare D1 边缘批量点亮 (每批 50 首)
    chunk_size = 50
    for i in range(0, len(valid_updates), chunk_size):
        chunk = valid_updates[i:i+chunk_size]
        payload = {
            "updates": [{
                "id": sid,
                "file_path": mp3,
                "lrc_path": lrc
            } for sid, mp3, lrc in chunk]
        }
        res = subprocess.run([
            'curl.exe', '-s', '--noproxy', '*', '-X', 'POST', D1_LIGHT_URL,
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(payload, ensure_ascii=False)
        ], capture_output=True, text=True, encoding='utf-8', timeout=15)
        print(f"   • D1 批次 [{i//chunk_size + 1}/{(len(valid_updates)-1)//chunk_size + 1}] 点亮 {len(chunk)} 首: {res.stdout.strip()}")

    print(f"\n🎉 歌手【{artist}】历史已采录音轨共 {len(valid_updates)} 首已全面同步并上线！")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "费玉清"
    sync_artist(target)
