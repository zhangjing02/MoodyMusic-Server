import sqlite3
import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'backend/database/catalog_sync.db'
D1_BATCH_UPDATE_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-update"

TITLE_MAP = {
    390: ("猶豫 (超越時代紀念版)", "Amani"),
    391: ("猶豫 (超越時代紀念版)", "坚持信念"),
    392: ("猶豫 (超越時代紀念版)", "不再犹豫"),
    393: ("猶豫 (超越時代紀念版)", "係要聽ROCK N' ROLL"),
    394: ("猶豫 (超越時代紀念版)", "我早应该习惯"),
    395: ("猶豫 (超越時代紀念版)", "谁伴我闯荡"),
    396: ("猶豫 (超越時代紀念版)", "高温派对"),
    397: ("猶豫 (超越時代紀念版)", "谁来主宰"),
    398: ("猶豫 (超越時代紀念版)", "爱你一切"),
    399: ("猶豫 (超越時代紀念版)", "完全的拥有"),
    400: ("猶豫 (超越時代紀念版)", "你知道我的迷惘 (Live)"),
    401: ("猶豫 (超越時代紀念版)", "岁月无声 (Live)"),
    402: ("猶豫 (超越時代紀念版)", "漆黑的空间 (Live)"),
    403: ("猶豫 (超越時代紀念版)", "怀念你 (Live)"),
    404: ("猶豫 (超越時代紀念版)", "和自己的心比赛 (Live)"),
    405: ("猶豫 (超越時代紀念版)", "撒旦的咒语 (Live)"),
    406: ("猶豫 (超越時代紀念版)", "不需要太懂 (Live)"),
    407: ("猶豫 (超越時代紀念版)", "光辉岁月 (国语) (Live)"),
    408: ("猶豫 (超越時代紀念版)", "大地 (国语) (Live)"),
    409: ("猶豫 (超越時代紀念版)", "午夜怨曲 (国语) (Live)"),
    410: ("猶豫 (超越時代紀念版)", "漆黑的空间"),
    411: ("猶豫 (超越時代紀念版)", "光辉岁月 (国语)"),
    412: ("猶豫 (超越時代紀念版)", "大地"),
    413: ("猶豫 (超越時代紀念版)", "午夜怨曲 (国语)"),
    414: ("猶豫 (超越時代紀念版)", "撒旦的咒语"),
    415: ("猶豫 (超越時代紀念版)", "岁月无声"),
    416: ("猶豫 (超越時代紀念版)", "怀念你，忘记你"),
    504: ("猶豫", "Amani"),
    505: ("猶豫", "坚持信念"),
    506: ("猶豫", "不再犹豫"),
    507: ("猶豫", "係要聽ROCK N' ROLL"),
    508: ("猶豫", "我早应该习惯"),
    509: ("猶豫", "谁伴我闯荡"),
    510: ("猶豫", "高温派对"),
    511: ("猶豫", "谁来主宰"),
    512: ("猶豫", "爱你一切"),
    513: ("猶豫", "完全的拥有")
}

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

updates_d1 = []
for sid, (alb, tit) in TITLE_MAP.items():
    c.execute("UPDATE tracks_sync_state SET song_title = ?, album_title = ? WHERE song_id = ?", (tit, alb, sid))
    updates_d1.append({
        "id": sid,
        "title": tit,
        "album_title": alb
    })

conn.commit()
conn.close()
print(f"✅ 本地 SQLite 中 {len(TITLE_MAP)} 首 Beyond 歌曲已更新为中文标题与专辑名")

try:
    resp = requests.post(D1_BATCH_UPDATE_URL, json={"updates": updates_d1}, timeout=15)
    if resp.status_code == 200:
        print(f"✨ Cloudflare D1 边缘数据库已同步更新 {len(updates_d1)} 首 Beyond 歌曲骨架为中文！")
    else:
        print(f"⚠️ D1 返回状态码 {resp.status_code}: {resp.text}")
except Exception as e:
    print(f"⚠️ D1 同步异常: {e}")
