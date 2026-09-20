#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""郑智化最后 4 首关键曲目定向重铸流水线"""

import os, sys, json, subprocess, requests, boto3
from botocore.config import Config

sys.stdout.reconfigure(line_buffering=True)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORK_DIR = "/tmp/zheng_last_4"
os.makedirs(WORK_DIR, exist_ok=True)

with open(os.path.join(BASE_DIR, "r2_config.json"), "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]

s3_clients = {}
domains = {}
buckets = {}
for acc in ["account_07", "account_08"]:
    cfg = r2_cfg[acc]
    s3_clients[acc] = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4")
    )
    domains[acc] = cfg.get("public_url", cfg.get("public_domain", "")).rstrip("/")
    buckets[acc] = cfg["name"]

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}
D1_LIGHT_API = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TARGETS = [
    {"id": 28932, "title": "有关于承诺", "album": "落泪的戏子", "vid": "3ueXr7XGG28", "acc": "account_07"},
    {"id": 28942, "title": "新绿岛小夜曲", "album": "游戏人间", "vid": "Lj8-lwJFX3c", "acc": "account_08"},
    {"id": 28943, "title": "原来的样子", "album": "游戏人间", "vid": "LNTUQVPceN8", "acc": "account_08"},
    {"id": 28951, "title": "Say Goodbye", "album": "夜未眠", "vid": "HtJ87Uhd7YI", "acc": "account_07"},
]

def transcribe_whisper(clip_path):
    if not GROQ_KEY:
        return ""
    try:
        with open(clip_path, "rb") as f:
            r = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": (os.path.basename(clip_path), f, "audio/mpeg"), "model": (None, "whisper-large-v3")},
                proxies=GROQ_PROXIES,
                timeout=25
            )
        if r.status_code == 200:
            return r.json().get("text", "").strip()
    except:
        pass
    return ""

def get_best_lrc(title):
    try:
        r = requests.get(f"https://music.163.com/api/search/get/web?s=郑智化+{title}&type=1&limit=3", headers=HEADERS, timeout=6)
        songs = r.json().get("result", {}).get("songs", [])
        for s in songs:
            if "郑智化" in s.get("artists", [{}])[0].get("name", ""):
                nid = s["id"]
                lr = requests.get(f"http://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1", headers=HEADERS, timeout=6)
                lrc = lr.json().get("lrc", {}).get("lyric", "")
                if lrc and len(lrc) > 30:
                    return lrc
    except:
        pass
    return None

d1_updates = []
for t in TARGETS:
    sid = t["id"]
    title = t["title"]
    album = t["album"]
    vid = t["vid"]
    acc = t["acc"]

    print(f"\n▶ 定向重铸: 《{title}》 (专辑: {album}, ID: {sid}) | YouTube: {vid} -> 目标: {acc}")

    raw_mp3 = f"{WORK_DIR}/s_{sid}_raw.mp3"
    proc_mp3 = f"{WORK_DIR}/s_{sid}.mp3"
    lrc_file = f"{WORK_DIR}/s_{sid}.lrc"

    # 1. 下载
    cmd = [
        "yt-dlp", "--proxy", "http://127.0.0.1:7898",
        "-x", "--audio-format", "mp3",
        "-o", f"{WORK_DIR}/s_{sid}_yt.%(ext)s",
        f"https://www.youtube.com/watch?v={vid}"
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120)
        os.rename(f"{WORK_DIR}/s_{sid}_yt.mp3", raw_mp3)
        print(f"   ✅ 视频音源下载成功")
    except Exception as e:
        print(f"   ❌ 下载失败: {e}")
        continue

    # 2. LRC
    lrc_txt = get_best_lrc(title)
    if lrc_txt:
        with open(lrc_file, "w", encoding="utf-8") as f:
            f.write(lrc_txt)

    # 3. 压制
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_mp3,
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
            proc_mp3
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", proc_mp3
        ]).decode().strip())
        print(f"   ✅ EBU R128 标准化压制完成: 时长 {dur:.1f}s")
    except Exception as e:
        print(f"   ❌ 压制失败: {e}")
        continue

    # 4. Whisper 质检
    clip = f"{WORK_DIR}/s_{sid}_clip.mp3"
    subprocess.run(["ffmpeg", "-y", "-ss", "45", "-t", "25", "-i", proc_mp3, "-ac", "1", "-ar", "16000", clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    heard = transcribe_whisper(clip)
    if os.path.exists(clip): os.remove(clip)
    print(f"   🎤 Whisper 听辨: '{heard[:45]}...'")

    # 5. 上传
    key_audio = f"music/郑智化/{album}/s_{sid}.mp3"
    key_lrc = f"lyrics/郑智化/{album}/s_{sid}.lrc"
    s3_clients[acc].upload_file(proc_mp3, buckets[acc], key_audio, ExtraArgs={"ContentType": "audio/mpeg"})
    print(f"   ☁️ R2 音频覆写成功: {buckets[acc]}/{key_audio}")
    if os.path.exists(lrc_file):
        s3_clients[acc].upload_file(lrc_file, buckets[acc], key_lrc, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        print(f"   ☁️ R2 歌词覆写成功: {buckets[acc]}/{key_lrc}")

    cdn = domains[acc]
    d1_updates.append({
        "id": sid,
        "file_path": f"{cdn}/{key_audio}",
        "lrc_path": f"{cdn}/{key_lrc}",
        "duration": round(dur),
        "is_lit": 1
    })

if d1_updates:
    r = requests.post(D1_LIGHT_API, json={"updates": d1_updates}, timeout=20)
    print(f"\n📡 D1 原子批量点亮响应: {r.status_code} | {r.text}")

print(f"\n🎉 最终 4 首攻坚完成，成功点亮 {len(d1_updates)} 首！")
