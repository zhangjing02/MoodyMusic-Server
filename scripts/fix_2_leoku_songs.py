#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import subprocess
import json
import boto3
import requests
from syncedlyrics import search as search_lrc

R2_CONFIG_FILE = "MoodyMusic-Server/r2_config.json"
with open(R2_CONFIG_FILE, "r", encoding="utf-8") as f:
    cfg = json.load(f)["buckets"]["account_08"]

s3 = boto3.client(
    "s3",
    endpoint_url=cfg["endpoint_url"],
    aws_access_key_id=cfg["access_key_id"],
    aws_secret_access_key=cfg["secret_access_key"],
    region_name="auto"
)

tasks = [
    {
        "id": 7443,
        "artist": "古巨基",
        "album": "愛與夢飛行",
        "title": "十秒之後",
        "vid": "TJDm-BX0c30"
    },
    {
        "id": 7370,
        "artist": "古巨基",
        "album": "戀戀情深",
        "title": "In Fact We Are Both Selfish",
        "lrc_title": "其實我們一樣自私",
        "vid": "frr-FFzx2Dw"
    }
]

updates = []
for t in tasks:
    sid = t["id"]
    vid = t["vid"]
    raw = f"/tmp/raw_{sid}.mp3"
    mp3 = f"/tmp/s_{sid}.mp3"
    lrc = f"/tmp/s_{sid}.lrc"
    
    # 1. 下载
    subprocess.run([
        "yt-dlp", "--proxy", "http://127.0.0.1:7897",
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "-o", raw, f"https://www.youtube.com/watch?v={vid}"
    ], check=True)
    
    # 2. 压制
    title = t["title"]
    artist = t["artist"]
    album = t["album"]
    cmd_ff = [
        "ffmpeg", "-y", "-i", raw, "-vn", "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
        "-id3v2_version", "3",
        "-metadata", f"title={title}",
        "-metadata", f"artist={artist}",
        "-metadata", f"album={album}",
        mp3
    ]
    subprocess.run(cmd_ff, check=True)
    
    # 3. 歌词
    lrc_q = f"古巨基 {t.get('lrc_title', title)}"
    lrc_content = search_lrc(lrc_q)
    has_lrc = False
    if lrc_content:
        with open(lrc, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        has_lrc = True
        
    # 4. 上传
    r2_audio_key = f"music/古巨基/{album}/s_{sid}.mp3"
    r2_lrc_key = f"lyrics/古巨基/{album}/s_{sid}.lrc"
    
    s3.upload_file(mp3, cfg["name"], r2_audio_key, ExtraArgs={"ContentType": "audio/mpeg"})
    if has_lrc:
        s3.upload_file(lrc, cfg["name"], r2_lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        
    updates.append({
        "id": sid,
        "file_path": r2_audio_key,
        "lrc_path": r2_lrc_key if has_lrc else None
    })
    
    for fpath in [raw, mp3, lrc]:
        if os.path.exists(fpath):
            os.remove(fpath)
    print(f"✅ {title} 上传成功！")

# 5. D1 批量点亮
r = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json={"updates": updates}, timeout=20)
print("D1 点亮结果:", r.status_code, r.text)
