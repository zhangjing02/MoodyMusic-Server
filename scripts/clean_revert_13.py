import sqlite3
import subprocess
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# The 13 contaminated tracks to revert to their original baseline in stage1
revert_map = {
    8531: ("https://pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev/music/黄品源/愛你到永遠/s_8531.mp3", None),
    8072: ("https://pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev/music/黄小琥/放縱玫瑰/s_8072.mp3", None),
    8084: ("https://pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev/music/黄小琥/Fang Zong Mei Gui/s_8084.mp3", None),
    14227: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/容祖儿/Me, Re-Do (Deluxe Version)/s_14227.mp3", None),
    14730: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/容祖儿/Something About You/s_14730.mp3", None),
    14283: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/容祖儿/小日子 (特別版)/s_14283.mp3", None),
    14575: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/容祖儿/Bi-Heart/s_14575.mp3", None),
    22549: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/周华健/小天堂/s_22549.mp3", None),
    22566: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/周华健/生‧生活/s_22566.mp3", None),
    23750: ("https://pub-e7d069eb11954440aeb32012e8e3c670.r2.dev/music/齐秦/无情的雨无情的你/s_23750.mp3", None),
    22244: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/周华健/水滸三部曲 (原創音樂選輯)/s_22244.mp3", None),
    22248: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/周华健/水滸三部曲 (原創音樂選輯)/s_22248.mp3", None),
    22254: ("https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/周华健/水滸三部曲 (原創音樂選輯)/s_22254.mp3", None),
}

conn = sqlite3.connect('backend/database/catalog_sync.db')
cur = conn.cursor()

print("1. 正在还原本地 catalog_sync.db ...")
for sid, (url, dur) in revert_map.items():
    cur.execute("UPDATE songs SET file_path = ?, duration = ? WHERE id = ?", (url, dur, sid))
conn.commit()
print("   本地 DB 还原完成！")

print("2. 正在还原远端 Cloudflare D1 ...")
sql_stmts = []
for sid, (url, dur) in revert_map.items():
    dur_sql = "NULL" if dur is None else str(dur)
    sql_stmts.append(f"UPDATE songs SET file_path = '{url}', duration = {dur_sql} WHERE id = {sid};")

combined_sql = " ".join(sql_stmts)
cmd_d1 = [
    'npx', 'wrangler', 'd1', 'execute', 'moody-d1-test', '--remote',
    f"--command={combined_sql}"
]
res = subprocess.run(cmd_d1, cwd='backend', capture_output=True, shell=True)
print("   D1 还原完成，状态码:", res.returncode)

print("3. 正在更新 remediate_progress.json ...")
with open('backend/scripts/remediate_progress.json', 'r', encoding='utf-8') as f:
    prog = json.load(f)

# Keep only genuinely remediated (>60s) in completed
bad_set = set(revert_map.keys())
clean_completed = [x for x in prog.get('completed', []) if x not in bad_set]
prog['completed'] = clean_completed

with open('backend/scripts/remediate_progress.json', 'w', encoding='utf-8') as f:
    json.dump(prog, f, ensure_ascii=False, indent=2)

print(f"   最终核实纯净正版已修复总数: {len(clean_completed)} 首！")
