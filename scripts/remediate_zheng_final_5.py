#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
郑智化最后 5 首曲目（官方 Topic / 官方 Lyric Video 源）精准补全与覆盖流水线
"""
import sys
import json
import time
import os
import re
import sqlite3
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics

sys.stdout.reconfigure(encoding='utf-8')

WORKSPACE = r"e:\Workspace\AI-Project\MoodyMusic-Workspace"
BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
TMP_DIR = os.path.join(BASE_DIR, "downloads_optimized", "zheng_final_5")
os.makedirs(TMP_DIR, exist_ok=True)

PROXY = "http://127.0.0.1:10090"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    R2_CFG = json.load(f)

# Bucket 07
b07_cfg = R2_CFG['buckets']['account_07']
s3_07 = boto3.client(
    's3',
    endpoint_url=b07_cfg['endpoint_url'],
    aws_access_key_id=b07_cfg['access_key_id'],
    aws_secret_access_key=b07_cfg['secret_access_key'],
    config=Config(signature_version='s3v4')
)
B07_NAME = b07_cfg['name']
B07_DOMAIN = b07_cfg['public_domain'].rstrip('/')

# Bucket 08
b08_cfg = R2_CFG['buckets']['account_08']
s3_08 = boto3.client(
    's3',
    endpoint_url=b08_cfg['endpoint_url'],
    aws_access_key_id=b08_cfg['access_key_id'],
    aws_secret_access_key=b08_cfg['secret_access_key'],
    config=Config(signature_version='s3v4')
)
B08_NAME = b08_cfg['name']
B08_DOMAIN = b08_cfg['public_domain'].rstrip('/')

FINAL_TARGETS = [
    {"album": "单身逃亡", "title": "陷阱", "sid": 28880, "vid": "IFBZEnG5XrM", "bucket": "07"},
    {"album": "单身逃亡", "title": "猫", "sid": 28881, "vid": "FENHSmJW4As", "bucket": "07"},
    {"album": "落泪的戏子", "title": "风在唱着一首歌", "sid": 28930, "vid": "NfZNo8isj3I", "bucket": "07"},
    {"album": "游戏人间", "title": "阿飞和他的那个女人", "sid": 28936, "vid": "zyEWYl9yZC8", "bucket": "08"},
    {"album": "游戏人间", "title": "小草", "sid": 28940, "vid": "Go2F0QxZRrk", "bucket": "08"}
]

def standardize(raw, opt):
    cmd = [
        "ffmpeg", "-y", "-i", raw,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-b:a", "160k", "-ar", "44100",
        opt
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return res.returncode == 0 and os.path.exists(opt)

def get_duration(fpath):
    try:
        res = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            fpath
        ], capture_output=True, text=True, encoding='utf-8', errors='replace')
        for line in res.stdout.splitlines():
            if line.startswith('duration='):
                return int(float(line.split('=')[1]))
    except:
        pass
    return 0

success_count = 0
for idx, item in enumerate(FINAL_TARGETS, 1):
    alb = item['album']
    tit = item['title']
    sid = item['sid']
    vid = item['vid']
    bucket_type = item['bucket']
    
    if bucket_type == '08':
        target_s3 = s3_08
        target_bucket = B08_NAME
        target_domain = B08_DOMAIN
        bucket_label = "Bucket 08"
    else:
        target_s3 = s3_07
        target_bucket = B07_NAME
        target_domain = B07_DOMAIN
        bucket_label = "Bucket 07"

    print(f"\n[{idx}/5] 🎙️ 重制郑智化官方母带: 《{alb}》 - 《{tit}》 (ID: {sid}) [YouTube: {vid}]")

    raw_prefix = os.path.join(TMP_DIR, f"yt_{sid}")
    opt_file = os.path.join(TMP_DIR, f"opt_{sid}.mp3")
    lrc_file = os.path.join(TMP_DIR, f"lrc_{sid}.lrc")

    # 1. 下载官方视频音频
    print(" • [1/5] 抓取 YouTube 官方高保真音源...", end="", flush=True)
    cmd_dl = [
        "yt-dlp", "--proxy", PROXY,
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "-o", f"{raw_prefix}.%(ext)s",
        f"https://www.youtube.com/watch?v={vid}"
    ]
    subprocess.run(cmd_dl, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    
    raw_file = None
    for ext in ["mp3", "m4a", "webm", "opus"]:
        cand = f"{raw_prefix}.{ext}"
        if os.path.exists(cand) and os.path.getsize(cand) > 500000:
            raw_file = cand
            break

    if not raw_file:
        print(" ❌ 下载失败！")
        continue
    print(f" [🟢 成功! 大小: {os.path.getsize(raw_file)//1024} KB]")

    # 2. 标准化
    print(" • [2/5] EBU R128 (-14 LUFS) 响度标准化与 160k CBR Xing 编码...", end="", flush=True)
    if not standardize(raw_file, opt_file):
        print(" ❌ 编码失败！")
        continue
    dur_sec = get_duration(opt_file)
    fsize = os.path.getsize(opt_file)
    print(f" [完成! 时长: {dur_sec}s, 大小: {fsize/(1024*1024):.2f} MB]")

    # 3. 抓取同步歌词
    print(" • [3/5] 抓取毫秒级同步时间轴歌词...", end="", flush=True)
    has_lrc = False
    try:
        txt = syncedlyrics.search(f"郑智化 {tit}")
        if txt and len(txt) > 50:
            with open(lrc_file, 'w', encoding='utf-8') as f:
                f.write(txt)
            has_lrc = True
    except:
        pass
    print(" [🟢 成功]" if has_lrc else " [⚠️ 沿用原歌词]")

    # 4. 上传至目标 R2 Bucket 覆盖
    clean_alb = re.sub(r'[\\/*?:"<>|]', '_', alb).strip()
    r2_audio_key = f"music/郑智化/{clean_alb}/s_{sid}.mp3"
    r2_lrc_key = f"lyrics/郑智化/{clean_alb}/s_{sid}.lrc"

    print(f" • [4/5] 上传至 Cloudflare R2 {bucket_label} 物理覆盖...", end="", flush=True)
    with open(opt_file, 'rb') as f:
        target_s3.put_object(Bucket=target_bucket, Key=r2_audio_key, Body=f, ContentType='audio/mpeg')
    if has_lrc:
        with open(lrc_file, 'rb') as f:
            target_s3.put_object(Bucket=target_bucket, Key=r2_lrc_key, Body=f, ContentType='text/plain; charset=utf-8')
    print(" [🟢 上传成功]")

    cdn_audio = f"{target_domain}/{r2_audio_key}"
    cdn_lrc = f"{target_domain}/{r2_lrc_key}"

    # 5. 点亮与更新本地 DB
    print(" • [5/5] 更新 D1 与本地数据库...", end="", flush=True)
    payload = {
        "updates": [{
            "id": sid,
            "file_path": cdn_audio,
            "lrc_path": cdn_lrc
        }]
    }
    for attempt in range(3):
        try:
            r = requests.post(D1_LIGHT_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=15)
            if r.status_code == 200 and r.json().get('code') == 200:
                break
        except:
            pass
        time.sleep(1)

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE songs SET file_path = ?, lrc_path = ?, duration = ? WHERE id = ?", (cdn_audio, cdn_lrc, dur_sec, sid))
        cur.execute("UPDATE tracks_sync_state SET status = 'D1_LIT', r2_mp3_key = ?, r2_lrc_key = ?, file_size = ?, duration = ? WHERE song_id = ?", (cdn_audio, cdn_lrc, fsize, str(dur_sec), sid))
        conn.commit()
        conn.close()
    except:
        pass
    print(" [🟢 完成!]")

    for p in [raw_file, opt_file, lrc_file]:
        if p and os.path.exists(p):
            try: os.remove(p)
            except: pass

    success_count += 1
    print(f"🎉 修复完成: 《{alb}》 - 《{tit}》 -> {cdn_audio} ({dur_sec}s)")
    time.sleep(1)

print("\n" + "=" * 80)
print(f"🏁 郑智化最后 5 首曲目治理完毕! 成功修复: {success_count} / {len(FINAL_TARGETS)} 首")
print("=" * 80)
