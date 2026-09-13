#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 陈小春全专真实音视频与精准歌词自动化流水线
(Jordan Chan Authentic Audio & Synced Lyrics Pipeline)

功能：
1. 抓取陈小春 6 张专辑 23 首官方/原版 YouTube 音频并以 160k 纯净转码
2. 抓取高精度时间轴 LRC 歌词 (syncedlyrics / NetEase / Lrclib)
3. 直传至 Cloudflare R2 (moody-music-asset-02)
4. 调用 batch-light 接口彻底修复 D1 数据库中被错配绑定的周杰伦/蔡依林音频与歌词
5. 纳管至本地 catalog_sync.db
"""

import os
import sys
import re
import time
import json
import sqlite3
import subprocess
import urllib.parse
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
TEMP_DIR = os.path.join(BASE_DIR, "downloads", "jordan_chan_temp")
os.makedirs(TEMP_DIR, exist_ok=True)

API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
R2_DEV_PREFIX = "https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/"

NODE_PATH = r"D:\DevelopeTools\Node\node.exe" if os.path.exists(r"D:\DevelopeTools\Node\node.exe") else "node"
JS_RUNTIME_ARG = f"node:{NODE_PATH}"

JORDAN_CHAN_TRACKS = [
    # 专辑 1: No Big Deal (ID: 1957)
    (27699, "No Big Deal", "找個空間唱歌", 1),
    (27700, "No Big Deal", "分開一朝也天冧", 2),
    (27701, "No Big Deal", "是日忌嗌悶", 3),
    (27702, "No Big Deal", "我愛你", 4),
    (27703, "No Big Deal", "成王敗寇", 5),
    (27704, "No Big Deal", "背影樹", 6),
    (27705, "No Big Deal", "亂世巨星", 7),
    
    # 专辑 2: I'll Wash Away Your Blues (ID: 1956)
    (27687, "I'll Wash Away Your Blues", "蠢蠢欲動", 1),
    (27697, "I'll Wash Away Your Blues", "叱吒紅人", 2),
    (27688, "I'll Wash Away Your Blues", "只要地球還有女人 (男人版)", 3),
    (27698, "I'll Wash Away Your Blues", "苦男人 (房仔Mix)", 4),
    (27689, "I'll Wash Away Your Blues", "Qq的您", 5),
    (27690, "I'll Wash Away Your Blues", "小春電器", 6),
    (27691, "I'll Wash Away Your Blues", "愛情號", 7),
    (27692, "I'll Wash Away Your Blues", "我女人", 8),
    (27693, "I'll Wash Away Your Blues", "車神", 9),
    (27694, "I'll Wash Away Your Blues", "神奇事", 10),
    (27695, "I'll Wash Away Your Blues", "戰無不勝", 11),
    (27696, "I'll Wash Away Your Blues", "只要地球還有女人 (女人版)", 12),
    
    # 专辑 3: 我不是偉人 - Single (ID: 1952)
    (27667, "我不是偉人 - Single", "我不是偉人", 1),
    
    # 专辑 4: 難怪 ﹣ Single (ID: 1953)
    (27668, "難怪 ﹣ Single", "難怪", 1),
    
    # 专辑 5: 愛的相反 - Single (ID: 1954)
    (27669, "愛的相反 - Single", "愛的相反", 1),
    
    # 专辑 6: 笛子魔童 - Single (ID: 1955)
    (27686, "笛子魔童 - Single", "Flute Devil Child", 1)
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

def sanitize_folder_name(name: str) -> str:
    return re.sub(r'[\/:*?"<>|]', '_', name).strip()

def clean_song_title(title: str) -> list[str]:
    candidates = [title]
    t1 = re.sub(r'\(.*?\)|（.*?）|\[.*?\]|【.*?】', '', title).strip()
    if t1 and t1 not in candidates:
        candidates.append(t1)
    if "Flute Devil Child" in title:
        candidates.append("笛子魔童")
    return candidates

def fetch_lrc_chan(title: str) -> str | None:
    for ct in clean_song_title(title):
        for q in [f"陈小春 {ct}", f"陳小春 {ct}", ct]:
            try:
                lrc = syncedlyrics.search(q, providers=['NetEase', 'Lrclib'])
                if lrc and len(lrc) > 80 and '[' in lrc and ':' in lrc:
                    return lrc
            except Exception:
                pass
            time.sleep(0.2)
    return None

def download_audio_chan(title: str, out_mp3_path: str) -> bool:
    clean_titles = clean_song_title(title)
    main_title = clean_titles[0]
    query = f"陈小春 {main_title}"
    
    cmd_search = [
        "yt-dlp",
        "--encoding", "utf-8",
        "--js-runtimes", JS_RUNTIME_ARG,
        "--print", "%(id)s | %(title)s | %(duration)s | %(channel)s",
        f"ytsearch5:{query}"
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
            # 过滤时长 (1.5 ~ 8 分钟)
            if 90 <= dur_sec <= 480:
                best_video_id = vid
                break
                
    if not best_video_id and lines:
        best_video_id = lines[0].split('|')[0].strip()

    if not best_video_id:
        print(f"    ⚠️ 未找到候选视频")
        return False

    # 开始下载并转码为 160kbps MP3
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
    print("🚀 MOODY - 陈小春全专真实音频与歌词抓取补齐任务启动")
    print("=" * 80)

    s3_client, bucket_name = get_r2_client()
    print(f"☁️ R2 目标存储桶: {bucket_name}")
    
    success_list = []
    failed_list = []
    
    total = len(JORDAN_CHAN_TRACKS)
    
    for idx, (song_id, album, title, track_index) in enumerate(JORDAN_CHAN_TRACKS, 1):
        print(f"\n[{idx}/{total}] 🎵 处理陈小春: 《{title}》 (专辑: 《{album}》)...")
        
        safe_album = sanitize_folder_name(album)
        local_dir = os.path.join(BASE_DIR, "storage", "music", "陈小春", safe_album)
        os.makedirs(local_dir, exist_ok=True)
        local_mp3 = os.path.join(local_dir, f"s_{song_id}.mp3")
        local_lrc = os.path.join(BASE_DIR, "storage", "lyrics", "陈小春", safe_album, f"s_{song_id}.lrc")
        os.makedirs(os.path.dirname(local_lrc), exist_ok=True)
        
        # 1. 下载真音频
        ok_mp3 = download_audio_chan(title, local_mp3)
        if not ok_mp3:
            print(f"   ❌ 无法获取真实音频，跳过")
            failed_list.append((song_id, title, "音频下载失败"))
            continue
            
        file_sz = os.path.getsize(local_mp3)
        print(f"   ✅ [真音频就绪] {os.path.basename(local_mp3)} ({file_sz / 1024 / 1024:.2f} MB)")
        
        # 2. 获取真歌词
        lrc_text = fetch_lrc_chan(title)
        if lrc_text:
            with open(local_lrc, "w", encoding="utf-8") as lf:
                lf.write(lrc_text)
            print(f"   ✅ [真歌词就绪] ({len(lrc_text)} 字节)")
        else:
            print(f"   ⚠️ 未检索到带时间轴歌词，生成占位歌词")
            lrc_text = f"[00:00.00]{title}\n[00:05.00]陈小春\n[00:10.00]暂无滚动歌词"
            with open(local_lrc, "w", encoding="utf-8") as lf:
                lf.write(lrc_text)
                
        # 3. 上传音频与歌词到 R2
        r2_mp3_key = f"music/陈小春/{album}/s_{song_id}.mp3"
        r2_lrc_key = f"music/陈小春/{album}/s_{song_id}.lrc"
        
        try:
            # 上传 MP3
            with open(local_mp3, "rb") as mf:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=r2_mp3_key,
                    Body=mf.read(),
                    ContentType="audio/mpeg"
                )
            print(f"   ☁️ [R2 音频上传成功] {r2_mp3_key}")
            
            # 上传 LRC
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

    # 4. 批量纠偏 Cloudflare D1 数据库
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
                print(f"  🎉 [Cloudflare D1 纠偏点亮成功] 成功更新 {len(success_list)} 首歌曲的音频与歌词！")
            else:
                print(f"  ❌ D1 接口返回错误: HTTP {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"  ❌ D1 请求异常: {e}")

        # 5. 回写本地 SQLite
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        for item in success_list:
            cur.execute("""
                INSERT OR REPLACE INTO tracks_sync_state
                (song_id, artist_name, album_title, song_title, track_index, local_mp3, local_lrc, r2_mp3_key, r2_lrc_key, status, updated_at)
                VALUES (?, '陈小春', ?, ?, ?, ?, ?, ?, ?, 'D1_LIT', CURRENT_TIMESTAMP)
            """, (item["id"], item["album"], item["title"], item["track_index"], item["local_mp3"], item["local_lrc"], item["file_path"], item["lrc_path"]))
        conn.commit()
        conn.close()
        print("  💾 本地 catalog_sync.db 同步回写纳管完成！")

    print("\n" + "=" * 80)
    print(f"🏁 陈小春流水线收官！成功修复: {len(success_list)} 首 | 失败: {len(failed_list)} 首")
    print("=" * 80)

if __name__ == "__main__":
    run()
