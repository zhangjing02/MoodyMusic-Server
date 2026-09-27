#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remediate_fish_26503.py
梁静茹《Sunrise 我喜欢》第 5 首《我和自己的约会》(ID: 26503) 录音室原版母带入库与点亮流水线
"""

import os
import sys
import json
import boto3
from botocore.config import Config
import requests
import sqlite3
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = 'e:/Workspace/AI-Project/MoodyMusic-Workspace'
CONFIG_PATH = os.path.join(BASE_DIR, 'backend', 'r2_config.json')
LOCAL_DB_PATH = os.path.join(BASE_DIR, 'backend', 'database', 'catalog_sync.db')
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

MP3_FILE = os.path.join(BASE_DIR, 'backend', 'tmp', 's_26503.mp3')
LRC_FILE = os.path.join(BASE_DIR, 'backend', 'tmp', 's_26503.lrc')

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

key_mp3 = "music/梁静茹/Sunrise 我喜欢/s_26503.mp3"
key_lrc = "lyrics/梁静茹/Sunrise 我喜欢/s_26503.lrc"

print("==================================================")
print("🚀 启动梁静茹《我和自己的约会》(ID: 26503) 官方母带入库...")
print("==================================================")

# 1. 校验本地压制文件
assert os.path.exists(MP3_FILE), f"MP3 missing: {MP3_FILE}"
assert os.path.exists(LRC_FILE), f"LRC missing: {LRC_FILE}"
mp3_size = os.path.getsize(MP3_FILE)
lrc_size = os.path.getsize(LRC_FILE)
print(f"📦 本地压制文件: MP3={mp3_size} 字节, LRC={lrc_size} 字节")

# 2. 上传至 account_10
print(f"📤 上传至主力桶 {b10_name}...")
with open(MP3_FILE, 'rb') as f:
    s3.put_object(
        Bucket=b10_name,
        Key=key_mp3,
        Body=f.read(),
        ContentType='audio/mpeg'
    )
print(f"  ✅ MP3 上传完毕: {key_mp3}")

with open(LRC_FILE, 'rb') as f:
    s3.put_object(
        Bucket=b10_name,
        Key=key_lrc,
        Body=f.read(),
        ContentType='text/plain; charset=utf-8'
    )
print(f"  ✅ LRC 上传完毕: {key_lrc}")

# 3. S3 HEAD 校验
head_mp3 = s3.head_object(Bucket=b10_name, Key=key_mp3)
head_lrc = s3.head_object(Bucket=b10_name, Key=key_lrc)
assert head_mp3['ContentLength'] == mp3_size, "MP3 size mismatch!"
assert head_lrc['ContentLength'] == lrc_size, "LRC size mismatch!"
print(f"🛡️ S3 HEAD 校验通过: MP3 ({head_mp3['ContentLength']} 字节), LRC ({head_lrc['ContentLength']} 字节)")

# 4. 生成绝对直链
# 根据三端规范，URL 可直接存 UTF-8 真实路径，Worker 与 CDN 原生兼容
cdn_mp3 = f"{b10_domain}/{key_mp3}"
cdn_lrc = f"{b10_domain}/{key_lrc}"

# 5. 调用 Cloudflare D1 batch-light
print(f"⚡ 调用 D1 batch-light 点亮...")
payload = {
    "updates": [
        {
            "id": 26503,
            "file_path": cdn_mp3,
            "lrc_path": cdn_lrc,
            "duration": 279,
            "is_lit": 1
        }
    ]
}

# 必须禁用代理直连 D1 网关
resp = requests.post(
    D1_LIGHT_URL,
    json=payload,
    headers={"Content-Type": "application/json"},
    proxies={'http': None, 'https': None},
    timeout=15
)
print(f"D1 batch-light response [{resp.status_code}]: {resp.text}")
assert resp.ok, f"D1 batch-light failed: {resp.text}"

# 6. 同步本地 catalog_sync.db
print(f"💾 同步更新本地数据库...")
conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()
cur.execute(
    "UPDATE songs SET file_path = ?, lrc_path = ?, duration = ? WHERE id = ?",
    (cdn_mp3, cdn_lrc, 279, 26503)
)
conn.commit()
conn.close()
print("  ✅ 本地数据库同步成功")

# 7. 公网 CDN 抽验
print(f"🌐 抽验公网 CDN 连通性...")
enc_key_mp3 = urllib.parse.quote(key_mp3)
test_mp3_url = f"{b10_domain}/{enc_key_mp3}"
r_cdn = requests.head(test_mp3_url, headers={'User-Agent': 'MoodyPlayer/1.0'}, timeout=10)
print(f"  • CDN MP3 HEAD [{r_cdn.status_code}] (Content-Length: {r_cdn.headers.get('Content-Length')})")
assert r_cdn.status_code == 200, f"CDN MP3 check failed: {r_cdn.status_code}"

enc_key_lrc = urllib.parse.quote(key_lrc)
test_lrc_url = f"{b10_domain}/{enc_key_lrc}"
r_lrc = requests.get(test_lrc_url, headers={'User-Agent': 'MoodyPlayer/1.0'}, timeout=10)
print(f"  • CDN LRC GET [{r_lrc.status_code}] (Content-Length: {len(r_lrc.content)})")
assert r_lrc.status_code == 200, f"CDN LRC check failed: {r_lrc.status_code}"

print("\n🎉 全部流水线执行成功！梁静茹《我和自己的约会》(ID: 26503) 官方正版音轨已就绪并点亮！")
