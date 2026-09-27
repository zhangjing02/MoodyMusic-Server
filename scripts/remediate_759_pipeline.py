#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remediate_759_pipeline.py
罗大佑 1988 传世神专《爱人同志》(Album ID: 759) 录音室首版母带切片、压制与点亮流水线
"""

import os
import sys
import json
import boto3
from botocore.config import Config
import requests
import sqlite3
import urllib.parse
import subprocess

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = 'e:/Workspace/AI-Project/MoodyMusic-Workspace'
CONFIG_PATH = os.path.join(BASE_DIR, 'backend', 'r2_config.json')
LOCAL_DB_PATH = os.path.join(BASE_DIR, 'backend', 'database', 'catalog_sync.db')
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

FULL_AUDIO = os.path.join(BASE_DIR, 'backend', 'tmp', 'lover_1988_full.mp3')
TRACK_DIR = os.path.join(BASE_DIR, 'backend', 'tmp', 'luo_759_tracks')
os.makedirs(TRACK_DIR, exist_ok=True)

TRACKS = [
    {"index": 1, "id": 10393, "title": "暗恋", "start": 0.0, "dur": 214.3},
    {"index": 2, "id": 10394, "title": "恋曲1990", "start": 218.5, "dur": 307.9},
    {"index": 3, "id": 10395, "title": "爱人同志", "start": 534.5, "dur": 237.6},
    {"index": 4, "id": 10396, "title": "你的样子", "start": 784.5, "dur": 202.8},
    {"index": 5, "id": 10397, "title": "梦", "start": 992.2, "dur": 261.3},
    {"index": 6, "id": 10398, "title": "黄色脸孔", "start": 1260.3, "dur": 243.4},
    {"index": 7, "id": 10399, "title": "京城夜", "start": 1510.3, "dur": 256.5},
    {"index": 8, "id": 10400, "title": "明天的太阳", "start": 1770.7, "dur": 231.0},
    {"index": 9, "id": 10401, "title": "游戏规则", "start": 2005.7, "dur": 205.0},
    {"index": 10, "id": 10402, "title": "不变的结局", "start": 2214.9, "dur": 313.2}
]

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    cfg = json.load(f)['buckets']

target_bucket_info = cfg['account_10']
b10_name = target_bucket_info['name']
b10_domain = target_bucket_info['public_domain'].rstrip('/')

s3 = boto3.client(
    's3',
    endpoint_url=target_bucket_info['endpoint_url'],
    aws_access_key_id=target_bucket_info['access_key_id'],
    aws_secret_access_key=target_bucket_info['secret_access_key'],
    config=Config(signature_version='s3v4')
)

print("=" * 80)
print("🚀 启动《爱人同志》(1988) 10 首曲目首版母带切片、压制与上云流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print("=" * 80)

processed_items = []
for t in TRACKS:
    sid = t["id"]
    title = t["title"]
    idx = t["index"]
    st = t["start"]
    dur = t["dur"]
    
    final_mp3 = os.path.join(TRACK_DIR, f"s_{sid}.mp3")
    lrc_file = os.path.join(TRACK_DIR, f"s_{sid}.lrc")
    
    assert os.path.exists(lrc_file), f"Missing LRC: {lrc_file}"
    
    print(f"🎛️ [{idx:02d}] 切片并压制 《{title}》 (ID: {sid}, 起始:{st}s, 预计:{dur}s)...")
    cmd = [
        "ffmpeg", "-y", "-ss", str(st), "-i", FULL_AUDIO,
        "-t", str(dur),
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-ar", "44100", "-ac", "2",
        "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
        final_mp3
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    out_dur = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", final_mp3
    ]).decode().strip()
    dur_int = round(float(out_dur))
    
    mp3_size = os.path.getsize(final_mp3)
    lrc_size = os.path.getsize(lrc_file)
    print(f"   ✅ 时长: {dur_int}s | 体积: MP3={mp3_size} 字节, LRC={lrc_size} 字节")
    
    processed_items.append({
        "id": sid,
        "title": title,
        "index": idx,
        "mp3_path": final_mp3,
        "lrc_path": lrc_file,
        "duration": dur_int,
        "mp3_size": mp3_size,
        "lrc_size": lrc_size
    })

# 上传至 account_10
print("\n" + "=" * 80)
print(f"📤 上传 10 首曲目至 R2 主力桶 {b10_name}...")
print("=" * 80)

updates_payload = []
for item in processed_items:
    sid = item["id"]
    title = item["title"]
    key_mp3 = f"music/罗大佑/爱人同志/s_{sid}.mp3"
    key_lrc = f"lyrics/罗大佑/爱人同志/s_{sid}.lrc"
    
    # MP3
    with open(item["mp3_path"], "rb") as fp:
        s3.put_object(Bucket=b10_name, Key=key_mp3, Body=fp.read(), ContentType="audio/mpeg")
    # LRC
    with open(item["lrc_path"], "rb") as fp:
        s3.put_object(Bucket=b10_name, Key=key_lrc, Body=fp.read(), ContentType="text/plain; charset=utf-8")
        
    head_mp3 = s3.head_object(Bucket=b10_name, Key=key_mp3)
    head_lrc = s3.head_object(Bucket=b10_name, Key=key_lrc)
    assert head_mp3["ContentLength"] == item["mp3_size"]
    assert head_lrc["ContentLength"] == item["lrc_size"]
    
    cdn_mp3 = f"{b10_domain}/{key_mp3}"
    cdn_lrc = f"{b10_domain}/{key_lrc}"
    
    updates_payload.append({
        "id": sid,
        "file_path": cdn_mp3,
        "lrc_path": cdn_lrc,
        "duration": item["duration"],
        "is_lit": 1
    })
    print(f"  ✅ [S3 HEAD OK] 《{title}》 -> {cdn_mp3}")

# D1 batch-light
print("\n" + "=" * 80)
print("⚡ 调用 Cloudflare D1 batch-light 原子点亮...")
print("=" * 80)

resp = requests.post(
    D1_LIGHT_URL,
    json={"updates": updates_payload},
    headers={"Content-Type": "application/json"},
    proxies={'http': None, 'https': None},
    timeout=20
)
print(f"D1 batch-light 返回 [{resp.status_code}]: {resp.text}")
assert resp.ok, f"D1 failed: {resp.text}"

# 同步本地数据库
print("\n" + "=" * 80)
print("💾 同步更新本地 catalog_sync.db 数据库...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()
for u in updates_payload:
    cur.execute(
        "UPDATE songs SET file_path = ?, lrc_path = ?, duration = ? WHERE id = ?",
        (u["file_path"], u["lrc_path"], u["duration"], u["id"])
    )
conn.commit()
conn.close()
print("  ✅ 本地数据库同步成功！")

# CDN 抽验
print("\n" + "=" * 80)
print("🌐 抽验公网 CDN 连通性...")
print("=" * 80)
for u in updates_payload:
    enc_path = urllib.parse.quote(u["file_path"].replace(b10_domain + "/", ""))
    chk_url = f"{b10_domain}/{enc_path}"
    r_chk = requests.head(chk_url, headers={'User-Agent': 'Mozilla/5.0'}, proxies={'http': None, 'https': None}, timeout=10)
    print(f"  • ID {u['id']} HEAD [{r_chk.status_code}] (Content-Length: {r_chk.headers.get('Content-Length')})")
    assert r_chk.status_code == 200

print("\n🎉 罗大佑 1988 传世神专《爱人同志》全专辑 10 首录音室原版母带已全部重构、压制、入库并成功点亮！")
