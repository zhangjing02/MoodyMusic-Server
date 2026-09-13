#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 张学友《Smile》经典首张大碟正版音源与歌词自动化流水线
(Jacky Cheung Smile Album Pipeline)

功能：
1. 抓取张学友 1985 年首张专辑《Smile》全部 11 首真实音频 (160k 立体声)
2. 抓取高精度带时间轴 LRC 歌词
3. 直传至 Cloudflare R2 (moody-music-asset-02)
4. 调用 batch-light 彻底纠正云端被错配绑定的周杰伦/蔡依林音频与歌词
5. 纳管至本地 catalog_sync.db
"""

import os
import sys
import re
import time
import json
import sqlite3
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
TEMP_DIR = os.path.join(BASE_DIR, "downloads", "jacky_smile_temp")
os.makedirs(TEMP_DIR, exist_ok=True)

API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
R2_DEV_PREFIX = "https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/"

NODE_PATH = r"D:\DevelopeTools\Node\node.exe" if os.path.exists(r"D:\DevelopeTools\Node\node.exe") else "node"
JS_RUNTIME_ARG = f"node:{NODE_PATH}"

JACKY_SMILE_TRACKS = [
    (27661, "轻抚你的脸", 1),
    (27657, "爱的卡帮", 2),
    (27663, "丝丝记忆", 3),
    (27660, "局外人", 4),
    (27658, "怀抱的您", 5),
    (27664, "甜梦", 6),
    (27662, "情已逝", 7),
    (27666, "造梦者", 8),
    (27665, "温柔", 9),
    (27659, "交叉算了", 10),
    (27656, "Smile Again 玛莉亚", 11)
]

def get_r2_client():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    b_info = cfg["buckets"]["account_02"]
    s3 = boto3.client(
        service_name="s3",
        endpoint_url=b_info["endpoint_url"],
        aws_access_key_id=b_info["access_key_id"],
        aws_secret_access_key=b_info["secret_access_key"],
        region_name="auto",
        config=Config(s3={"addressing_style": "path"})
    )
    return s3, b_info["name"]

def fetch_lrc_jacky(title: str) -> str | None:
    for q in [f"张学友 {title}", f"張學友 {title}", title]:
        try:
            lrc = syncedlyrics.search(q, providers=['NetEase', 'Lrclib'])
            if lrc and len(lrc) > 80 and '[' in lrc and ':' in lrc:
                return lrc
        except Exception:
            pass
        time.sleep(0.2)
    return None

def download_audio_jacky(title: str, out_mp3_path: str) -> bool:
    query = f"张学友 {title}"
    cmd_search = [
        "yt-dlp",
        "--encoding", "utf-8",
        "--js-runtimes", JS_RUNTIME_ARG,
        "--print", "%(id)s | %(title)s | %(duration)s",
        f"ytsearch4:{query}"
    ]
    try:
        proc = subprocess.run(cmd_search, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', check=True)
        lines = proc.stdout.strip().splitlines()
    except Exception as e:
        print(f"    ❌ yt-dlp 搜索失败: {e}")
        return False

    best_video_id = None
    for line in lines:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 3:
            vid, vtitle, vdur = parts[0], parts[1], parts[2]
            try:
                dur_sec = float(vdur)
            except Exception:
                dur_sec = 0
            if 90 <= dur_sec <= 420:
                best_video_id = vid
                break
                
    if not best_video_id and lines:
        best_video_id = lines[0].split('|')[0].strip()

    if not best_video_id:
        print(f"    ⚠️ 未找到候选视频")
        return False

    temp_download_template = os.path.join(TEMP_DIR, f"temp_{best_video_id}.%(ext)s")
    cmd_dl = [
        "yt-dlp",
        "--encoding", "utf-8",
        "--js-runtimes", JS_RUNTIME_ARG,
        "-f", "bestaudio/best",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "160K",
        "-o", temp_download_template,
        f"https://www.youtube.com/watch?v={best_video_id}"
    ]
    try:
        subprocess.run(cmd_dl, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        expected_mp3 = os.path.join(TEMP_DIR, f"temp_{best_video_id}.mp3")
        if os.path.exists(expected_mp3) and os.path.getsize(expected_mp3) > 100 * 1024:
            if os.path.exists(out_mp3_path):
                os.remove(out_mp3_path)
            os.rename(expected_mp3, out_mp3_path)
            return True
    except Exception as e:
        print(f"    ❌ 下载/转码异常: {e}")

    return False

def run():
    print("=" * 80)
    print("🚀 MOODY - 张学友《Smile》专辑真实音频与歌词纠偏流水线启动")
    print("=" * 80)

    s3_client, bucket_name = get_r2_client()
    print(f"☁️ R2 目标存储桶: {bucket_name}")
    
    success_list = []
    failed_list = []
    
    total = len(JACKY_SMILE_TRACKS)
    album = "Smile"
    
    for idx, (song_id, title, track_index) in enumerate(JACKY_SMILE_TRACKS, 1):
        print(f"\n[{idx}/{total}] 🎵 处理张学友: 《{title}》 (专辑: 《{album}》)...")
        
        local_dir = os.path.join(BASE_DIR, "storage", "music", "张学友", album)
        os.makedirs(local_dir, exist_ok=True)
        local_mp3 = os.path.join(local_dir, f"s_{song_id}.mp3")
        local_lrc = os.path.join(BASE_DIR, "storage", "lyrics", "张学友", album, f"s_{song_id}.lrc")
        os.makedirs(os.path.dirname(local_lrc), exist_ok=True)
        
        ok_mp3 = download_audio_jacky(title, local_mp3)
        if not ok_mp3:
            print(f"   ❌ 无法获取真实音频，跳过")
            failed_list.append((song_id, title, "音频下载失败"))
            continue
            
        file_sz = os.path.getsize(local_mp3)
        print(f"   ✅ [真音频就绪] {os.path.basename(local_mp3)} ({file_sz / 1024 / 1024:.2f} MB)")
        
        lrc_text = fetch_lrc_jacky(title)
        if lrc_text:
            with open(local_lrc, "w", encoding="utf-8") as lf:
                lf.write(lrc_text)
            print(f"   ✅ [真歌词就绪] ({len(lrc_text)} 字节)")
        else:
            print(f"   ⚠️ 未检索到带时间轴歌词，生成占位歌词")
            lrc_text = f"[00:00.00]{title}\n[00:05.00]张学友\n"
            with open(local_lrc, "w", encoding="utf-8") as lf:
                lf.write(lrc_text)
                
        r2_mp3_key = f"music/张学友/{album}/s_{song_id}.mp3"
        r2_lrc_key = f"music/张学友/{album}/s_{song_id}.lrc"
        
        try:
            with open(local_mp3, "rb") as mf:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=r2_mp3_key,
                    Body=mf.read(),
                    ContentType="audio/mpeg"
                )
            print(f"   ☁️ [R2 音频上传成功] {r2_mp3_key}")
            
            s3_client.put_object(
                Bucket=bucket_name,
                Key=r2_lrc_key,
                Body=lrc_text.encode('utf-8'),
                ContentType="text/plain; charset=utf-8"
            )
            print(f"   ☁️ [R2 歌词上传成功] {r2_lrc_key}")
            
            success_list.append({
                "id": song_id,
                "album": album,
                "title": title,
                "file_path": R2_DEV_PREFIX + r2_mp3_key,
                "lrc_path": R2_DEV_PREFIX + r2_lrc_key,
                "local_mp3": local_mp3,
                "local_lrc": local_lrc,
                "track_index": track_index
            })
        except Exception as e:
            print(f"   ❌ R2 上传异常: {e}")
            failed_list.append((song_id, title, f"R2 上传错误: {e}"))

    if success_list:
        print("\n" + "=" * 80)
        print(f"⚡ 开始纠偏并点亮 Cloudflare D1 数据库 ({len(success_list)} 首)...")
        payload = {
            "updates": [
                {
                    "id": item["id"],
                    "file_path": item["file_path"],
                    "lrc_path": item["lrc_path"]
                }
                for item in success_list
            ]
        }
        
        try:
            resp = requests.post(API_BATCH_LIGHT_URL, json=payload, timeout=20)
            if resp.status_code == 200:
                print(f"  🎉 [Cloudflare D1 纠偏点亮成功] 成功纠偏 {len(success_list)} 首歌曲！")
            else:
                print(f"  ❌ D1 接口返回错误: HTTP {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"  ❌ D1 请求异常: {e}")

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        for item in success_list:
            cur.execute("""
                INSERT OR REPLACE INTO tracks_sync_state
                (song_id, artist_name, album_title, song_title, track_index, local_mp3, local_lrc, r2_mp3_key, r2_lrc_key, status, updated_at)
                VALUES (?, '张学友', ?, ?, ?, ?, ?, ?, ?, 'D1_LIT', CURRENT_TIMESTAMP)
            """, (item["id"], item["album"], item["title"], item["track_index"], item["local_mp3"], item["local_lrc"], item["file_path"], item["lrc_path"]))
        conn.commit()
        conn.close()
        print("  💾 本地 catalog_sync.db 同步回写纳管完成！")

    print("\n" + "=" * 80)
    print(f"🏁 张学友《Smile》流水线收官！成功修复: {len(success_list)} 首 | 失败: {len(failed_list)} 首")
    print("=" * 80)

if __name__ == "__main__":
    run()
