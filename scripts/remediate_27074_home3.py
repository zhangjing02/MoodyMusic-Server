#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remediate_27074_home3.py
处理并点亮 罗大佑 2017《家 (III)》同名主打歌 (Song ID: 27074)
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

RAW_AUDIO = os.path.join(BASE_DIR, 'backend', 'tmp', 'home3_raw.mp3')
FINAL_MP3 = os.path.join(BASE_DIR, 'backend', 'tmp', 's_27074.mp3')
FINAL_LRC = os.path.join(BASE_DIR, 'backend', 'tmp', 's_27074.lrc')

LRC_CONTENT = """[ti:家(III)]
[ar:罗大佑]
[al:家 (III)]
[by:MoodyMusic]
[00:00.00]家 (III) - 罗大佑
[00:01.00]词：罗大佑
[00:02.00]曲：罗大佑
[00:30.04]本是同根而生的人们
[00:33.43]相聚成你的家或我的家
[00:37.14]将时光流转或是月圆花好
[00:40.59]刻在荧幕之上阳光之下
[00:44.56]展翅高飞的人儿离开
[00:47.91]就此穿越时空告别
[00:51.54]就不声不响或许不堪回首
[00:55.11]绝非不闻不问来告解
[00:59.23]给我个温暖的满怀着温暖的
[01:02.49]彼此关照的家庭
[01:06.14]让兄弟姐妹怀抱父母慈祥的爱
[01:09.61]依然成长在心灵
[01:13.32]给我些温暖的体谅而坚强的
[01:16.96]彼此保护的心情
[01:20.61]但愿成长在日后寒暑狂风暴雨里
[01:24.26]有颗不变的心
[01:28.47]如此相近的人们相处
[01:31.62]却只有如此人会懂
[01:35.30]那矛盾就与幸福一同天作之合
[01:38.83]潜伏存在冥冥之中
[01:42.79]总有一天
[01:44.31]等骨肉愈合团圆到那时刻
[01:48.07]谁能预测
[01:49.84]就不声不响或许不堪回首
[01:53.17]绝非不闻不问的纠扯
[01:57.36]给我个温暖的满怀着温暖的
[02:00.67]不愿纷争的家庭
[02:04.29]让窗外有蓝天绿草也如茵
[02:08.01]再来点白云
[02:11.71]给我些温暖的体谅而坚强的
[02:15.83]彼此保护的心情
[02:19.07]但愿成长在日后寒暑狂风暴雨里
[02:22.48]有颗不变的心
[02:41.52]本是同根而生的人们
[02:44.09]相聚成你的家或我的家
[02:48.08]将时光流转或是月圆花好
[02:51.40]刻在荧幕之上阳光之下
[02:55.49]展翅高飞的人儿
[02:57.99]离开是否穿越时空告别
[03:02.64]到那天忽然重现在你面前
[03:06.04]对你再次微笑才发觉
[03:09.82]给我个温暖的满怀着温暖的
[03:13.35]不愿纷争的家庭
[03:17.10]让兄弟姊妹怀抱父母慈祥的爱
[03:20.75]依然成长在心灵
[03:24.35]给我些温暖的体谅而坚强的
[03:27.94]彼此保护的心情
[03:31.62]但愿成长在日后寒暑狂风暴雨里
[03:35.66]有颗不变的心
[03:38.92]给我个温暖的满怀着温暖的
[03:42.55]彼此关照的家庭
[03:46.11]让窗外有蓝天绿草也如茵
[03:49.66]再来点白云
[03:53.39]给我些温暖的体谅而坚强的
[03:57.02]彼此保护的心情
[04:00.67]但愿成长在日后寒暑狂风暴雨里
[04:04.17]有颗不变的心
[04:08.07]但愿成长在日后寒暑狂风暴雨里
[04:11.55]有颗不变的心
[04:15.24]但愿成长在日后寒暑狂风暴雨里
[04:18.92]有颗不变的心
"""

with open(FINAL_LRC, "w", encoding="utf-8") as f:
    f.write(LRC_CONTENT.strip() + "\n")

print("🎛️ 1. 压制 160k CBR + EBU R128 (-14 LUFS)...")
cmd = [
    "ffmpeg", "-y", "-i", RAW_AUDIO,
    "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
    "-ar", "44100", "-ac", "2",
    "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
    FINAL_MP3
]
subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

out_dur = subprocess.check_output([
    "ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", FINAL_MP3
]).decode().strip()
dur_int = round(float(out_dur))
mp3_size = os.path.getsize(FINAL_MP3)
lrc_size = os.path.getsize(FINAL_LRC)
print(f"   ✅ 时长: {dur_int}s | 体积: MP3={mp3_size} 字节, LRC={lrc_size} 字节")

# 上传至 account_10
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

key_mp3 = "music/罗大佑/家 (III)/s_27074.mp3"
key_lrc = "lyrics/罗大佑/家 (III)/s_27074.lrc"

print(f"📤 2. 上传至 R2 {b10_name}...")
with open(FINAL_MP3, "rb") as fp:
    s3.put_object(Bucket=b10_name, Key=key_mp3, Body=fp.read(), ContentType="audio/mpeg")
with open(FINAL_LRC, "rb") as fp:
    s3.put_object(Bucket=b10_name, Key=key_lrc, Body=fp.read(), ContentType="text/plain; charset=utf-8")

head_mp3 = s3.head_object(Bucket=b10_name, Key=key_mp3)
head_lrc = s3.head_object(Bucket=b10_name, Key=key_lrc)
assert head_mp3["ContentLength"] == mp3_size
assert head_lrc["ContentLength"] == lrc_size
print("   ✅ S3 HEAD 校验一致通过！")

cdn_mp3 = f"{b10_domain}/{key_mp3}"
cdn_lrc = f"{b10_domain}/{key_lrc}"

# D1 batch-light
print("⚡ 3. 调用 D1 batch-light 点亮...")
payload = {
    "updates": [{
        "id": 27074,
        "file_path": cdn_mp3,
        "lrc_path": cdn_lrc,
        "duration": dur_int,
        "is_lit": 1
    }]
}
resp = requests.post(
    D1_LIGHT_URL,
    json=payload,
    headers={"Content-Type": "application/json"},
    proxies={'http': None, 'https': None},
    timeout=20
)
print(f"   D1 batch-light: {resp.text}")
assert resp.ok

# 同步本地
print("💾 4. 同步本地 catalog_sync.db...")
conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()
cur.execute("UPDATE songs SET file_path = ?, lrc_path = ?, duration = ? WHERE id = 27074", (cdn_mp3, cdn_lrc, dur_int))
conn.commit()
conn.close()
print("   ✅ 本地数据库同步成功！")

# CDN HEAD
parsed = urllib.parse.urlsplit(cdn_mp3)
chk_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, urllib.parse.quote(parsed.path), '', ''))
r_chk = requests.head(chk_url, headers={'User-Agent': 'Mozilla/5.0'}, proxies={'http': None, 'https': None}, timeout=10)
print(f"🌐 5. 公网 CDN 验证: HTTP [{r_chk.status_code}] (Content-Length: {r_chk.headers.get('Content-Length')})")
assert r_chk.status_code == 200

print("🎉 罗大佑 2017《家 (III)》官方正版母带重构与点亮圆满成功！")
