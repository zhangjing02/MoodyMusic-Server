import sqlite3
import sys
import requests

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'backend/database/catalog_sync.db'
D1_BATCH_UPDATE_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-update"

HPY_REMAINING = {
    # 感謝 情人
    8319: "情人款款",
    8320: "孤鸟",
    8321: "放长假",
    8322: "对!就是你",
    8323: "少年悍将",
    8324: "写给你的歌",
    8325: "错觉",
    8326: "别怕",
    8327: "你教我的事",
    8328: "感谢",
    8329: "风中的花",
    
    # 愛情香
    8460: "相逢",
    8461: "没有地址的信",
    8462: "把爱给我",
    8463: "秘密收藏",
    8464: "你怎么舍得我难过",
    8465: "树的记忆",
    8466: "难释怀",
    
    # 新年快樂
    8498: "没有回来的女人",
    8499: "新年快乐",
    8500: "最美的梦最痛的梦",
    8501: "你还爱我吗",
    8502: "站在你的身边",
    8503: "春风",
    8505: "心中所爱的人",
    8506: "半夜的路灯",
    8507: "好久不见",
    
    # 候鳥 五月天電影音樂作品
    8394: "罗密欧与茱丽叶",
    8395: "像烟火",
    8396: "候鸟",
    8398: "左键 (网络男欢女爱)",
    8401: "公路电影",
    8402: "盛开"
}

conn = sqlite3.connect(DB_PATH, timeout=30.0)
c = conn.cursor()

updates_d1 = []
for sid, tit in HPY_REMAINING.items():
    c.execute("UPDATE tracks_sync_state SET song_title = ?, status = 'PENDING' WHERE song_id = ?", (tit, sid))
    updates_d1.append({"id": sid, "title": tit})

conn.commit()
conn.close()
print(f"✅ 本地 SQLite 中 {len(HPY_REMAINING)} 首黄品源英文曲名已纠偏为中文，并重置为 PENDING！")

# 同步 D1
try:
    resp = requests.post(D1_BATCH_UPDATE_URL, json={"updates": updates_d1}, timeout=15)
    print(f"✨ Cloudflare D1 边缘更新状态: {resp.status_code}")
except Exception as e:
    print(f"⚠️ D1 同步异常: {e}")
