#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOODY 早期曲库治理 - 阶段 2A：真实存在错配曲目 (18 首) 精准换源与点亮
=============================================================================
"""

import os
import sys
import json
import re
import time
import subprocess
import requests
import boto3
from botocore.config import Config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_FILE = os.path.join(BASE_DIR, "reports", "TASK_REPLACE_18_REAL_SONGS.json")
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
LOG_DIR = os.path.join(BASE_DIR, "reports")
WORK_DIR = "/tmp/moody_remediate_18_real"
os.makedirs(WORK_DIR, exist_ok=True)

D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://music.163.com/"
}

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_data = json.load(f)["buckets"]

b11 = r2_data["account_11"]
s3_11 = boto3.client(
    "s3",
    endpoint_url=b11["endpoint_url"],
    aws_access_key_id=b11["access_key_id"],
    aws_secret_access_key=b11["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
BUCKET_NAME = b11["name"]
PUBLIC_DOMAIN = b11.get("public_url", "").rstrip("/")

def download_audio(nid: int, out_path: str) -> bool:
    url = f"https://music.163.com/song/media/outer/url?id={nid}.mp3"
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=15)
        if r.status_code == 200:
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(65536):
                    if chunk: f.write(chunk)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 500000:
                return True
    except:
        pass
    return False

def download_lrc(nid: int, out_path: str) -> bool:
    url = f"https://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1"
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        if r.status_code == 200:
            lrc = r.json().get("lrc", {}).get("lyric", "")
            if lrc and len(lrc) > 30 and "纯音乐，请欣赏" not in lrc:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(lrc)
                return True
    except:
        pass
    return False

def standardize_audio(raw_file: str, opt_file: str) -> bool:
    cmd = [
        "ffmpeg", "-y", "-i", raw_file,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-b:a", "160k", "-ar", "44100",
        opt_file
    ]
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0 and os.path.exists(opt_file) and os.path.getsize(opt_file) > 500000

def get_duration(fpath: str) -> int:
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', fpath]
        res = subprocess.run(cmd, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if line.startswith('duration='):
                return int(float(line.split('=')[1]))
    except:
        pass
    return 0

def main():
    print("=" * 80)
    print("🚀 启动 MOODY 早期曲库治理 - 阶段 2A：真实曲目 (18 首) 精准换源与点亮")
    print("=" * 80)

    with open(TASK_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    success_cnt = 0
    fail_cnt = 0
    records = []

    for idx, item in enumerate(tasks, 1):
        sid = item["song_id"]
        artist = item["artist"]
        album = item["album"]
        title = item["title"]
        match_info = item.get("official_match", {})
        nid = match_info.get("id")

        print(f"\n[{idx:02d}/{len(tasks):02d}] 正在重制换源: [{artist}] 《{album}》 - 《{title}》 (ID: {sid})")
        print(f"    官方锚定曲目: {match_info.get('name')} (歌手: {match_info.get('artist')}, ID: {nid})")

        raw_mp3 = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
        opt_mp3 = os.path.join(WORK_DIR, f"opt_{sid}.mp3")
        opt_lrc = os.path.join(WORK_DIR, f"opt_{sid}.lrc")

        # 1. 下载官方正版母带
        if not download_audio(nid, raw_mp3):
            print("    ❌ 正版母带下载失败，跳过！")
            fail_cnt += 1
            continue

        # 2. 标准化压制
        if not standardize_audio(raw_mp3, opt_mp3):
            print("    ❌ EBU R128 标准化压制失败，跳过！")
            fail_cnt += 1
            continue
        dur_sec = get_duration(opt_mp3)

        # 3. 下载配套 LRC
        has_lrc = download_lrc(nid, opt_lrc)

        # 4. 上传 R2
        clean_alb = re.sub(r'[\\/*?:"<>|]', '_', album).strip()
        clean_art = re.sub(r'[\\/*?:"<>|]', '_', artist).strip()
        r2_audio_key = f"music/{clean_art}/{clean_alb}/s_{sid}.mp3"
        r2_lrc_key = f"lyrics/{clean_art}/{clean_alb}/s_{sid}.lrc"

        with open(opt_mp3, "rb") as f:
            s3_11.put_object(Bucket=BUCKET_NAME, Key=r2_audio_key, Body=f, ContentType="audio/mpeg")

        if has_lrc:
            with open(opt_lrc, "rb") as f:
                s3_11.put_object(Bucket=BUCKET_NAME, Key=r2_lrc_key, Body=f, ContentType="text/plain; charset=utf-8")

        new_audio_url = f"{PUBLIC_DOMAIN}/{r2_audio_key}"
        new_lrc_url = f"{PUBLIC_DOMAIN}/{r2_lrc_key}" if has_lrc else item.get("lrc_path")

        # 5. 更新 D1
        payload = {
            "updates": [{
                "id": sid,
                "file_path": new_audio_url,
                "lrc_path": new_lrc_url
            }]
        }

        updated = False
        for retry in range(3):
            try:
                r = requests.post(D1_LIGHT_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
                if r.status_code == 200 and r.json().get("code") == 200:
                    updated = True
                    break
            except:
                time.sleep(1)

        for p in [raw_mp3, opt_mp3, opt_lrc]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

        if updated:
            print(f"    🟢 治理成功! ({dur_sec}s) -> {new_audio_url}")
            success_cnt += 1
            records.append({
                "song_id": sid,
                "artist": artist,
                "album": album,
                "title": title,
                "status": "REPLACED_SUCCESS",
                "old_audio": item.get("file_path"),
                "new_audio": new_audio_url,
                "new_lrc": new_lrc_url,
                "duration": dur_sec
            })
        else:
            print(f"    ❌ D1 更新失败！")
            fail_cnt += 1

        time.sleep(0.5)

    record_file = os.path.join(LOG_DIR, "STAGE_2A_REAL_SONGS_REPLACED_LOG.json")
    with open(record_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 阶段 2A 真实曲目换源完成！成功: {success_cnt} 首，失败: {fail_cnt} 首")
    print(f"📜 明细已归档: {record_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
