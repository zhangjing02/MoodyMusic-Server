# -*- coding: utf-8 -*-
"""
将 R2 中已存在物理音频但此前未在 D1 点亮的齐秦歌曲毫秒批量点亮
"""
import sys
import os
import sqlite3
import requests

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
DB_PATH = os.path.join(WORKSPACE, 'backend', 'database', 'catalog_sync.db')
D1_LIGHT_URL = 'https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light'

def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, t.r2_mp3_key, t.r2_lrc_key
        FROM songs s
        JOIN artists ar ON s.artist_id = ar.id
        JOIN tracks_sync_state t ON s.id = t.song_id
        WHERE ar.name LIKE '%齐秦%' 
          AND (s.file_path IS NULL OR s.file_path = '')
          AND t.r2_mp3_key IS NOT NULL AND t.r2_mp3_key != ''
    """)
    records = cur.fetchall()
    print(f"📦 发现云端 R2 已有音轨但此前在 D1 留白的齐秦曲目: {len(records)} 首")

    updates = []
    for sid, mp3, lrc in records:
        updates.append({'id': sid, 'file_path': mp3, 'lrc_path': lrc})

    success = 0
    for i in range(0, len(updates), 50):
        batch = updates[i:i+50]
        try:
            r = requests.post(D1_LIGHT_URL, json={'updates': batch}, timeout=15)
            if r.status_code == 200:
                success += len(batch)
                print(f"  ✅ 第 {i//50 + 1} 批成功点亮 {len(batch)} 首至 Cloudflare D1")
            else:
                print(f"  ❌ 第 {i//50 + 1} 批点亮失败: HTTP {r.status_code} {r.text}")
        except Exception as e:
            print(f"  ❌ 网络异常: {e}")

    for sid, mp3, lrc in records:
        cur.execute("UPDATE songs SET file_path = ?, lrc_path = ? WHERE id = ?", (mp3, lrc, sid))
        cur.execute("UPDATE tracks_sync_state SET status = 'D1_LIT' WHERE song_id = ?", (sid,))
    conn.commit()
    conn.close()

    print(f"\n🎉 批量同步完成! 成功为生产端 Cloudflare D1 瞬间点亮 {success} 首已有音轨!")

if __name__ == '__main__':
    run()
