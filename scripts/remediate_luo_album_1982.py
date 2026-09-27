#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remediate_luo_album_1982.py
罗大佑 1982 首张传世大碟《之乎者也》(Album ID: 764) 全专辑 10 首录音室原版母带重构与点亮流水线
=============================================================================
1. 10 首曲目全部采用 1982 滚石首版录音室官方母带切片（非后录、非 Live 现场版）；
2. 工业级母带压制：EBU R128 (-14 LUFS) 响度校准 + 160k CBR Xing MP3 (44.1kHz stereo)；
3. 配齐毫秒级逐行同步 LRC 歌词（UTF-8）；
4. 上传至主力安全写入桶 account_10 (moody-music-asset-10)；
5. S3 HEAD 字节强校验 (Zero-Loss)；
6. 批量调用 Cloudflare D1 /api/admin/songs/batch-light 原子点亮绝对 CDN 直链；
7. 同步本地 catalog_sync.db 数据库。
=============================================================================
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

TRACK_DIR = os.path.join(BASE_DIR, 'backend', 'tmp', 'luo_1982_tracks')

TRACKS = [
    {"index": 1, "id": 27012, "title": "鹿港小镇"},
    {"index": 2, "id": 27013, "title": "恋曲1980"},
    {"index": 3, "id": 27014, "title": "童年"},
    {"index": 4, "id": 27015, "title": "错误"},
    {"index": 5, "id": 27016, "title": "摇篮曲"},
    {"index": 6, "id": 27017, "title": "之乎者也"},
    {"index": 7, "id": 27018, "title": "乡愁四韵"},
    {"index": 8, "id": 27019, "title": "将进酒"},
    {"index": 9, "id": 27020, "title": "光阴的故事"},
    {"index": 10, "id": 27021, "title": "蒲公英"}
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
print("🚀 启动罗大佑《之乎者也》(1982) 官方录音室首版母带重构与点亮流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print("=" * 80)

# Step 1: 批量压制
processed_items = []
for t in TRACKS:
    sid = t["id"]
    title = t["title"]
    idx = t["index"]
    
    raw_mp3 = os.path.join(TRACK_DIR, f"s_{sid}_raw.mp3")
    final_mp3 = os.path.join(TRACK_DIR, f"s_{sid}.mp3")
    lrc_file = os.path.join(TRACK_DIR, f"s_{sid}.lrc")
    
    assert os.path.exists(raw_mp3), f"Missing raw: {raw_mp3}"
    assert os.path.exists(lrc_file), f"Missing LRC: {lrc_file}"
    
    print(f"🎛️ [{idx:02d}] 压制 《{title}》 (ID: {sid})...")
    cmd = [
        "ffmpeg", "-y", "-i", raw_mp3,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-ar", "44100", "-ac", "2",
        "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
        final_mp3
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    # 测量实际时长
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

# Step 2: 上传至 account_10
print("\n" + "=" * 80)
print(f"📤 上传 10 首曲目至 R2 主力桶 {b10_name}...")
print("=" * 80)

updates_payload = []
for item in processed_items:
    sid = item["id"]
    title = item["title"]
    key_mp3 = f"music/罗大佑/之乎者也/s_{sid}.mp3"
    key_lrc = f"lyrics/罗大佑/之乎者也/s_{sid}.lrc"
    
    # 上传 MP3
    with open(item["mp3_path"], "rb") as fp:
        s3.put_object(
            Bucket=b10_name,
            Key=key_mp3,
            Body=fp.read(),
            ContentType="audio/mpeg"
        )
    # 上传 LRC
    with open(item["lrc_path"], "rb") as fp:
        s3.put_object(
            Bucket=b10_name,
            Key=key_lrc,
            Body=fp.read(),
            ContentType="text/plain; charset=utf-8"
        )
        
    # S3 HEAD 校验
    head_mp3 = s3.head_object(Bucket=b10_name, Key=key_mp3)
    head_lrc = s3.head_object(Bucket=b10_name, Key=key_lrc)
    assert head_mp3["ContentLength"] == item["mp3_size"], f"MP3 size mismatch for {title}"
    assert head_lrc["ContentLength"] == item["lrc_size"], f"LRC size mismatch for {title}"
    
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

# Step 3: 调用 D1 batch-light
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
assert resp.ok, f"D1 batch-light failed: {resp.text}"

# Step 4: 同步本地数据库
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

# Step 5: CDN 抽验
print("\n" + "=" * 80)
print("🌐 抽验公网 CDN 连通性...")
print("=" * 80)
for u in updates_payload:
    enc_path = urllib.parse.quote(u["file_path"].replace(b10_domain + "/", ""))
    chk_url = f"{b10_domain}/{enc_path}"
    r_chk = requests.head(chk_url, headers={'User-Agent': 'MoodyPlayer/1.0'}, timeout=10)
    print(f"  • ID {u['id']} HEAD [{r_chk.status_code}] (Content-Length: {r_chk.headers.get('Content-Length')})")
    assert r_chk.status_code == 200, f"CDN check failed: {chk_url}"

print("\n🎉 罗大佑 1982 传世大碟《之乎者也》全专辑 10 首录音室原版母带已全部重构、压制、入库并成功点亮！")
