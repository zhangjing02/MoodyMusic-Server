#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remediate_757_shining.py
罗大佑 1989《闪亮的日子 (1974-1981)》(Album ID: 757) 10首录音室母带 LRC与时长全面点亮
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
TRACK_DIR = os.path.join(BASE_DIR, 'backend', 'tmp', 'album_757')
os.makedirs(TRACK_DIR, exist_ok=True)

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

TRACKS = [
    {"id": 10373, "title": "閃亮的日子", "netease_id": 108426},
    {"id": 10374, "title": "歌", "netease_id": 108427},
    {"id": 10375, "title": "神話", "netease_id": 108428},
    {"id": 10376, "title": "旅程", "netease_id": 108429},
    {"id": 10377, "title": "是否", "netease_id": 108430},
    {"id": 10378, "title": "風兒你在輕輕的吹", "netease_id": 108431},
    {"id": 10379, "title": "光陰的故事", "netease_id": 108432},
    {"id": 10380, "title": "戀曲1980", "netease_id": 108433},
    {"id": 10381, "title": "癡癡的等", "netease_id": 108434},
    {"id": 10382, "title": "愛的箴言", "netease_id": 108435}
]

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

updates_payload = []

print("=" * 80)
print("🚀 开始处理《闪亮的日子》(1989, Album ID: 757) 10 首录音室歌曲...")
print("=" * 80)

for t in TRACKS:
    sid = t["id"]
    title = t["title"]
    nid = t["netease_id"]
    
    cur.execute("SELECT file_path FROM songs WHERE id = ?", (sid,))
    fpath = cur.fetchone()[0]
    
    # 探查音频真实时长
    local_sample = os.path.join(TRACK_DIR, f"s_{sid}.mp3")
    if not os.path.exists(local_sample) or os.path.getsize(local_sample) < 1000:
        parsed = urllib.parse.urlsplit(fpath)
        u_enc = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, urllib.parse.quote(parsed.path), '', ''))
        req = urllib.request.Request(u_enc, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp, open(local_sample, 'wb') as fp:
            fp.write(resp.read())
            
    out_dur = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", local_sample
    ]).decode().strip()
    dur_int = round(float(out_dur))
    
    # 获取高精度 LRC
    lrc_local = os.path.join(TRACK_DIR, f"s_{sid}.lrc")
    if not os.path.exists(lrc_local) or os.path.getsize(lrc_local) < 50:
        r_lrc = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1", headers={'User-Agent': 'Mozilla/5.0'}).json()
        lrc_text = r_lrc.get('lrc', {}).get('lyric', '')
        with open(lrc_local, 'w', encoding='utf-8') as fp:
            fp.write(lrc_text.strip() + '\n')
            
    lrc_size = os.path.getsize(lrc_local)
    key_lrc = f"lyrics/罗大佑/閃亮的日子/s_{sid}.lrc"
    with open(lrc_local, 'rb') as fp:
        s3.put_object(Bucket=b10_name, Key=key_lrc, Body=fp.read(), ContentType="text/plain; charset=utf-8")
        
    head_lrc = s3.head_object(Bucket=b10_name, Key=key_lrc)
    assert head_lrc["ContentLength"] == lrc_size
    cdn_lrc = f"{b10_domain}/{key_lrc}"
    
    print(f"  ✅ [{sid}] 《{title}》: 时长 {dur_int}s | LRC 上传成功 -> {cdn_lrc}")
    
    updates_payload.append({
        "id": sid,
        "file_path": fpath,
        "lrc_path": cdn_lrc,
        "duration": dur_int,
        "is_lit": 1
    })

print("\n⚡ 调用 D1 batch-light 更新...")
resp = requests.post(
    D1_LIGHT_URL,
    json={"updates": updates_payload},
    headers={"Content-Type": "application/json"},
    proxies={'http': None, 'https': None},
    timeout=20
)
print(f"D1 batch-light 返回: {resp.text}")
assert resp.ok

print("💾 同步本地数据库...")
for u in updates_payload:
    cur.execute("UPDATE songs SET lrc_path = ?, duration = ? WHERE id = ?", (u["lrc_path"], u["duration"], u["id"]))
conn.commit()
conn.close()

print("\n🎉 《闪亮的日子》(1989, 10 首录音室经典) 歌词与元数据全面点亮完成！")
