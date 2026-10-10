#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import boto3
import sqlite3
import requests
import subprocess
from botocore.config import Config

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))
from r2_safety_guard import safe_r2_put_object, pre_write_capacity_guard, get_r2_config

# 1. Config & S3 client
r2_cfg = get_r2_config()
target_acc = "account_13"
b_cfg = r2_cfg["buckets"][target_acc]
bucket_name = b_cfg["name"]
public_domain = b_cfg["public_url"].rstrip("/")

s3 = boto3.client(
    "s3",
    endpoint_url=b_cfg["endpoint_url"],
    aws_access_key_id=b_cfg["access_key_id"],
    aws_secret_access_key=b_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)

# 2. Local prepared files
work_dir = r"G:\music-backup\tmp\shouhuo_inspect\standardized"
t1_mp3 = os.path.join(work_dir, "s_29308.mp3")
t3_mp3 = os.path.join(work_dir, "s_29310.mp3")

assert os.path.exists(t1_mp3), f"Missing {t1_mp3}"
assert os.path.exists(t3_mp3), f"Missing {t3_mp3}"

# Accurate lyrics
lrc_29308 = """[00:00.00]刘若英 - Action(双瞳拍摄现场) (live)
[00:03.00]其实我有点累了，可是我会因为你继续的努力
[00:15.00]好来，先回位好，简单画面喔
[00:30.00]方圆圆再一次来，站到位置上来
[00:45.00]准备来，准备正式来，16-1开始开始！
""".strip().encode("utf-8")

lrc_29310 = """[00:00.00]刘若英 - Airport(2000Tokyo)
[00:05.00]（东京机场 / 地铁现场收音纪实）
""".strip().encode("utf-8")

# 3. Upload to R2 with Safety Guard
tasks = [
    {
        "id": 29308,
        "title": "Action(双瞳拍摄现场) (live)",
        "duration": 56,
        "audio_path": t1_mp3,
        "audio_key": "music/刘若英/收获 新歌+精选/s_29308.mp3",
        "lrc_bytes": lrc_29308,
        "lrc_key": "lyrics/刘若英/收获 新歌+精选/s_29308.lrc"
    },
    {
        "id": 29310,
        "title": "Airport(2000Tokyo)",
        "duration": 24,
        "audio_path": t3_mp3,
        "audio_key": "music/刘若英/收获 新歌+精选/s_29310.mp3",
        "lrc_bytes": lrc_29310,
        "lrc_key": "lyrics/刘若英/收获 新歌+精选/s_29310.lrc"
    }
]

print("=" * 70)
print("🚀 开始通过 R2 Safety Guard 上传音频与歌词到 account_13...")
print("=" * 70)

for t in tasks:
    sid = t["id"]
    title = t["title"]
    print(f"\n📦 处理 ID: {sid} ({title})")
    
    with open(t["audio_path"], "rb") as f:
        audio_body = f.read()
    
    # Pre-write capacity guard check
    pre_write_capacity_guard(target_acc, incoming_bytes=len(audio_body) + len(t["lrc_bytes"]))
    
    # Upload audio
    print(f"  Uploading audio ({len(audio_body)} bytes) -> {t['audio_key']}")
    safe_r2_put_object(
        s3_client=s3,
        bucket_name=bucket_name,
        account_key=target_acc,
        key=t["audio_key"],
        body=audio_body,
        content_type="audio/mpeg"
    )
    
    # Upload lyrics
    print(f"  Uploading lyrics ({len(t['lrc_bytes'])} bytes) -> {t['lrc_key']}")
    safe_r2_put_object(
        s3_client=s3,
        bucket_name=bucket_name,
        account_key=target_acc,
        key=t["lrc_key"],
        body=t["lrc_bytes"],
        content_type="text/plain; charset=utf-8"
    )
    
    # Compute Absolute CDN URLs (RFC-3986 encoding for + and chinese)
    # The URL in D1 uses requests.utils.quote with safe parameter
    enc_path_audio = requests.utils.quote(t["audio_key"], safe="/")
    enc_path_lrc = requests.utils.quote(t["lrc_key"], safe="/")
    
    t["cdn_audio_url"] = f"{public_domain}/{enc_path_audio}"
    t["cdn_lrc_url"] = f"{public_domain}/{enc_path_lrc}"
    
    print(f"  Audio CDN: {t['cdn_audio_url']}")
    print(f"  LRC CDN:   {t['cdn_lrc_url']}")
    
    # Verify HTTP 200 via HEAD
    r_audio = requests.head(t["cdn_audio_url"], timeout=10)
    r_lrc = requests.head(t["cdn_lrc_url"], timeout=10)
    print(f"  Verify Audio CDN HTTP: {r_audio.status_code}, Length: {r_audio.headers.get('content-length')}")
    print(f"  Verify LRC CDN HTTP:   {r_lrc.status_code}, Length: {r_lrc.headers.get('content-length')}")
    assert r_audio.status_code == 200, f"Audio CDN failed with {r_audio.status_code}"
    assert r_lrc.status_code == 200, f"LRC CDN failed with {r_lrc.status_code}"

print("\n" + "=" * 70)
print("💾 同步更新本地 catalog_sync.db 数据库...")
print("=" * 70)
local_db = os.path.join(BASE_DIR, "database", "catalog_sync.db")
conn = sqlite3.connect(local_db)
cur = conn.cursor()
for t in tasks:
    cur.execute(
        "UPDATE songs SET file_path = ?, lrc_path = ?, duration = ?, format = 'mp3', bit_rate = 160 WHERE id = ?",
        (t["cdn_audio_url"], t["cdn_lrc_url"], t["duration"], t["id"])
    )
conn.commit()
conn.close()
print("✅ 本地数据库更新成功！")

print("\n" + "=" * 70)
print("☁️ 同步更新 Cloudflare D1 远程数据库...")
print("=" * 70)
d1_dir = os.path.join(BASE_DIR, "cloudflare-worker")
for t in tasks:
    sql = f"UPDATE songs SET file_path = '{t['cdn_audio_url']}', lrc_path = '{t['cdn_lrc_url']}', duration = {t['duration']}, format = 'mp3', bit_rate = 160 WHERE id = {t['id']};"
    cmd = ["npx", "wrangler", "d1", "execute", "moody-d1-test", "--remote", "--command", sql]
    res = subprocess.run(cmd, cwd=d1_dir, capture_output=True, text=True, encoding='utf-8', errors='replace', shell=True)
    if res.returncode == 0:
        print(f"✅ D1 更新成功: ID {t['id']}")
    else:
        print(f"❌ D1 更新失败: ID {t['id']}, err: {res.stderr}")

print("\n" + "=" * 70)
print("🎉 治理与写入全流程验证完成！")
print("=" * 70)
