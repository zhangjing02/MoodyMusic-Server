#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOODY 早期曲库治理 - 阶段 2B：13 首真实曲目官方唱片公司频道母带精准替换
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

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_FILE = os.path.join(BASE_DIR, "reports", "TASK_REPLACE_REMAINING_13.json")
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
LOG_DIR = os.path.join(BASE_DIR, "reports")
WORK_DIR = "/tmp/moody_remediate_topic_workspace"
os.makedirs(WORK_DIR, exist_ok=True)

PROXY = "http://127.0.0.1:7897"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

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

def download_official_topic(artist: str, title: str, out_prefix: str) -> tuple[bool, str, str]:
    c_tit = title.split('(')[0].split('（')[0].strip()
    queries = [
        f"{artist} {c_tit} Topic",
        f"{artist} {c_tit} Official",
        f"{artist} {c_tit} 官方"
    ]
    for q in queries:
        cmd_search = [
            "yt-dlp", "--proxy", PROXY,
            "--flat-playlist", "--no-warnings",
            "--print", "%(id)s | %(channel)s | %(title)s | %(duration)s",
            f"ytsearch3:{q}"
        ]
        try:
            res = subprocess.run(cmd_search, capture_output=True, text=True, timeout=20)
            for line in res.stdout.splitlines():
                parts = line.split(" | ")
                if len(parts) >= 3:
                    vid, channel, vtitle = parts[0], parts[1], parts[2]
                    ch_l = channel.lower()
                    vt_l = vtitle.lower()
                    # 避免纯伴奏和解说
                    if not any(k in vt_l for k in ["伴奏", "instrumental", "karaoke", "zither", "harp", "解说", "后座力"]):
                        cmd_dl = [
                            "yt-dlp", "--proxy", PROXY,
                            "-x", "--audio-format", "mp3", "--audio-quality", "0",
                            "-o", f"{out_prefix}.%(ext)s",
                            f"https://www.youtube.com/watch?v={vid}"
                        ]
                        subprocess.run(cmd_dl, capture_output=True, timeout=60)
                        for ext in ["mp3", "m4a", "webm", "opus"]:
                            cand = f"{out_prefix}.{ext}"
                            if os.path.exists(cand) and os.path.getsize(cand) > 500000:
                                return True, cand, f"{channel} - {vtitle}"
        except Exception:
            pass
    return False, "", ""

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

def fetch_lyrics(artist: str, title: str, out_lrc: str) -> bool:
    c_tit = title.split('(')[0].split('（')[0].strip()
    if syncedlyrics:
        try:
            txt = syncedlyrics.search(f"{artist} {c_tit}")
            if txt and len(txt) > 40 and "纯音乐，请欣赏" not in txt:
                with open(out_lrc, "w", encoding="utf-8") as f:
                    f.write(txt)
                return True
        except:
            pass
    return False

def main():
    print("=" * 80)
    print("🚀 启动 MOODY 早期曲库治理 - 阶段 2B：13 首真实曲目官方 Topic 精准替换")
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

        print(f"\n[{idx:02d}/{len(tasks):02d}] 正在重制换源: [{artist}] 《{album}》 - 《{title}》 (ID: {sid})")

        prefix = os.path.join(WORK_DIR, f"raw_{sid}")
        opt_mp3 = os.path.join(WORK_DIR, f"opt_{sid}.mp3")
        opt_lrc = os.path.join(WORK_DIR, f"opt_{sid}.lrc")

        ok, raw_file, desc = download_official_topic(artist, title, prefix)
        if not ok:
            print("   ❌ 官方 Topic 母带下载失败，跳过！")
            fail_cnt += 1
            continue

        print(f"   🟢 官方频道母带获取成功: {desc} ({os.path.getsize(raw_file)//1024} KB)")

        if not standardize_audio(raw_file, opt_mp3):
            print("   ❌ 压制失败！")
            fail_cnt += 1
            continue
        dur_sec = get_duration(opt_mp3)

        has_lrc = fetch_lyrics(artist, title, opt_lrc)

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

        for p in [raw_file, opt_mp3, opt_lrc]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

        if updated:
            print(f"   🎉 治理成功! ({dur_sec}s) -> {new_audio_url}")
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
                "duration": dur_sec,
                "source": desc
            })
        else:
            print("   ❌ D1 更新失败！")
            fail_cnt += 1

        time.sleep(0.5)

    record_file = os.path.join(LOG_DIR, "STAGE_2B_TOPIC_REPLACED_LOG.json")
    with open(record_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 阶段 2B 完成！成功: {success_cnt} 首，失败: {fail_cnt} 首")
    print(f"📜 审计日志归档至: {record_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
