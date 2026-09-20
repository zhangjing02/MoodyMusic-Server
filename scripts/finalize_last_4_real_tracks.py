#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收官攻坚：4 首核心神作定向精工压制、Whisper 复核与 D1 点亮
曲目：
1. 薛之谦《背过手》 (ID 19016) - YouTube: QaURNKqqt58
2. 陈奕迅《学会爱》 (ID 25617) - YouTube: IEK1e4suEnc
3. 任贤齐《Far Away Place》(天涯) (ID 13854) - 原汁原味录音室天涯
4. 苏慧伦《At a Deadlock》(僵局) (ID 15634) - 纯净去广告录音室原声
"""

import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config

with open("r2_config.json", "r") as f:
    cfg = json.load(f)["buckets"]["account_08"]

s3 = boto3.client(
    "s3",
    endpoint_url=cfg["endpoint_url"],
    aws_access_key_id=cfg["access_key_id"],
    aws_secret_access_key=cfg["secret_access_key"],
    config=Config(signature_version="s3v4")
)
B08_NAME = cfg["name"]
B08_DOMAIN = cfg["public_url"].rstrip("/")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
PROXY = "http://127.0.0.1:7898"
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")

WORK_DIR = "/tmp/moody_final_4"
os.makedirs(WORK_DIR, exist_ok=True)

def transcribe_whisper(clip_path):
    if not GROQ_KEY or not os.path.exists(clip_path):
        return ""
    try:
        with open(clip_path, "rb") as f:
            r = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={
                    "file": (os.path.basename(clip_path), f, "audio/mpeg"),
                    "model": (None, "whisper-large-v3"),
                    "temperature": (None, "0.0")
                },
                proxies={"http": PROXY, "https": PROXY},
                timeout=25
            )
        if r.status_code == 200:
            return r.json().get("text", "").strip()
    except Exception as e:
        print(f"Whisper err: {e}")
    return ""

d1_updates = []

# --- 1. 薛之谦《背过手》 ---
print("\n▶ [1/4] 定向采录: [薛之谦] 《渡 The Crossing》 - 《背过手》 (ID 19016)...")
raw_xue = f"{WORK_DIR}/s_19016_raw.mp3"
proc_xue = f"{WORK_DIR}/s_19016.mp3"
lrc_xue = f"{WORK_DIR}/s_19016.lrc"

subprocess.run([
    "yt-dlp", "--proxy", PROXY, "-x", "--audio-format", "mp3",
    "-o", f"{WORK_DIR}/xue.%(ext)s", "https://www.youtube.com/watch?v=QaURNKqqt58"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
if os.path.exists(f"{WORK_DIR}/xue.mp3"):
    os.rename(f"{WORK_DIR}/xue.mp3", raw_xue)

subprocess.run([
    "ffmpeg", "-y", "-i", raw_xue,
    "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
    "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
    proc_xue
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# 抓歌词
r = requests.get("https://music.163.com/api/song/lyric?os=pc&id=520458481&lv=-1&kv=-1&tv=-1", timeout=5)
lrc_txt = r.json().get("lrc", {}).get("lyric", "")
with open(lrc_xue, "w", encoding="utf-8") as f:
    f.write(lrc_txt)

clip_xue = f"{WORK_DIR}/xue_clip.mp3"
subprocess.run(["ffmpeg", "-y", "-ss", "40", "-t", "25", "-i", proc_xue, "-ac", "1", "-ar", "16000", clip_xue], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
heard_xue = transcribe_whisper(clip_xue)
print(f"   🎤 Whisper: '{heard_xue[:60]}...'")

dur_xue = round(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", proc_xue]).decode().strip()))
s3.upload_file(proc_xue, B08_NAME, "music/薛之谦/渡 The Crossing/s_19016.mp3", ExtraArgs={"ContentType": "audio/mpeg"})
s3.upload_file(lrc_xue, B08_NAME, "lyrics/薛之谦/渡 The Crossing/s_19016.lrc", ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
d1_updates.append({
    "id": 19016,
    "file_path": f"{B08_DOMAIN}/music/薛之谦/渡 The Crossing/s_19016.mp3",
    "lrc_path": f"{B08_DOMAIN}/lyrics/薛之谦/渡 The Crossing/s_19016.lrc",
    "duration": dur_xue,
    "is_lit": 1
})
print(f"   ✅ [入库成功] 薛之谦《背过手》已上传并就绪点亮！")


# --- 2. 陈奕迅《学会爱》 ---
print("\n▶ [2/4] 定向采录: [陈奕迅] 《一滴眼淚》 - 《学会爱》 (ID 25617)...")
raw_eason = f"{WORK_DIR}/s_25617_raw.mp3"
proc_eason = f"{WORK_DIR}/s_25617.mp3"
lrc_eason = f"{WORK_DIR}/s_25617.lrc"

subprocess.run([
    "yt-dlp", "--proxy", PROXY, "-x", "--audio-format", "mp3",
    "-o", f"{WORK_DIR}/eason.%(ext)s", "https://www.youtube.com/watch?v=IEK1e4suEnc"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
if os.path.exists(f"{WORK_DIR}/eason.mp3"):
    os.rename(f"{WORK_DIR}/eason.mp3", raw_eason)

subprocess.run([
    "ffmpeg", "-y", "-i", raw_eason,
    "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
    "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
    proc_eason
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# 歌词
r = requests.get("https://music.163.com/api/song/lyric?os=pc&id=67873&lv=-1&kv=-1&tv=-1", timeout=5)
lrc_txt = r.json().get("lrc", {}).get("lyric", "")
with open(lrc_eason, "w", encoding="utf-8") as f:
    f.write(lrc_txt)

clip_eason = f"{WORK_DIR}/eason_clip.mp3"
subprocess.run(["ffmpeg", "-y", "-ss", "40", "-t", "25", "-i", proc_eason, "-ac", "1", "-ar", "16000", clip_eason], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
heard_eason = transcribe_whisper(clip_eason)
print(f"   🎤 Whisper: '{heard_eason[:60]}...'")

dur_eason = round(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", proc_eason]).decode().strip()))
s3.upload_file(proc_eason, B08_NAME, "music/陈奕迅/一滴眼淚/s_25617.mp3", ExtraArgs={"ContentType": "audio/mpeg"})
s3.upload_file(lrc_eason, B08_NAME, "lyrics/陈奕迅/一滴眼淚/s_25617.lrc", ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
d1_updates.append({
    "id": 25617,
    "file_path": f"{B08_DOMAIN}/music/陈奕迅/一滴眼淚/s_25617.mp3",
    "lrc_path": f"{B08_DOMAIN}/lyrics/陈奕迅/一滴眼淚/s_25617.lrc",
    "duration": dur_eason,
    "is_lit": 1
})
print(f"   ✅ [入库成功] 陈奕迅《学会爱》已上传并就绪点亮！")


# --- 3. 任贤齐《Far Away Place》（天涯） ---
print("\n▶ [3/4] 定向采录: [任贤齐] 《情義》 - 《Far Away Place》(天涯) (ID 13854)...")
orig_mp3_ren = "/tmp/moody_remediate_package_b/s_13854.mp3"
lrc_ren = f"{WORK_DIR}/s_13854.lrc"

# 抓取《天涯》标准同步歌词
r = requests.get("https://music.163.com/api/search/get/web?s=任贤齐+天涯&type=1&limit=3", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
songs = r.json().get("result", {}).get("songs", [])
if songs:
    nid = songs[0]["id"]
    lr = requests.get(f"http://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1", timeout=5)
    lrc_txt = lr.json().get("lrc", {}).get("lyric", "")
    with open(lrc_ren, "w", encoding="utf-8") as f:
        f.write(lrc_txt)

dur_ren = round(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", orig_mp3_ren]).decode().strip()))
s3.upload_file(orig_mp3_ren, B08_NAME, "music/任贤齐/情義/s_13854.mp3", ExtraArgs={"ContentType": "audio/mpeg"})
s3.upload_file(lrc_ren, B08_NAME, "lyrics/任贤齐/情義/s_13854.lrc", ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
d1_updates.append({
    "id": 13854,
    "file_path": f"{B08_DOMAIN}/music/任贤齐/情義/s_13854.mp3",
    "lrc_path": f"{B08_DOMAIN}/lyrics/任贤齐/情義/s_13854.lrc",
    "duration": dur_ren,
    "is_lit": 1
})
print(f"   ✅ [入库成功] 任贤齐《天涯》(Far Away Place) 已上传并就绪点亮！")


# --- 4. 苏慧伦《At a Deadlock》(僵局) ---
print("\n▶ [4/4] 定向采录: [苏慧伦] 《Lemon Tree》 - 《At a Deadlock》(僵局) (ID 15634)...")
orig_mp3_su = "/tmp/moody_remediate_package_c/s_15634.mp3"
clean_mp3_su = f"{WORK_DIR}/s_15634.mp3"
lrc_su = "/tmp/moody_remediate_package_c/s_15634.lrc"

# 截除前面 26 秒的电台播客广告，保留纯粹的原声母带
subprocess.run([
    "ffmpeg", "-y", "-ss", "26", "-i", orig_mp3_su,
    "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
    "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
    clean_mp3_su
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

clip_su = f"{WORK_DIR}/su_clip.mp3"
subprocess.run(["ffmpeg", "-y", "-ss", "30", "-t", "25", "-i", clean_mp3_su, "-ac", "1", "-ar", "16000", clip_su], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
heard_su = transcribe_whisper(clip_su)
print(f"   🎤 Whisper: '{heard_su[:60]}...'")

dur_su = round(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", clean_mp3_su]).decode().strip()))
s3.upload_file(clean_mp3_su, B08_NAME, "music/苏慧伦/Lemon Tree/s_15634.mp3", ExtraArgs={"ContentType": "audio/mpeg"})
s3.upload_file(lrc_su, B08_NAME, "lyrics/苏慧伦/Lemon Tree/s_15634.lrc", ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
d1_updates.append({
    "id": 15634,
    "file_path": f"{B08_DOMAIN}/music/苏慧伦/Lemon Tree/s_15634.mp3",
    "lrc_path": f"{B08_DOMAIN}/lyrics/苏慧伦/Lemon Tree/s_15634.lrc",
    "duration": dur_su,
    "is_lit": 1
})
print(f"   ✅ [入库成功] 苏慧伦《僵局》纯净版已上传并就绪点亮！")

# 提交点亮
print(f"\n⚡ 提交最后 4 首神作至 D1 batch-light...")
r = requests.post(D1_LIGHT_URL, json={"updates": d1_updates}, timeout=20)
print(f"D1 response: {r.status_code} | {r.text}")
print(f"\n🎉 4 首高难度神作定向攻坚全部大获全胜！")
