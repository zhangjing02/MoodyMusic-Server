import sqlite3
import requests
import json
import os
import sys
import boto3
from botocore.config import Config
import syncedlyrics

sys.stdout.reconfigure(encoding='utf-8')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

# 使用当前活跃的 Bucket 06
acc_info = cfg["buckets"]["account_06"]
s3 = boto3.client(
    service_name="s3",
    endpoint_url=acc_info["endpoint_url"],
    aws_access_key_id=acc_info["access_key_id"],
    aws_secret_access_key=acc_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, connect_timeout=10, read_timeout=20)
)
BUCKET_NAME = acc_info["name"]
PUBLIC_DOMAIN = acc_info["public_domain"]

TIANHEI_SONGS = [
    (108, "他一定很愛你"),
    (109, "天黑"),
    (110, "天天看到你"),
    (111, "一個人住"),
    (112, "Andy"),
    (113, "撕夜"),
    (114, "無法阻擋"),
    (115, "你很好"),
    (116, "離別"),
    (117, "Right Here Waiting")
]

lyrics_dir = os.path.join(BASE_DIR, "storage", "lyrics", "阿杜", "天黑")
os.makedirs(lyrics_dir, exist_ok=True)

d1_updates = []

for sid, title in TIANHEI_SONGS:
    print(f"🎵 正在检索阿杜 - 《{title}》 LRC 歌词...")
    lrc_text = None
    queries = [f"阿杜 {title}", f"A-Do {title}", title]
    for q in queries:
        try:
            lrc_text = syncedlyrics.search(q, providers=["NetEase", "Lrclib"])
            if lrc_text and "[" in lrc_text:
                print(f"   ✅ 找到歌词 (Query: '{q}')")
                break
        except Exception:
            pass
            
    if lrc_text:
        lrc_file = os.path.join(lyrics_dir, f"s_{sid}.lrc")
        with open(lrc_file, "w", encoding="utf-8") as f:
            f.write(lrc_text)
            
        r2_key = f"music/阿杜/天黑/s_{sid}.lrc"
        s3.upload_file(lrc_file, BUCKET_NAME, r2_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        full_lrc_url = f"{PUBLIC_DOMAIN}/{r2_key}"
        print(f"   🚀 LRC 已上传至 Bucket 06: {full_lrc_url}")
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT r2_mp3_key FROM tracks_sync_state WHERE song_id = ?", (sid,))
        mp3_url = c.fetchone()[0]
        c.execute("UPDATE tracks_sync_state SET r2_lrc_key = ?, local_lrc = ? WHERE song_id = ?", (full_lrc_url, lrc_file, sid))
        conn.commit()
        conn.close()
        
        d1_updates.append({
            "id": sid,
            "url": mp3_url,
            "lrc_path": full_lrc_url,
            "status": "active"
        })

if d1_updates:
    print(f"\n✨ 正在将 {len(d1_updates)} 首阿杜《天黑》的 LRC 歌词秒级同步到 Cloudflare D1...")
    resp = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json={"songs": d1_updates}, timeout=15)
    print("D1 响应:", resp.status_code, resp.text)

print("🎉 阿杜《天黑》专辑歌词补齐完毕！")
