#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 质检错配曲目高保真录音室母带重采与自动修复流水线
==============================================================================
执行清单:
1. 阿杜 《我不該躲》 - 《為愛投降》 (ID: 4) -> Bilibili 官方母带 BV1Fx411V7ur
2. 阿杜 《第9次初恋》 - 《几年了》 (ID: 38) -> YouTube Topic 官方母带 h-U2R07I5lU (达成全专100%满贯)
3. 阿杜 《沒什麼好怕》 - 《沒什麼好怕》 (ID: 59) -> YouTube Topic 官方母带 acinuJ639Qs
4. 王菲 《將愛》 - 《花事了》 (ID: 24170) -> YouTube HQ 母带 66fS-7y9zyA
5. 王菲 《將愛》 - 《MV》 (ID: 24168) -> YouTube 录音室母带 9SOg4S9foPE
6. 古巨基 《其實我...我...我》 - 《順風車》 (ID: 7480) -> YouTube 官方母带 RASokHbU174
==============================================================================
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

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "qc_repair")
os.makedirs(WORK_DIR, exist_ok=True)

YOUTUBE_PROXY = "http://127.0.0.1:10090"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# 待重采与修复的真录音室母带任务列表
REPAIR_TASKS = [
    {
        "id": 4,
        "artist": "阿杜",
        "album": "我不該躲",
        "title": "為愛投降",
        "source_url": "https://www.bilibili.com/video/BV1Fx411V7ur",
        "use_proxy": False
    },
    {
        "id": 38,
        "artist": "阿杜",
        "album": "第9次初恋",
        "title": "几年了",
        "source_url": "https://www.youtube.com/watch?v=h-U2R07I5lU",
        "use_proxy": True
    },
    {
        "id": 59,
        "artist": "阿杜",
        "album": "沒什麼好怕",
        "title": "沒什麼好怕",
        "source_url": "https://www.youtube.com/watch?v=acinuJ639Qs",
        "use_proxy": True
    },
    {
        "id": 24170,
        "artist": "王菲",
        "album": "將愛",
        "title": "花事了",
        "source_url": "https://www.youtube.com/watch?v=66fS-7y9zyA",
        "use_proxy": True
    },
    {
        "id": 24168,
        "artist": "王菲",
        "album": "將愛",
        "title": "MV",
        "source_url": "https://www.youtube.com/watch?v=9SOg4S9foPE",
        "use_proxy": True
    },
    {
        "id": 7480,
        "artist": "古巨基",
        "album": "其實我...我...我",
        "title": "順風車",
        "source_url": "https://www.youtube.com/watch?v=RASokHbU174",
        "use_proxy": True
    }
]

def init_s3_client():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    acc = cfg['buckets']['account_06']
    s3 = boto3.client(
        's3',
        endpoint_url=acc['endpoint_url'],
        aws_access_key_id=acc['access_key_id'],
        aws_secret_access_key=acc['secret_access_key'],
        config=Config(signature_version='s3v4')
    )
    return s3, acc['name'], acc['public_domain']

def download_audio(task: dict, raw_output_path: str) -> bool:
    url = task["source_url"]
    use_proxy = task["use_proxy"]
    if os.path.exists(raw_output_path):
        try: os.remove(raw_output_path)
        except: pass

    cmd = ["yt-dlp", "--no-playlist", "--force-overwrites", "-x", "--audio-format", "mp3", "--audio-quality", "0"]
    if use_proxy:
        cmd.extend(["--proxy", YOUTUBE_PROXY, "--js-runtimes", "node", "--extractor-args", "youtube:player_client=android,web"])
    
    # 临时前缀模板
    tmpl = raw_output_path.replace(".mp3", ".%(ext)s")
    cmd.extend(["-o", tmpl, url])

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
        return os.path.exists(raw_output_path) and os.path.getsize(raw_output_path) > 100000
    except Exception as e:
        print(f"  ❌ 下载异常: {e}")
        return False

def standardize_audio(raw_path: str, master_path: str, artist: str, album: str, title: str) -> bool:
    """EBU R128 音量标准化 + 160k CBR (44.1kHz) + Xing Header + ID3v2 元数据"""
    if os.path.exists(master_path):
        try: os.remove(master_path)
        except: pass

    cmd = [
        "ffmpeg", "-y",
        "-i", raw_path,
        "-vn",
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame",
        "-b:a", "160k",
        "-ar", "44100",
        "-write_xing", "1",
        "-metadata", f"title={title}",
        "-metadata", f"artist={artist}",
        "-metadata", f"album={album}",
        master_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=60)
        return os.path.exists(master_path) and os.path.getsize(master_path) > 50000
    except Exception as e:
        print(f"  ❌ 压制异常: {e}")
        return False

def fetch_and_save_lrc(artist: str, album: str, title: str, lrc_path: str) -> bool:
    try:
        queries = [f"{artist} {title}", f"{artist} {album} {title}", title]
        for q in queries:
            try:
                lrc = syncedlyrics.search(q, providers=['NetEase', 'Kugou', 'Lrclib'])
                if lrc and len(lrc.strip()) > 30:
                    with open(lrc_path, 'w', encoding='utf-8') as f:
                        f.write(lrc)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

def run_repair():
    print("=" * 90)
    print("🛠️ 启动 MOODY 高保真录音室母带重新采录与 D1 点亮闭环流水线")
    print("=" * 90)

    s3, bucket_name, cdn_domain = init_s3_client()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    success_list = []

    for idx, t in enumerate(REPAIR_TASKS, 1):
        sid = t["id"]
        art = t["artist"]
        alb = t["album"]
        song = t["title"]

        print(f"\n[{idx}/{len(REPAIR_TASKS)}] 正在修复: [{art}] 《{alb}》 - 《{song}》 (ID: {sid})")
        
        raw_mp3 = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
        master_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
        lrc_file = os.path.join(WORK_DIR, f"s_{sid}.lrc")

        # 1. 抓取高保真母带
        print(f"  ⬇️ 正在从母带源采录: {t['source_url']}...")
        ok = download_audio(t, raw_mp3)
        if not ok:
            print(f"  ❌ 母带采录失败，跳过")
            continue
        print(f"  ✅ 采录成功! 文件大小: {os.path.getsize(raw_mp3)/1024/1024:.2f} MB")

        # 2. EBU R128 标准化压制
        print(f"  🎛️ 正在执行 EBU R128 标准化压制 (160k CBR + Xing Header)...")
        ok = standardize_audio(raw_mp3, master_mp3, art, alb, song)
        if not ok:
            print(f"  ❌ 压制失败，跳过")
            continue
        print(f"  ✅ 标准化母带压制完成! 最终体积: {os.path.getsize(master_mp3)/1024/1024:.2f} MB")

        # 3. 抓取毫秒级同步歌词
        print(f"  📝 正在检索并匹配毫秒级同步时间轴 LRC...")
        has_lrc = fetch_and_save_lrc(art, alb, song, lrc_file)
        if has_lrc:
            print(f"  ✅ 同步 LRC 歌词抓取成功 ({os.path.getsize(lrc_file)} bytes)")
        else:
            print(f"  ⚠️ 未查到精确时间轴歌词，将仅点亮音频")

        # 4. 上传至 R2 Bucket 06 (account_06)
        r2_mp3_key = f"music/{art}/{alb}/s_{sid}.mp3"
        r2_lrc_key = f"music/{art}/{alb}/s_{sid}.lrc" if has_lrc else None

        cdn_mp3_url = f"{cdn_domain}/{r2_mp3_key}"
        cdn_lrc_url = f"{cdn_domain}/{r2_lrc_key}" if has_lrc else None

        print(f"  ☁️ 正在上传至 Cloudflare R2 ({bucket_name})...")
        with open(master_mp3, 'rb') as f:
            s3.put_object(Bucket=bucket_name, Key=r2_mp3_key, Body=f, ContentType='audio/mpeg')
        print(f"  ✅ 音频上传成功: {cdn_mp3_url}")

        if has_lrc:
            with open(lrc_file, 'rb') as f:
                s3.put_object(Bucket=bucket_name, Key=r2_lrc_key, Body=f, ContentType='text/plain; charset=utf-8')
            print(f"  ✅ 歌词上传成功: {cdn_lrc_url}")

        # 5. 调用 D1 batch-light 毫秒点亮
        print(f"  🌐 正在通过 Cloudflare D1 边缘接口点亮...")
        light_payload = {
            "updates": [{
                "id": sid,
                "file_path": cdn_mp3_url,
                "lrc_path": cdn_lrc_url
            }]
        }
        try:
            r = requests.post(D1_LIGHT_URL, json=light_payload, timeout=15)
            if r.status_code == 200:
                print(f"  ✨ D1 生产数据库点亮成功! {r.json().get('message')}")
                # 6. 同步本地 catalog_sync.db
                cur.execute("UPDATE songs SET file_path = ?, lrc_path = ? WHERE id = ?", (cdn_mp3_url, cdn_lrc_url, sid))
                cur.execute("""
                    UPDATE tracks_sync_state 
                    SET status = 'D1_LIT', r2_mp3_key = ?, r2_lrc_key = ?, last_error = NULL 
                    WHERE song_id = ?
                """, (cdn_mp3_url, cdn_lrc_url, sid))
                conn.commit()
                success_list.append((art, alb, song, sid))
            else:
                print(f"  ❌ D1 点亮接口返回异常: {r.status_code} {r.text}")
        except Exception as e:
            print(f"  ❌ D1 网络点亮异常: {e}")

        # 清理临时原始文件
        if os.path.exists(raw_mp3):
            try: os.remove(raw_mp3)
            except: pass

    print("\n" + "=" * 90)
    print(f"🎉 修复完成! 成功采录、压制、上传并点亮 {len(success_list)} 首歌曲:")
    for art, alb, song, sid in success_list:
        print(f"  • [{art}] 《{alb}》 - 《{song}》 (ID: {sid})")
    print("=" * 90)

if __name__ == "__main__":
    run_repair()
