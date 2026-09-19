#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
执行纯音乐 (INSTRUMENTAL) 标签标注与误报序曲复原
"""
import sqlite3
import requests
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
REPORT_PATH = os.path.join(BASE_DIR, "reports", "AI_LISTENING_AUDIT_REPORT.json")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

INSTRUMENTAL_KEYWORDS = [
    '纯音乐', '純音樂', '伴奏', 'instrumental', 'intro', 'outro', 'interlude', '序曲', '配乐',
    'ost', 'soundtrack', '原声', 'score', '过场', '片头曲', '片尾曲', '主题音乐', '二胡',
    '古筝', '笛子', '钢琴曲', '吉他独奏', 'theme', 'bgm', 'prelude', 'symphony'
]

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. 恢复刀郎《山歌寥哉》-《序曲》(ID: 5293)
daolang_id = 5293
daolang_url = "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/山歌寥哉/s_5293.mp3"
r = requests.post(D1_LIGHT_URL, json={"updates": [{"id": daolang_id, "file_path": daolang_url, "lrc_path": None}]})
print(f"刀郎《序曲》D1恢复点亮结果: {r.status_code}, {r.text}")

c.execute("UPDATE songs SET file_path = ?, lrc_path = NULL, mood = 'INSTRUMENTAL' WHERE id = ?", (daolang_url, daolang_id))
c.execute("UPDATE tracks_sync_state SET status = 'D1_LIT', r2_mp3_key = ?, r2_lrc_key = NULL WHERE song_id = ?", (daolang_url, daolang_id))
conn.commit()
print("刀郎《序曲》已标记为 INSTRUMENTAL 并恢复点亮")

# 2. 全库检索并标注纯音乐歌曲
tagged_count = 0
c.execute("""
    SELECT s.id, a.name, al.title, s.title
    FROM songs s
    JOIN artists a ON s.artist_id = a.id
    JOIN albums al ON s.album_id = al.id
""")
all_songs = c.fetchall()
inst_ids = []
for sid, art, alb, song in all_songs:
    norm_song = song.lower()
    norm_alb = alb.lower()
    if any(k in norm_song or k in norm_alb for k in INSTRUMENTAL_KEYWORDS):
        inst_ids.append(sid)

for sid in inst_ids:
    c.execute("UPDATE songs SET mood = 'INSTRUMENTAL' WHERE id = ?", (sid,))
conn.commit()
print(f"全库共标注纯音乐/原声配乐 (INSTRUMENTAL): {len(inst_ids)} 首")

# 3. 更新 AI_LISTENING_AUDIT_REPORT.json
if os.path.exists(REPORT_PATH):
    with open(REPORT_PATH, 'r', encoding='utf-8') as f:
        rep = json.load(f)
    
    if daolang_id in rep.get("ai_mismatch_ids", []):
        rep["ai_mismatch_ids"].remove(daolang_id)
        rep["ai_mismatch_detected"] = len(rep["ai_mismatch_ids"])
    
    for item in rep.get("ai_audit_details", []):
        if item.get("id") == daolang_id:
            item["status"] = "INSTRUMENTAL"
            item["reason"] = "37秒纯器乐序曲 (Whisper无声乐前奏自回归幻觉，非错配，已打标签复原)"
            break
            
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print("AI 质检报告已同步更新")
