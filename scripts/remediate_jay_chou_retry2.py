#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周杰伦遗漏 2 首曲目 (半岛铁盒、无双) 补跑与精准质检流水线
"""

import os
import sys
import json
import time
import subprocess
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/remediate_jay_chou"
os.makedirs(WORK_DIR, exist_ok=True)

TASKS = [
    {
        "id": 23312,
        "artist": "周杰伦",
        "album": "八度空间",
        "title": "半岛铁盒",
        "yt_id": "duZDsG3tvoA",
        "expected_dur": 320,
        "start_offset": 0
    },
    {
        "id": 23369,
        "artist": "周杰伦",
        "album": "我很忙",
        "title": "无双",
        "yt_id": "IYiIL2ZgOK4",
        "expected_dur": 234,
        "start_offset": 0
    }
]

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_all = json.load(f)["buckets"]

target_cfg = r2_all["account_11"]
s3_target = boto3.client(
    "s3",
    endpoint_url=target_cfg["endpoint_url"],
    aws_access_key_id=target_cfg["access_key_id"],
    aws_secret_access_key=target_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
TARGET_BUCKET_NAME = target_cfg["name"]
TARGET_DOMAIN = target_cfg["public_url"].rstrip("/")

def download_audio_with_retry(yt_id, out_raw, max_retries=3):
    yt_url = f"https://www.youtube.com/watch?v={yt_id}"
    for attempt in range(1, max_retries + 1):
        try:
            print(f"      下载尝试 {attempt}/{max_retries}...")
            cmd = [
                "yt-dlp",
                "-x", "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", out_raw,
                "--no-playlist",
                yt_url
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=90, check=True)
            if not os.path.exists(out_raw) and os.path.exists(out_raw + ".mp3"):
                os.rename(out_raw + ".mp3", out_raw)
            if os.path.exists(out_raw) and os.path.getsize(out_raw) > 500 * 1024:
                return True
        except Exception as e:
            print(f"      下载第 {attempt} 次失败: {e}")
            time.sleep(3)
    return False

def standardize_audio(in_file, out_file, start_offset=0):
    cmd = ["ffmpeg", "-y"]
    if start_offset > 0:
        cmd.extend(["-ss", str(start_offset)])
    cmd.extend([
        "-i", in_file,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-c:a", "libmp3lame",
        "-b:a", "160k",
        "-ar", "44100",
        "-write_xing", "1",
        "-id3v2_version", "3",
        out_file
    ])
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)

def get_audio_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    out = subprocess.check_output(cmd, timeout=8).decode().strip()
    return float(out)

def update_d1(song_id, new_file_path, duration_sec):
    wrangler_bin = os.path.join(BASE_DIR, "cloudflare-worker", "node_modules", ".bin", "wrangler")
    escaped_path = new_file_path.replace("'", "''")
    sql = f"UPDATE songs SET file_path = '{escaped_path}', duration = {int(duration_sec)}, format = 'mp3', bit_rate = 160 WHERE id = {song_id};"
    cmd = [
        wrangler_bin, "d1", "execute", "moody-d1-test", "--remote",
        "--command", sql
    ]
    cwd = os.path.join(BASE_DIR, "cloudflare-worker")
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
    if res.returncode == 0:
        return True, res.stdout
    else:
        return False, res.stderr

def run_retry():
    print("=" * 80)
    print("🚀 启动周杰伦 2 首曲目补跑置换 (半岛铁盒, 无双)")
    print("=" * 80)
    
    for t in TASKS:
        sid = t["id"]
        title = t["title"]
        artist = t["artist"]
        album = t["album"]
        print(f"\n处理 ID {sid}: {artist} - {title} ({album})")
        
        raw_file = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
        std_file = os.path.join(WORK_DIR, f"std_{sid}.mp3")
        
        # 1. 下载
        if not download_audio_with_retry(t["yt_id"], raw_file):
            print(f"❌ 下载最终失败: {title}")
            continue
            
        # 2. 压制
        print(f"   EBU R128 标准化压制中...")
        standardize_audio(raw_file, std_file, start_offset=t["start_offset"])
        dur = get_audio_duration(std_file)
        print(f"   实测时长: {dur:.2f}s (预期: {t['expected_dur']}s)")
        
        # 3. 上传
        r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
        target_cdn_url = f"{TARGET_DOMAIN}/{r2_key}"
        print(f"   上传至 Bucket 11: {r2_key}...")
        with open(std_file, "rb") as f:
            s3_target.put_object(
                Bucket=TARGET_BUCKET_NAME,
                Key=r2_key,
                Body=f,
                ContentType="audio/mpeg"
            )
        print(f"   ✅ 上传成功: {target_cdn_url}")
        
        # 4. 回写 D1
        print(f"   更新 D1 数据库...")
        ok, msg = update_d1(sid, target_cdn_url, dur)
        if ok:
            print(f"   ✅ D1 更新成功 (ID {sid})")
        else:
            print(f"   ❌ D1 更新失败: {msg}")

if __name__ == "__main__":
    run_retry()
