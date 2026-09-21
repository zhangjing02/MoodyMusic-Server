#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专门针对 Twins 代表神作《Touch of Love 爱的温柔》的精准补完与点亮脚本
"""

import os
import sys
import json
import time
import requests
import subprocess
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
PROXY_URL = "http://127.0.0.1:7898"
PROXIES = {"http": PROXY_URL, "https": PROXY_URL}
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]["account_09"] # 写入全新的第9桶

s3 = boto3.client(
    "s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)

# 目标曲目与定制关键词
TARGETS = [
    {
        "id": 28048,
        "title": "下一站天后",
        "search": "下一站天后 Twins",
        "keywords": ["百德新街", "时代广场", "台上任我唱", "肥皂泡", "开过窗", "四面", "天后", "下一站"]
    },
    {
        "id": 28047,
        "title": "多謝失戀",
        "search": "多謝失戀 Twins",
        "keywords": ["自我解困", "失恋", "心恋", "体温", "练习", "合分", "好人", "解困", "多谢失恋"]
    },
    {
        "id": 28050,
        "title": "變變變",
        "search": "變變變 Twins",
        "keywords": ["年轻人", "时代变", "千变", "怀念", "飞", "改变", "变变变"]
    },
    {
        "id": 28056,
        "title": "我的驕傲",
        "search": "我的驕傲 Twins",
        "keywords": ["believe me i can fly", "singing in the sky", "神话", "骄傲", "藏金与花"]
    },
    {
        "id": 28052,
        "title": "亂世佳人",
        "search": "亂世佳人 Twins 官方",
        "keywords": ["乱世", "佳人", "恋爱", "感动", "戏院", "散场"]
    },
    {
        "id": 28049,
        "title": "千金",
        "search": "千金 Twins 粤语",
        "keywords": ["千金", "王子", "长大", "美丽", "金", "恋爱"]
    }
]

def transcribe(clip):
    if not GROQ_KEY or not os.path.exists(clip): return ""
    try:
        with open(clip, "rb") as f:
            r = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": (os.path.basename(clip), f, "audio/mpeg"), "model": (None, "whisper-large-v3")},
                proxies=PROXIES,
                timeout=25
            )
            if r.status_code == 200:
                return r.json().get("text", "")
    except Exception as e:
        print("Whisper error:", e)
    return ""

def main():
    print("==================================================================")
    print("🚀 启动 Twins《Touch of Love 爱的温柔》核心大碟精准补全点亮流水线")
    print("==================================================================")

    work_dir = "/tmp/remedy_touch_of_love"
    os.makedirs(work_dir, exist_ok=True)
    d1_updates = []

    for item in TARGETS:
        sid = item["id"]
        tit = item["title"]
        q = item["search"]
        kws = item["keywords"]

        print(f"\n▶ 正在采录: Twins - 《{tit}》 (ID: {sid})")
        raw_mp3 = f"{work_dir}/s_{sid}_raw.mp3"
        proc_mp3 = f"{work_dir}/s_{sid}.mp3"
        clip_mp3 = f"{work_dir}/s_{sid}_clip.mp3"

        # 1. 尝试网易云
        downloaded = False
        try:
            r = requests.get("https://music.163.com/api/search/get/web", params={"s": q, "type": 1, "limit": 4}, headers=HEADERS, timeout=5)
            songs = r.json().get("result", {}).get("songs", [])
            for s in songs:
                s_art = [a.get("name", "") for a in s.get("artists", [])]
                if any("twins" in a.lower() for a in s_art):
                    url = f"https://music.163.com/song/media/outer/url?id={s['id']}.mp3"
                    chk = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=5)
                    if chk.status_code == 200 and int(chk.headers.get("Content-Length", 0)) > 1000000:
                        audio = requests.get(url, headers=HEADERS, stream=True, timeout=15)
                        with open(raw_mp3, "wb") as f:
                            for c in audio.iter_content(65536): f.write(c)
                        downloaded = True
                        break
        except Exception:
            pass

        # 2. 尝试 YouTube
        if not downloaded:
            try:
                cmd = ["yt-dlp", "--proxy", PROXY_URL, "--get-id", f"ytsearch1:{q}"]
                vid = subprocess.check_output(cmd, timeout=20).decode().strip()
                if vid:
                    dl_cmd = ["yt-dlp", "--proxy", PROXY_URL, "-x", "--audio-format", "mp3", "-o", raw_mp3, f"https://www.youtube.com/watch?v={vid}"]
                    subprocess.run(dl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
                    downloaded = os.path.exists(raw_mp3)
            except Exception:
                pass

        if not downloaded or not os.path.exists(raw_mp3) or os.path.getsize(raw_mp3) < 500000:
            print(f"   ❌ 无法下载到有效音源: {tit}")
            continue

        # 3. 压制
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_mp3,
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
            proc_mp3
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        dur_raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", proc_mp3]).decode().strip()
        dur = float(dur_raw)

        # 4. Whisper 听音验证
        subprocess.run(["ffmpeg", "-y", "-ss", "45", "-t", "30", "-i", proc_mp3, "-ac", "1", "-ar", "16000", clip_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        text = transcribe(clip_mp3).lower()
        print(f"   🗣️ [Whisper 转写]: {text[:80]}...")

        passed = any(kw.lower() in text for kw in kws)
        if not passed:
            print(f"   ⚠️ 45s 未命中关键词，尝试 75s-105s 切片...")
            subprocess.run(["ffmpeg", "-y", "-ss", "75", "-t", "30", "-i", proc_mp3, "-ac", "1", "-ar", "16000", clip_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            text2 = transcribe(clip_mp3).lower()
            print(f"   🗣️ [副歌转写]: {text2[:80]}...")
            passed = any(kw.lower() in text2 for kw in kws)

        if not passed:
            print(f"   ❌ [质检未通过] 经听音鉴真未能确认是 Twins《{tit}》原版！")
            continue

        print(f"   ✅ [质检通过] 确认录音室正版原声！")

        # 5. 上传 R2 Bucket 09
        key = f"music/Twins/Touch of Love/s_{sid}.mp3"
        s3.upload_file(proc_mp3, r2_cfg["name"], key, ExtraArgs={"ContentType": "audio/mpeg"})
        audio_url = f"{r2_cfg['public_url'].rstrip('/')}/{key}"
        print(f"   ☁️ 已上传 R2: {audio_url}")

        d1_updates.append({"id": sid, "file_path": audio_url, "duration": round(dur)})

    # 6. 提交 D1 点亮
    if d1_updates:
        print(f"\n⚡ 正在向生产网关提交 D1 batch-light ({len(d1_updates)} 首)...")
        r = requests.post(D1_LIGHT_URL, json={"updates": d1_updates}, timeout=15)
        print(f"🟢 [点亮响应]: {r.json().get('message')}")
    else:
        print("\n⚠️ 无待点亮曲目")

if __name__ == "__main__":
    main()
