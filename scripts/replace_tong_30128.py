#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
replace_tong_30128.py
采录童安格官方频道 1989《其实你不懂我的心》录音室男声母带 (YT: _gmbdy57_8U)
压制为标准 160k CBR Xing MP3 并覆盖上传至 R2 account_10 (s_30128.mp3)
"""

import os
import sys
import json
import boto3
from botocore.config import Config
import subprocess
import urllib.request
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8')

PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY") or ""
YT_ID = "_gmbdy57_8U"  # Angus Tung - Topic 官方录音室母带 (195s)
WORK_DIR = r"G:\music-backup\tmp\tong_1989"
os.makedirs(WORK_DIR, exist_ok=True)

RAW_AUDIO = os.path.join(WORK_DIR, "raw_30128.mp3")
FINAL_AUDIO = os.path.join(WORK_DIR, "track_30128_fixed.mp3")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'r2_config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    cfg = json.load(f)['buckets']['account_10']

b10_name = cfg['name']
b10_domain = cfg['public_domain'].rstrip('/')

s3 = boto3.client(
    's3',
    endpoint_url=cfg['endpoint_url'],
    aws_access_key_id=cfg['access_key_id'],
    aws_secret_access_key=cfg['secret_access_key'],
    config=Config(signature_version='s3v4')
)

print("=" * 80)
print(f"🎵 1. 从 YouTube 官方母带 (_gmbdy57_8U) 采录音频...")
print(f"代理地址: {PROXY}")
print("=" * 80)

if os.path.exists(RAW_AUDIO):
    os.remove(RAW_AUDIO)

cmd_dl = ['yt-dlp']
if PROXY:
    cmd_dl.extend(['--proxy', PROXY])
cmd_dl.extend([
    '-x', '--audio-format', 'mp3',
    '-o', RAW_AUDIO,
    f"https://www.youtube.com/watch?v={YT_ID}"
])
subprocess.run(cmd_dl, check=True)
print(f"✅ 下载完成: {RAW_AUDIO}, 大小: {os.path.getsize(RAW_AUDIO)} 字节")

print("\n" + "=" * 80)
print("🎛️ 2. 标准工程母带压制 (EBU R128 + 160k CBR Xing MP3)...")
print("=" * 80)

if os.path.exists(FINAL_AUDIO):
    os.remove(FINAL_AUDIO)

cmd_enc = [
    'ffmpeg', '-y', '-i', RAW_AUDIO,
    '-af', 'afade=t=in:ss=0:d=0.08,loudnorm=I=-14:TP=-1.0:LRA=11',
    '-c:a', 'libmp3lame', '-b:a', '160k', '-ar', '44100',
    FINAL_AUDIO
]
subprocess.run(cmd_enc, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

out_dur = subprocess.check_output([
    "ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", FINAL_AUDIO
]).decode().strip()
dur_int = round(float(out_dur))
mp3_sz = os.path.getsize(FINAL_AUDIO)
print(f"✅ 压制完成: 时长 {dur_int}s | 体积: {mp3_sz} 字节")

print("\n" + "=" * 80)
print(f"📤 3. 上传覆盖 R2 {b10_name} -> music/童安格/其实你不懂我的心/s_30128.mp3 ...")
print("=" * 80)

key_mp3 = "music/童安格/其实你不懂我的心/s_30128.mp3"
with open(FINAL_AUDIO, "rb") as fp:
    s3.put_object(Bucket=b10_name, Key=key_mp3, Body=fp.read(), ContentType="audio/mpeg")

head_mp3 = s3.head_object(Bucket=b10_name, Key=key_mp3)
assert head_mp3["ContentLength"] == mp3_sz, "ContentLength mismatch!"
cdn_mp3 = f"{b10_domain}/{key_mp3}"
print(f"✅ [S3 HEAD OK] 新音频直链已就绪: {cdn_mp3} (大小: {head_mp3['ContentLength']} 字节)")

print("\n" + "=" * 80)
print("🌐 4. 公网 CDN 验证...")
print("=" * 80)
p = urllib.parse.urlsplit(cdn_mp3)
u_enc = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), '', ''))
req = urllib.request.Request(u_enc, headers={'User-Agent': 'Mozilla/5.0'})
r_chk = urllib.request.urlopen(req, timeout=10)
print(f"  • CDN 状态: {r_chk.status}, Content-Length: {r_chk.headers.get('Content-Length')}")
print("\n🎉 童安格《其实你不懂我的心》男声官方母带替换全部成功完成！")
