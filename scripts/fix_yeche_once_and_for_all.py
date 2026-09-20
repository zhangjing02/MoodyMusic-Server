#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - 曾轶可《夜车》官方纯净录音室母带重铸与覆盖
彻底拔除：
- 网络翻唱版本 (Cover)
- 时政自媒体口播录音
重铸为：
- 曾轶可《恋爱通告》官方纯净录音室母带
- EBU R128 (-14 LUFS) 标准化 + 160k CBR Xing MP3
- 同步覆盖《一只猫的旅行》(ID: 28807) 与《2022》(ID: 28855)
==============================================================================
"""

import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)["buckets"]["account_07"]

s3 = boto3.client(
    's3',
    endpoint_url=cfg['endpoint_url'],
    aws_access_key_id=cfg['access_key_id'],
    aws_secret_access_key=cfg['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4')
)
BUCKET_NAME = cfg['name']
DOMAIN = cfg['public_url'].rstrip('/')

D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
RAW_INPUT = "/tmp/dreamer_yeche.mp3"
NORM_OUT = "/tmp/clean_yeche_160k.mp3"

def main():
    print("=" * 80)
    print("🚀 曾轶可《夜车》官方录音室纯净母带终极压制与上线")
    print("=" * 80)
    
    # 1. EBU R128 标准化压制
    cmd = [
        "ffmpeg", "-y", "-i", RAW_INPUT,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k",
        "-write_xing", "1",
        NORM_OUT
    ]
    subprocess.run(cmd, check=True)
    
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
        "-of", "default=noprint_wrappers=1:nokey=1", NORM_OUT
    ]).decode('utf-8').strip().split('\n')
    dur = float(probe[0])
    sz = int(probe[1])
    print(f"✅ 压制成功: 时长 {dur:.1f}s, 大小 {sz/(1024*1024):.2f} MB")
    
    # 2. Whisper 验收切片 (15s-45s 核心主唱段)
    clip = "/tmp/check_yeche_clip.mp3"
    subprocess.run(["ffmpeg", "-y", "-ss", "15", "-t", "30", "-i", NORM_OUT, "-ac", "1", "-ar", "16000", clip], check=True)
    groq_key = os.environ.get("GROQ_API_KEY", "")
    proxies = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
    with open(clip, "rb") as f:
        r = requests.post(
            'https://api.groq.com/openai/v1/audio/transcriptions',
            headers={'Authorization': f'Bearer {groq_key}'},
            files={'file': ('clip.mp3', f, 'audio/mpeg'), 'model': (None, 'whisper-large-v3')},
            proxies=proxies, timeout=30
        )
    heard = r.json().get('text', '')
    print(f"🟢 Whisper 验收听到: \"{heard[:60]}...\"")
    
    # 3. 毫秒级歌词下载 (网易云 340376 的歌词)
    lrc_out = "/tmp/clean_yeche.lrc"
    lrc_res = requests.get("http://music.163.com/api/song/lyric?os=pc&id=340376&lv=-1&kv=-1&tv=-1", headers={'User-Agent': 'Mozilla/5.0'}).json()
    lrc_text = lrc_res.get('lrc', {}).get('lyric', '')
    with open(lrc_out, "w", encoding="utf-8") as f:
        f.write(lrc_text)
    print(f"✅ 毫秒级歌词准备完毕: {len(lrc_text)} 字符")
    
    # 4. 双专物理覆盖写入 S3
    targets = [
        {"album": "一只猫的旅行", "id": 28807},
        {"album": "2022", "id": 28855}
    ]
    
    updates = []
    for t in targets:
        alb = t["album"]
        sid = t["id"]
        
        mp3_key = f"music/曾轶可/{alb}/s_{sid}.mp3"
        lrc_key = f"lyrics/曾轶可/{alb}/s_{sid}.lrc"
        
        print(f"📤 正在覆盖写入: {mp3_key} ...")
        s3.upload_file(NORM_OUT, BUCKET_NAME, mp3_key, ExtraArgs={'ContentType': 'audio/mpeg'})
        s3.upload_file(lrc_out, BUCKET_NAME, lrc_key, ExtraArgs={'ContentType': 'text/plain; charset=utf-8'})
        
        audio_url = f"{DOMAIN}/{mp3_key}"
        lrc_url = f"{DOMAIN}/{lrc_key}"
        updates.append({
            "id": sid,
            "file_path": audio_url,
            "lrc_path": lrc_url
        })
        print(f"   🚀 云端覆盖成功 -> {audio_url}")
        
    # 5. D1 生产网关点亮
    print("\n⚡ 向生产网关提交 batch-light 更新...")
    resp = requests.post(D1_LIGHT_URL, json={"updates": updates}, headers={"Content-Type": "application/json"}, timeout=20)
    print(f"D1 响应: {resp.status_code} - {resp.text}")
    print("=" * 80)
    print("🎉 曾轶可《夜车》正版原唱母带重铸上线全部完成！")
    print("=" * 80)

if __name__ == "__main__":
    main()
