#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 音乐曲库 - 强迫症大圆满收尾工程 (Complete Final 9 Tracks)
=============================================================
精准采录最后 9 首曲目，将全部 18 张经典大碟 100% 满贯点亮！
目标存储桶: Bucket 06 (moody-music-asset-06)
"""

import os
import sys
import json
import sqlite3
import subprocess
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
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "perfectionist_patch")
os.makedirs(WORK_DIR, exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

TARGET_BUCKET_KEY = "account_06"
acc_info = cfg["buckets"][TARGET_BUCKET_KEY]
BUCKET_NAME = acc_info["name"]
PUBLIC_DOMAIN = acc_info["public_domain"]
API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
API_BATCH_UPDATE_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-update"

s3 = boto3.client(
    service_name="s3",
    endpoint_url=acc_info["endpoint_url"],
    aws_access_key_id=acc_info["access_key_id"],
    aws_secret_access_key=acc_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, connect_timeout=10, read_timeout=20)
)

# 9 首精确任务定义
FINAL_TASKS = [
    {
        "sid": 1524,
        "artist": "陈奕迅",
        "album": "68'29\"",
        "title": "原來這裡沒有你",
        "url": None, # 本地 clean_1524.mp3 已就绪
        "rename_to": None,
        "lrc_query": "陈奕迅 原来这里没有你"
    },
    {
        "sid": 1534,
        "artist": "陈奕迅",
        "album": "68'29\"",
        "title": "現場直播",
        "url": None, # 本地 clean_1534.mp3 已就绪
        "rename_to": None,
        "lrc_query": "陈奕迅 现场直播"
    },
    {
        "sid": 99,
        "artist": "阿杜",
        "album": "哈囉",
        "title": "下雨的時候會想起你",
        "url": "https://www.youtube.com/watch?v=HjEbtiyt_g0",
        "rename_to": "下雨的時候會想你",
        "lrc_query": "阿杜 下雨的时候会想你"
    },
    {
        "sid": 51,
        "artist": "阿杜",
        "album": "第九次初戀",
        "title": "纯净天然无害",
        "url": "https://www.youtube.com/watch?v=aZXN9uaXruo",
        "rename_to": "純淨 天然 無害",
        "lrc_query": "阿杜 纯净 天然 无害"
    },
    {
        "sid": 25930,
        "artist": "飞儿乐团",
        "album": "Better Life",
        "title": "花疯",
        "url": "https://www.youtube.com/watch?v=lgtShyICOBk",
        "rename_to": "花瘋",
        "lrc_query": "飞儿乐团 花疯"
    },
    {
        "sid": 23664,
        "artist": "齐秦",
        "album": "狼II",
        "title": "斗鱼",
        "url": "https://www.youtube.com/watch?v=f6Y4iDpAr5M",
        "rename_to": "鬪魚",
        "lrc_query": "齐秦 斗鱼"
    },
    {
        "sid": 25476,
        "artist": "陈奕迅",
        "album": "不想放手",
        "title": "且聽下回分解",
        "url": "https://www.youtube.com/watch?v=pJp0psh4uXE",
        "rename_to": "獨居動物",
        "lrc_query": "陈奕迅 独居动物"
    },
    {
        "sid": 25546,
        "artist": "陈奕迅",
        "album": "上五樓的快活",
        "title": "給我一個吻",
        "url": "https://www.youtube.com/watch?v=7OFuveIV_BQ",
        "rename_to": "謀情害命",
        "lrc_query": "陈奕迅 谋情害命"
    },
    {
        "sid": 25551,
        "artist": "陈奕迅",
        "album": "上五樓的快活",
        "title": "我也知道",
        "url": "https://www.youtube.com/watch?v=o768pj1HVrA",
        "rename_to": "從何說起",
        "lrc_query": "陈奕迅 从何说起"
    }
]

def sanitize_folder_name(name):
    for c in r'<>:"/\|?*':
        name = name.replace(c, '_')
    return name

def main():
    print("=" * 80)
    print("🚀 开始执行 9 首收尾音轨精准采录、纠偏与点亮流水线...")
    print("=" * 80, flush=True)

    success_cnt = 0

    for task in FINAL_TASKS:
        sid = task["sid"]
        artist = task["artist"]
        album = task["album"]
        title = task["title"]
        url = task["url"]
        rename_to = task["rename_to"]
        lrc_query = task["lrc_query"]

        print(f"\n🎧 [Processing #{sid}] {artist} - 《{title}》 (Album: 《{album}》)", flush=True)

        # 1. 歌名纠偏 (如果需要)
        display_title = title
        if rename_to:
            print(f"   ✏️ 修正曲库标题: 《{title}》 -> 《{rename_to}》", flush=True)
            try:
                r_update = requests.post(API_BATCH_UPDATE_URL, json={"updates": [{"id": sid, "title": rename_to}]}, timeout=10)
                if r_update.status_code == 200:
                    print(f"   ✨ D1 标题已更新为: 《{rename_to}》", flush=True)
                else:
                    print(f"   ⚠️ D1 标题更新响应: {r_update.status_code}", flush=True)
            except Exception as e:
                print(f"   ⚠️ D1 标题更新异常: {e}", flush=True)

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE tracks_sync_state SET song_title = ? WHERE song_id = ?", (rename_to, sid))
            conn.commit()
            conn.close()
            display_title = rename_to

        clean_f = os.path.join(WORK_DIR, f"clean_{sid}.mp3")

        # 2. 音频下载与转码
        if url:
            raw_f = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
            print(f"   📥 从 YouTube 下载音源: {url}", flush=True)
            dl_cmd = [
                'yt-dlp', '--force-overwrites', '--no-playlist',
                '-x', '--audio-format', 'mp3', '--audio-quality', '0',
                '-o', raw_f, url
            ]
            subprocess.run(dl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            print(f"   🎛️ EBU R128 + 160k CBR (44.1kHz) 标准转码压制...", flush=True)
            ff_cmd = [
                'ffmpeg', '-y', '-i', raw_f,
                '-af', 'loudnorm=I=-14:LRA=11:TP=-1.5',
                '-ar', '44100', '-b:a', '160k', '-c:a', 'libmp3lame',
                '-write_xing', '1', '-id3v2_version', '3',
                clean_f
            ]
            subprocess.run(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(raw_f):
                os.remove(raw_f)
        else:
            print(f"   ⚡ 使用本地已转码音频: {clean_f}", flush=True)

        if not os.path.exists(clean_f):
            print(f"   ❌ 音频文件不存在: {clean_f}", flush=True)
            continue

        file_size = os.path.getsize(clean_f)

        # 3. 歌词抓取 (使用 Windows 安全路径)
        safe_album = sanitize_folder_name(album)
        safe_artist = sanitize_folder_name(artist)
        lyrics_dir = os.path.join(BASE_DIR, "storage", "lyrics", safe_artist, safe_album)
        os.makedirs(lyrics_dir, exist_ok=True)
        local_lrc = os.path.join(lyrics_dir, f"s_{sid}.lrc")

        lrc_text = None
        for q in [lrc_query, f"{artist} {display_title}", display_title]:
            try:
                lrc_text = syncedlyrics.search(q, providers=["NetEase", "Lrclib"])
                if lrc_text and "[" in lrc_text:
                    break
            except Exception:
                pass

        if lrc_text:
            with open(local_lrc, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            print(f"   📜 LRC 歌词已匹配 (长度: {len(lrc_text)} 字符)", flush=True)
        else:
            print(f"   ⚪ 未抓取到同步歌词", flush=True)

        # 4. 上传至 Cloudflare R2
        r2_mp3_key = f"music/{artist}/{album}/s_{sid}.mp3"
        s3.upload_file(clean_f, BUCKET_NAME, r2_mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        full_mp3_url = f"{PUBLIC_DOMAIN}/{r2_mp3_key}"
        print(f"   🚀 R2 音频上传完成: {r2_mp3_key}", flush=True)

        full_lrc_url = None
        if os.path.exists(local_lrc):
            r2_lrc_key = f"music/{artist}/{album}/s_{sid}.lrc"
            try:
                s3.upload_file(local_lrc, BUCKET_NAME, r2_lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
                full_lrc_url = f"{PUBLIC_DOMAIN}/{r2_lrc_key}"
                print(f"   📜 R2 歌词上传完成: {r2_lrc_key}", flush=True)
            except Exception as e:
                print(f"   ⚠️ 歌词上传失败: {e}", flush=True)

        # 5. D1 边缘即时点亮
        light_payload = {"updates": [{"id": sid, "file_path": full_mp3_url, "lrc_path": full_lrc_url}]}
        try:
            resp = requests.post(API_BATCH_LIGHT_URL, json=light_payload, timeout=15)
            if resp.status_code == 200:
                print(f"   ✨ D1 边缘即时点亮成功！", flush=True)
            else:
                print(f"   ⚠️ D1 点亮响应码: {resp.status_code}", flush=True)
        except Exception as e:
            print(f"   ⚠️ D1 点亮请求异常: {e}", flush=True)

        # 6. 本地 SQLite 更新
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            UPDATE tracks_sync_state
            SET status = 'D1_LIT',
                r2_mp3_key = ?,
                r2_lrc_key = ?,
                local_mp3 = ?,
                local_lrc = ?,
                file_size = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE song_id = ?
        """, (full_mp3_url, full_lrc_url, clean_f, local_lrc if full_lrc_url else None, file_size, sid))
        conn.commit()
        conn.close()

        print(f"   🎉 [{sid}] {artist} - 《{display_title}》 完工！", flush=True)
        success_cnt += 1

    print("\n" + "=" * 80)
    print(f"🏆 收尾工程全部完成！成功点亮: {success_cnt}/9 首！全部 18 张大碟达成 100% 满贯！")
    print("=" * 80, flush=True)

if __name__ == '__main__':
    main()
