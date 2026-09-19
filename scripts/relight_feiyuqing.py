import sys
import json
import sqlite3
import subprocess
import os

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
DB_PATH = os.path.join(WORKSPACE, "backend", "database", "catalog_sync.db")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("""
    SELECT id, file_path, lrc_path 
    FROM songs 
    WHERE artist_id = (SELECT id FROM artists WHERE name = '费玉清') 
      AND file_path IS NOT NULL AND file_path != ''
""")
rows = cur.fetchall()
conn.close()

print(f"Total songs to verify on D1: {len(rows)}")

chunk_size = 35
for i in range(0, len(rows), chunk_size):
    chunk = rows[i:i+chunk_size]
    payload = {'updates': [{'id': r[0], 'file_path': r[1], 'lrc_path': r[2]} for r in chunk]}
    success = False
    for attempt in range(3):
        res = subprocess.run([
            'curl.exe', '-s', '--noproxy', '*', '-X', 'POST', D1_LIGHT_URL,
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(payload, ensure_ascii=False)
        ], capture_output=True, text=True, encoding='utf-8', timeout=15)
        if '"code":200' in res.stdout:
            print(f"  Chunk {i//chunk_size + 1}/{(len(rows)-1)//chunk_size + 1} ({len(chunk)} songs): OK")
            success = True
            break
    if not success:
        print(f"  Chunk {i//chunk_size + 1}: FAILED -> {res.stdout.strip() or res.stderr.strip()}")

print("Done!")
