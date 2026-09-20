#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复迪克牛仔 6 首失败曲目 - 使用精准 NetEase ID 直接拉取"""

import os, json, subprocess, requests, boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
with open(os.path.join(BASE_DIR, "r2_config.json")) as f:
    cfg = json.load(f)["buckets"]["account_07"]

s3 = boto3.client("s3", endpoint_url=cfg["endpoint_url"],
    aws_access_key_id=cfg["access_key_id"],
    aws_secret_access_key=cfg["secret_access_key"],
    region_name="auto", config=Config(signature_version="s3v4"))
BUCKET = cfg["name"]
DOMAIN = cfg.get("public_url", cfg.get("public_domain", "")).rstrip("/")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
D1_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
HEADERS = {"User-Agent": "Mozilla/5.0"}
WORK = "/tmp/dick_retry6"
os.makedirs(WORK, exist_ok=True)

# 6 首失败曲目 + 对应权威 NetEase ID
TASKS = [
    {"id": 28662, "title": "街角的GUITAR MAN", "album": "忘记我还是忘记他", "netease_id": 77418},
    {"id": 28677, "title": "管他谁爱谁",       "album": "我这个你不爱的人",  "netease_id": 77319},
    {"id": 28682, "title": "他不爱我",          "album": "咆哮2002",          "netease_id": 77242},
    {"id": 28684, "title": "勇气",              "album": "咆哮2002",          "netease_id": 77252},
    {"id": 28703, "title": "迷途",              "album": "风飞沙",            "netease_id": 76974},
    {"id": 28710, "title": "禁区",              "album": "禁区",              "netease_id": 76968},
]

def whisper(clip_path):
    with open(clip_path, "rb") as f:
        r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": (os.path.basename(clip_path), f, "audio/mpeg"), "model": (None, "whisper-large-v3")},
            proxies=GROQ_PROXIES, timeout=25)
    return r.json().get("text", "").strip()

d1_updates = []
for t in TASKS:
    sid, title, album, nid = t["id"], t["title"], t["album"], t["netease_id"]
    print(f"\n▶ 《{title}》 (ID:{sid}) via NetEase {nid}")

    raw = f"{WORK}/s_{sid}_raw.mp3"
    proc = f"{WORK}/s_{sid}.mp3"
    lrc_out = f"{WORK}/s_{sid}.lrc"

    # 1. 下载音频
    mp3_url = f"http://music.163.com/song/media/outer/url?id={nid}.mp3"
    data = requests.get(mp3_url, headers=HEADERS, timeout=20).content
    if len(data) < 500*1024:
        print(f"   ❌ 音频过小 ({len(data)} bytes)，跳过")
        continue
    open(raw, "wb").write(data)
    print(f"   ✅ 下载成功: {len(data)//1024} KB")

    # 2. 下载 LRC
    lrc_r = requests.get(f"http://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1", headers=HEADERS, timeout=8)
    lrc_txt = lrc_r.json().get("lrc", {}).get("lyric", "")
    if lrc_txt and len(lrc_txt) > 30:
        open(lrc_out, "w", encoding="utf-8").write(lrc_txt)

    # 3. EBU R128 + 160k CBR 压制
    subprocess.run(["ffmpeg", "-y", "-i", raw,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1", proc],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    dur = float(subprocess.check_output(["ffprobe", "-v", "error",
        "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", proc]).decode().strip())
    print(f"   ✅ 压制完成: {dur:.1f}s")

    # 4. Whisper 质检 (切片 30s~60s)
    clip = f"{WORK}/s_{sid}_clip.mp3"
    subprocess.run(["ffmpeg", "-y", "-ss", "30", "-t", "30", "-i", proc, "-ac", "1", "-ar", "16000", clip],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    heard = whisper(clip)
    os.remove(clip)
    print(f"   🎤 Whisper: {heard[:60]}")

    # 黑名单拦截
    bad = False
    for kw in ["Zither Harp", "李宗盛", "三万英尺"]:
        if kw in heard and kw not in title:
            print(f"   🚫 黑名单命中 [{kw}]，跳过")
            bad = True; break
    if len(heard.strip()) < 5:
        print(f"   🚫 无有效人声，跳过"); bad = True
    if bad:
        continue

    # 5. 上传 R2
    key_audio = f"music/迪克牛仔/{album}/s_{sid}.mp3"
    key_lrc   = f"lyrics/迪克牛仔/{album}/s_{sid}.lrc"
    s3.upload_file(proc, BUCKET, key_audio, ExtraArgs={"ContentType": "audio/mpeg"})
    print(f"   ☁️ R2 音频覆写: {key_audio}")
    if os.path.exists(lrc_out):
        s3.upload_file(lrc_out, BUCKET, key_lrc, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        print(f"   ☁️ R2 歌词覆写: {key_lrc}")

    d1_updates.append({"id": sid, "file_path": f"{DOMAIN}/{key_audio}",
        "lrc_path": f"{DOMAIN}/{key_lrc}", "duration": round(dur), "is_lit": 1})

# 6. D1 点亮
if d1_updates:
    r = requests.post(D1_URL, json={"updates": d1_updates}, timeout=20)
    print(f"\n📡 D1 点亮响应: {r.status_code} | {r.text}")

print(f"\n🎉 迪克牛仔 6 首补救完成，成功 {len(d1_updates)} 首")
