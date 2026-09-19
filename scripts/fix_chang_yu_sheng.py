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
        "id": 23159, "artist": "张雨生", "album": "Yu Hou Xing Kong",
        "title": "Wo Qing Yi Di Jie Shu Liao Yi Duan Gan Qing",
        "lrc_title": "我轻易地结束了一段感情", "vid": "RXz0ejSxWB4"
    },
    {
        "id": 23107, "artist": "张雨生", "album": "兩伊戰爭 (2018 Remastering)",
        "title": "The Indian Summer Night (2018 Remastering)",
        "lrc_title": "The Indian Summer Night", "vid": "3rg-rESTMrk"
    },
    {
        "id": 23112, "artist": "张雨生", "album": "兩伊戰爭 (2018 Remastering)",
        "title": "發暈 (2018 Remastering)",
        "lrc_title": "发晕", "vid": "BWW_d-3R20o"
    },
    {
        "id": 23116, "artist": "张雨生", "album": "口是心非 (2017 Remastering)",
        "title": "CAPPUCCINO (2017 Remastering)",
        "lrc_title": "Cappuccino", "vid": "p66-H_TgCYc"
    },
    {
        "id": 23122, "artist": "张雨生", "album": "口是心非 (2017 Remastering)",
        "title": "神采 (2017 Remastering)",
        "lrc_title": "神采", "vid": "SuJLJ_Vowp8"
    },
    {
        "id": 23123, "artist": "张雨生", "album": "口是心非 (2017 Remastering)",
        "title": "在黃昏融化了世界的色彩以前 (2017 Remastering)",
        "lrc_title": "在黄昏融化了世界的色彩以前", "vid": "pyR-hAWqAk4"
    },
    {
        "id": 23124, "artist": "张雨生", "album": "口是心非 (2017 Remastering)",
        "title": "若我告訴你其實我愛的只是你 (2017 Remastering)",
        "lrc_title": "若我告诉你其实我爱的只是你", "vid": "-_LLJycOcnI"
    }
]

updates = []
for t in tasks:
    sid = t["id"]
    vid = t["vid"]
    raw = f"/tmp/raw_{sid}.mp3"
    mp3 = f"/tmp/s_{sid}.mp3"
    lrc = f"/tmp/s_{sid}.lrc"
    title = t["title"]
    artist = t["artist"]
    album = t["album"]
    
    # 1. 下载
    subprocess.run([
        "yt-dlp", "--proxy", "http://127.0.0.1:7897",
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "-o", raw, f"https://www.youtube.com/watch?v={vid}"
    ], check=True)
    
    # 2. 压制
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
    lrc_q = f"张雨生 {t.get('lrc_title', title)}"
    lrc_content = search_lrc(lrc_q)
    has_lrc = False
    if lrc_content:
        with open(lrc, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        has_lrc = True
        
    # 4. 上传
    r2_audio_key = f"music/张雨生/{album}/s_{sid}.mp3"
    r2_lrc_key = f"lyrics/张雨生/{album}/s_{sid}.lrc"
    
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
