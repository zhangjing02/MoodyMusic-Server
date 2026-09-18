import sqlite3
import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'backend/database/catalog_sync.db'

RENAME_MAP = {
    51: "纯净天然无害",
    53: "挂失",
    57: "左心房",
    23751: "无情的雨无情的你",
    13718: "Memory",
    13677: "Wind Beneath My Wings"
}

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

updates_d1 = []
for sid, new_title in RENAME_MAP.items():
    c.execute("UPDATE tracks_sync_state SET song_title = ? WHERE song_id = ?", (new_title, sid))
    updates_d1.append({"id": sid, "title": new_title})

conn.commit()
conn.close()
print(f"✅ 本地 SQLite 已纠偏 {len(RENAME_MAP)} 首歌曲标题")

try:
    resp = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-update", json={"updates": updates_d1}, timeout=15)
    print("✨ D1 边缘数据库同步状态:", resp.status_code, resp.text)
except Exception as e:
    print("⚠️ D1 异常:", e)
