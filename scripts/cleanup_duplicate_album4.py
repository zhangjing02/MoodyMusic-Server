#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 音乐曲库 - 清理阿杜重复专辑 (Album 4) 并为正规专辑 (Album 3) 补全歌词
=============================================================================
1. 为 Album 3 《第9次初恋》 (ID 38-47) 抓取并上传 10 首 LRC 歌词，秒级点亮 D1；
2. 调用 D1 接口物理删除英文机翻重复专辑 Album 4 (album_id: 4)；
3. 同步清理本地 SQLite catalog_sync.db；
4. 验证清理后的阿杜大碟列表。
"""

import os
import sys
import json
import sqlite3
import requests
import boto3
from botocore.config import Config
import syncedlyrics

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

TARGET_BUCKET_KEY = "account_06"
acc_info = cfg["buckets"][TARGET_BUCKET_KEY]
BUCKET_NAME = acc_info["name"]
PUBLIC_DOMAIN = acc_info["public_domain"]

API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
API_ALBUM_DELETE_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/delete"

s3 = boto3.client(
    service_name="s3",
    endpoint_url=acc_info["endpoint_url"],
    aws_access_key_id=acc_info["access_key_id"],
    aws_secret_access_key=acc_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, connect_timeout=10, read_timeout=20)
)

ALBUM3_SONGS = [
    (38, "几年了"),
    (39, "Valentine's Day"),
    (40, "再唱一首"),
    (41, "第九次初恋"),
    (42, "纯净 天然 无害"),
    (43, "宠爱"),
    (44, "离开我的自由"),
    (45, "不提"),
    (46, "左心房"),
    (47, "挂失")
]

def main():
    print("=" * 80)
    print("🛠️ 开始执行阿杜重复专辑 (Album 4) 清理与正规专辑 (Album 3) 歌词升级...")
    print("=" * 80)

    # 1. 抓取与补全 Album 3 歌词
    lyrics_dir = os.path.join(BASE_DIR, "storage", "lyrics", "阿杜", "第9次初恋")
    os.makedirs(lyrics_dir, exist_ok=True)

    light_updates = []
    print("\n📜 正在为 Album 3 《第9次初恋》 检索与上传 10 首 LRC 同步歌词:")
    for sid, title in ALBUM3_SONGS:
        local_lrc = os.path.join(lyrics_dir, f"s_{sid}.lrc")
        lrc_text = None
        
        # 尝试检索
        queries = [f"阿杜 {title}", title]
        for q in queries:
            try:
                lrc_text = syncedlyrics.search(q, providers=["NetEase", "Lrclib"])
                if lrc_text and "[" in lrc_text:
                    break
            except Exception:
                pass

        full_lrc_url = None
        if lrc_text:
            with open(local_lrc, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            r2_lrc_key = f"music/阿杜/第9次初恋/s_{sid}.lrc"
            try:
                s3.upload_file(local_lrc, BUCKET_NAME, r2_lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
                full_lrc_url = f"{PUBLIC_DOMAIN}/{r2_lrc_key}"
                print(f"  ✅ [{sid}] 《{title}》 歌词上传完成: {r2_lrc_key}")
            except Exception as e:
                print(f"  ⚠️ [{sid}] 歌词上传异常: {e}")
        else:
            print(f"  ⚪ [{sid}] 《{title}》 未命中歌词")

        # 获取已有音频路径保持不变
        # 从 D1 查询已有点亮音频
        det = requests.get(f"https://m-api.changgepd.ccwu.cc/api/admin/albums/detail?album_id=3", timeout=10).json().get("data", {})
        existing_songs = {s["id"]: s.get("file_path") for s in det.get("songs", [])}
        file_path = existing_songs.get(sid)

        if file_path:
            light_updates.append({"id": sid, "file_path": file_path, "lrc_path": full_lrc_url})

    if light_updates:
        resp = requests.post(API_BATCH_LIGHT_URL, json={"updates": light_updates}, timeout=15)
        print(f"✨ D1 batch-light 响应: {resp.status_code} - 成功注入 {len(light_updates)} 首歌词！")

    # 2. 调用 D1 删除 Album 4 (英文机翻重复大碟)
    print("\n🗑️ 正在通过 D1 接口物理删除英文机翻重复专辑 Album 4 (id: 4)...")
    del_resp = requests.post(API_ALBUM_DELETE_URL, json={"album_id": 4}, timeout=15)
    print(f"D1 删除响应 ({del_resp.status_code}):", del_resp.text)

    # 3. 清理本地 SQLite
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 删除本地 48-57 的旧记录
    del_ids = [48, 49, 50, 51, 52, 53, 54, 55, 56, 57]
    placeholders = ','.join('?' for _ in del_ids)
    c.execute(f"DELETE FROM tracks_sync_state WHERE song_id IN ({placeholders})", del_ids)
    deleted_local = c.rowcount
    conn.commit()
    conn.close()
    print(f"📁 本地 SQLite catalog_sync.db 同步清除 {deleted_local} 条重复音轨记录。")

    # 4. 验证阿杜全专辑列表
    print("\n🔍 验证清理后阿杜在 D1 的专辑全貌:")
    search_url = "https://m-api.changgepd.ccwu.cc/api/admin/albums/search?artist_id=1"
    r = requests.get(search_url, timeout=10).json()
    albums = r.get("data", {}).get("albums", [])
    print(f"阿杜当前正规大碟数量: {len(albums)} 张")
    for a in sorted(albums, key=lambda x: x.get('release_date', '')):
        print(f"  🎵 [{a['id']}] 《{a['title']}》 ({a.get('release_date')}) - {a.get('song_count')} 首")

    print("\n" + "=" * 80)
    print("🎉 重复专辑清理与歌词补齐完毕！列表恢复干净整洁！")
    print("=" * 80)

if __name__ == '__main__':
    main()
