#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对疑似严重货不对版曲目执行实地 Groq Whisper 听音核实验证
"""

import os
import sys
import json
import subprocess
import requests

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

SUSPECTS = [
    {"id": 25617, "artist": "陈奕迅", "album": "一滴眼淚", "title": "最好的禮物", "url": "https://pub-dd32e05660c74c3dba04d231391eb82b.r2.dev/music/陈奕迅/一滴眼淚/s_25617.mp3"},
    {"id": 25618, "artist": "陈奕迅", "album": "一滴眼淚", "title": "像一隻貓", "url": "https://pub-dd32e05660c74c3dba04d231391eb82b.r2.dev/music/陈奕迅/一滴眼淚/s_25618.mp3"},
    {"id": 24170, "artist": "王菲", "album": "將愛", "title": "花事了", "url": "https://pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev/music/王菲/將愛/s_24170.mp3"},
    {"id": 24168, "artist": "王菲", "album": "將愛", "title": "MV", "url": "https://pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev/music/王菲/將愛/s_24168.mp3"},
    {"id": 25796, "artist": "动力火车", "album": "结伴", "title": "逆流", "url": "https://pub-dd32e05660c74c3dba04d231391eb82b.r2.dev/music/动力火车/结伴/s_25796.mp3"},
    {"id": 25795, "artist": "动力火车", "album": "结伴", "title": "我这个你不爱的人", "url": "https://pub-dd32e05660c74c3dba04d231391eb82b.r2.dev/music/动力火车/结伴/s_25795.mp3"},
    {"id": 59, "artist": "阿杜", "album": "沒什麼好怕", "title": "沒什麼好怕", "url": "https://pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev/music/阿杜/沒什麼好怕/s_59.mp3"},
]

def extract_and_transcribe(url, sid, ss=30, t=30):
    tmp_clip = f"/tmp/verify_{sid}.mp3"
    if os.path.exists(tmp_clip):
        os.remove(tmp_clip)
    cmd = [
        "ffmpeg", "-y", "-ss", str(ss), "-t", str(t),
        "-i", url, "-ac", "1", "-ar", "16000", "-b:a", "64k", tmp_clip
    ]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if r.returncode != 0 or not os.path.exists(tmp_clip) or os.path.getsize(tmp_clip) < 500:
            return "FFMPEG_EXTRACTION_FAILED"
        
        with open(tmp_clip, "rb") as f:
            resp = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": (f"verify_{sid}.mp3", f, "audio/mpeg")},
                data={"model": "whisper-large-v3", "temperature": "0.0"},
                timeout=25
            )
        if os.path.exists(tmp_clip):
            os.remove(tmp_clip)
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        else:
            return f"GROQ_ERROR_{resp.status_code}: {resp.text}"
    except Exception as e:
        if os.path.exists(tmp_clip): os.remove(tmp_clip)
        return f"EXCEPTION: {e}"

def main():
    print("=" * 80)
    print("🎧 开始对疑似货不对版歌曲进行实地 Groq Whisper AI 人声盲听验证...")
    print("=" * 80)
    for it in SUSPECTS:
        sid = it['id']
        art = it['artist']
        title = it['title']
        url = it['url']
        print(f"\n▶ [{art}] 《{title}》 (ID: {sid})")
        print(f"   URL: {url}")
        heard = extract_and_transcribe(url, sid, ss=30, t=30)
        print(f"   🗣️ [Whisper 转写]: {heard}")
        
if __name__ == "__main__":
    main()
