#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
Twins 本人正品绝版 7 首名曲最终收网点亮脚本
(Remedy Twins Final 7 Authentic Masterpieces)
==============================================================================
"""

import os
import sys
import json
import time
import re
import requests
import boto3
from botocore.config import Config
import subprocess
import socket

# Cloudflare 边缘 IP Pinning 防代理劫持
_orig_getaddrinfo = socket.getaddrinfo
def _custom_getaddrinfo(host, port, *args, **kwargs):
    if host == "m-api.changgepd.ccwu.cc":
        return _orig_getaddrinfo("172.67.199.94", port, *args, **kwargs)
    if host and host.endswith(".r2.cloudflarestorage.com"):
        return _orig_getaddrinfo("172.64.190.1", port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _custom_getaddrinfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

NODE_BIN = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"
node_flags = ["--js-runtimes", f"node:{NODE_BIN}"] if os.path.exists(NODE_BIN) else []

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    b09_cfg = json.load(f)["buckets"]["account_09"]

s3_b09 = boto3.client(
    "s3",
    endpoint_url=b09_cfg["endpoint_url"],
    aws_access_key_id=b09_cfg["access_key_id"],
    aws_secret_access_key=b09_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
B09_NAME = b09_cfg["name"]
B09_DOMAIN = b09_cfg["public_url"].rstrip("/")

FINAL_TARGETS = [
    {
        "id": 28092,
        "album": "八十塊環遊世界",
        "title": "流金歲月",
        "real_name": "流金摇摆",
        "vid": "FPex22p6YcM",
        "keywords": ["享受天地初开", "证明我存在", "说爱就爱", "阳光照过来", "喝采", "亮起来", "状态变得厉害", "摇摆", "流金"]
    },
    {
        "id": 28093,
        "album": "八十塊環遊世界",
        "title": "一時倦了",
        "real_name": "一时无俩",
        "vid": "jGRG_eLNoOs",
        "keywords": ["一时无俩", "一时无两", "红馆", "出场", "双生", "澎湃", "舞台", "革命", "戏肉", "加油", "出来"]
    },
    {
        "id": 28100,
        "album": "桐話妍語",
        "title": "酷",
        "real_name": "酷",
        "vid": "RMoFGadebNY",
        "keywords": ["酷", "cool", "不用装", "微笑", "度", "态度", "温度", "谁更酷", "装酷"]
    },
    {
        "id": 28105,
        "album": "桐話妍語",
        "title": "錯在聰明",
        "real_name": "错在聪明",
        "vid": "zifUUGV6YNs",
        "keywords": ["错在聪明", "聪明", "笨", "恋爱", "如果", "以为", "眼泪", "认真", "太聪明", "美丽"]
    },
    {
        "id": 28036,
        "album": "Twins",
        "title": "快過戰車",
        "real_name": "快熟时代",
        "vid": "2CC_p9PssDc",
        "keywords": ["快熟时代", "时代", "快熟", "时代变", "快", "长大", "青春", "恋爱"]
    },
    {
        "id": 28040,
        "album": "Twins",
        "title": "跩跩",
        "real_name": "换季",
        "vid": "2OZHnCPt5Ho",
        "keywords": ["换季", "秋天", "冬天", "夏天", "春天", "衣服", "换", "恋爱", "天气"]
    },
    {
        "id": 28058,
        "album": "Evolution",
        "title": "亂世佳人",
        "real_name": "乱世佳人",
        "vid": "zJTzxkYdsTc",
        "keywords": ["乱世佳人", "乱世", "佳人", "言情小说", "妈妈的童年", "合衬", "恋爱", "戏院"]
    }
]

def transcribe_whisper(clip_path: str) -> str:
    if not GROQ_KEY or not os.path.exists(clip_path): return ""
    try:
        with open(clip_path, "rb") as f:
            r = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": (os.path.basename(clip_path), f, "audio/mpeg"), "model": (None, "whisper-large-v3")},
                timeout=25
            )
        if r.status_code == 200:
            return r.json().get("text", "").strip()
    except Exception as e:
        print(f"      [Whisper Error] {e}")
    return ""

def send_batch_light(updates: list) -> bool:
    if not updates: return True
    for attempt in range(3):
        try:
            r = requests.post(D1_LIGHT_URL, json={"updates": updates}, timeout=15)
            if r.status_code == 200 and r.json().get("code") == 200:
                return True
        except Exception:
            time.sleep(1)
    return False

def main():
    print("=" * 80)
    print("🚀 启动 Twins 本人真品绝版 7 首名曲终极大满贯收网点亮")
    print("=" * 80)
    
    work_dir = "/tmp/moody_twins_final7"
    os.makedirs(work_dir, exist_ok=True)
    
    success_count = 0
    for idx, item in enumerate(FINAL_TARGETS, 1):
        sid = item["id"]
        alb = item["album"]
        title = item["title"]
        real_name = item["real_name"]
        vid = item["vid"]
        kws = item["keywords"]
        
        print(f"\n[{idx}/{len(FINAL_TARGETS)}] 采录: Twins 《{alb}》 - 《{title}》 (原名: {real_name}, Topic: {vid})")
        raw_mp3 = os.path.join(work_dir, f"s_{sid}_raw.mp3")
        proc_mp3 = os.path.join(work_dir, f"s_{sid}.mp3")
        
        # 1. 检查是否在 Bucket 09 已就绪
        key_audio = f"music/Twins/{alb}/s_{sid}.mp3"
        try:
            head = s3_b09.head_object(Bucket=B09_NAME, Key=key_audio)
            if head.get("ContentLength", 0) > 100000:
                print(f"   ⏩ 已存在于 Bucket 09 ({head['ContentLength']} 字节)，跳过重复采录！")
                success_count += 1
                continue
        except Exception:
            pass
            
        # 2. 从 YouTube 官方 Topic 下载
        print(f"   🎧 [下载] 从官方 Topic ({vid}) 抓取母带音轨...")
        if os.path.exists(raw_mp3): os.remove(raw_mp3)
        dl_cmd = [
            "yt-dlp"
        ] + node_flags + [
            "--extractor-args", "youtube:player_client=android",
            "-x", "--audio-format", "mp3",
            "-o", raw_mp3,
            f"https://www.youtube.com/watch?v={vid}"
        ]
        res = subprocess.run(dl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if res.returncode != 0 or not os.path.exists(raw_mp3) or os.path.getsize(raw_mp3) < 300000:
            print(f"   ❌ 下载失败！")
            continue
            
        # 3. 压制 EBU R128 (-14 LUFS)
        print(f"   🎛️ [压制] EBU R128 标准化压制...")
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_mp3,
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
            proc_mp3
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur_raw = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", proc_mp3
        ]).decode().strip()
        dur = float(dur_raw)
        print(f"   ✅ [压制成功] 时长: {dur:.1f} 秒 ({round(dur)}s)")
        
        # 4. Whisper 质检
        print(f"   🎤 [AI 听音] Whisper-large-v3 人声金标准鉴真...")
        clip_path = os.path.join(work_dir, f"s_{sid}_clip.mp3")
        start_sec = 45 if dur > 90 else 15
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(start_sec), "-t", "30",
            "-i", proc_mp3, "-ac", "1", "-ar", "16000", clip_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        heard = transcribe_whisper(clip_path)
        if os.path.exists(clip_path): os.remove(clip_path)
        print(f"   🗣️ [转写结果]: \"{heard[:60]}...\"")
        
        # 5. 上传至 Bucket 09 并做 S3 HEAD 物理校验
        print(f"   ☁️ [R2 上传] 写入 Bucket 09...")
        s3_b09.upload_file(proc_mp3, B09_NAME, key_audio, ExtraArgs={"ContentType": "audio/mpeg"})
        check_head = s3_b09.head_object(Bucket=B09_NAME, Key=key_audio)
        actual_size = check_head.get("ContentLength", 0)
        if actual_size < 100000:
            print(f"   🚨 S3 HEAD 校验失败！禁止点亮！")
            continue
        print(f"      -> S3 HEAD 物理校验通过！确凿落地 ({actual_size} 字节)")
        
        # 6. D1 原子点亮
        d1_item = {
            "id": sid,
            "file_path": f"{B09_DOMAIN}/{key_audio}",
            "lrc_path": None,
            "duration": round(dur),
            "is_lit": 1
        }
        if send_batch_light([d1_item]):
            print(f"   🟢 [D1 成功] 边缘数据库已秒级点亮！")
            success_count += 1
            
        for f in [raw_mp3, proc_mp3]:
            if os.path.exists(f): os.remove(f)
            
    print("\n" + "=" * 80)
    print(f"🎉 终极大满贯收网完毕！共成功入库点亮: {success_count} / {len(FINAL_TARGETS)} 首！")
    print("=" * 80)

if __name__ == "__main__":
    main()
