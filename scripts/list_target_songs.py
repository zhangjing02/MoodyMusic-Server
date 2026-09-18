import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'backend/database/catalog_sync.db'
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

TARGET_SONG_IDS = [
    # 薛之谦 无数
    18962,
    # 陈奕迅 不想放手, 68'29", 上五樓的快活
    25476, 1524, 1534, 25546, 25551,
    # 阿杜 哈囉, 第九次初戀
    99, 51, 53, 57,
    # 萧敬腾 IT'S ALL ABOUT LOVE, 蕭敬騰同名專輯
    19173, 24292, 24296,
    # 齐秦 呼唤, 冬雨, 出没, 狼II, 无情的雨无情的你
    23658, 23544, 23725, 23726, 23664, 23667, 23751, 23758,
    # 黄品源 面對品源, 愛你到永遠
    8555, 8523, 8526,
    # 齐豫 TEARS, 花兒不見了, Stories, 誰撿到這張紙條我愛你
    13641, 13677, 13718, 13721, 13711, 13712,
    # 飞儿乐团 Better Life, 飞行部落
    25928, 25930, 25892, 25894, 25895
]

placeholders = ','.join('?' for _ in TARGET_SONG_IDS)
c.execute(f"""
    SELECT song_id, artist_name, album_title, track_index, song_title, status 
    FROM tracks_sync_state 
    WHERE song_id IN ({placeholders})
    ORDER BY artist_name, album_title, track_index
""", TARGET_SONG_IDS)

rows = c.fetchall()
print(f"--- 目标补全歌曲共 {len(rows)} 首 ---")
for r in rows:
    print(f"[{r[0]}] {r[1]} - 《{r[2]}》 #{r[3]} 《{r[4]}》 ({r[5]})")

conn.close()
