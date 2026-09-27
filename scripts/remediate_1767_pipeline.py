#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remediate_1767_pipeline.py
罗大佑 1983 经典神专《未来的主人翁》(Album ID: 1767) 录音室首版母带重构、压制与点亮流水线
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

FULL_AUDIO = os.path.join(BASE_DIR, 'backend', 'tmp', 'future_master_full.mp3')
TRACK_DIR = os.path.join(BASE_DIR, 'backend', 'tmp', 'luo_1767_tracks')
os.makedirs(TRACK_DIR, exist_ok=True)

TRACKS = [
    {"index": 1, "id": 27022, "title": "诞生", "start": 0, "dur": 108},
    {"index": 2, "id": 27023, "title": "亚细亚的孤儿", "start": 108, "dur": 351},
    {"index": 3, "id": 27024, "title": "现象七十二变", "start": 459, "dur": 231},
    {"index": 4, "id": 27025, "title": "牧童", "start": 690, "dur": 202},
    {"index": 5, "id": 27026, "title": "未来的主人翁", "start": 892, "dur": 450},
    {"index": 6, "id": 27027, "title": "青春舞曲", "start": 1342, "dur": 212},
    {"index": 7, "id": 27028, "title": "爱的箴言", "start": 1554, "dur": 206},
    {"index": 8, "id": 27029, "title": "小妹", "start": 1760, "dur": 370},
    {"index": 9, "id": 27030, "title": "盲聋", "start": 2130, "dur": 248},
    {"index": 10, "id": 27031, "title": "稻草人", "start": 2378, "dur": 402}
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
print("🚀 启动《未来的主人翁》(1983) 10 首曲目首版母带切片、压制与上云流水线...")
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
    key_mp3 = f"music/罗大佑/未来的主人翁/s_{sid}.mp3"
    key_lrc = f"lyrics/罗大佑/未来的主人翁/s_{sid}.lrc"
    
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

print("\n🎉 罗大佑 1983 经典大碟《未来的主人翁》全专辑 10 首录音室原版母带已全部重构、压制、入库并成功点亮！")
