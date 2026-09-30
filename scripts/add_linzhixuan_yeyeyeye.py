#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《我是歌手》第一季 (2013) 增量补齐林志炫第十期齐秦致敬专场夺冠神作：
Track 20: 夜夜夜夜 - 林志炫
"""

import os
import sys
import json
import urllib.parse
import subprocess
import requests
import boto3
from botocore.config import Config

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
API_BASE = "https://m-api.changgepd.ccwu.cc"
HEADERS = {"User-Agent": "Mozilla/5.0"}

session = requests.Session()
session.trust_env = False  # 禁用环境变量代理，直连 Cloudflare Worker API

# 1. 读取 R2 配置 (写入 account_12)
with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfgs = json.load(f)["buckets"]

r2_cfg = r2_cfgs["account_12"]
s3_client = boto3.client(
    "s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4", connect_timeout=15, read_timeout=30)
)
BUCKET_NAME = r2_cfg["name"]
PUBLIC_BASE = r2_cfg["public_url"].rstrip("/")

ALBUM_ID = 1945
ARTIST_NAME = "我是歌手"
ALBUM_NAME = "第一季 (2013)"
ENC_ARTIST = urllib.parse.quote(ARTIST_NAME)
ENC_ALBUM = urllib.parse.quote(ALBUM_NAME)

print("=" * 80)
print("🚀 启动《我是歌手》第一季 林志炫《夜夜夜夜》增量接入流水线...")
print("=" * 80)

# Step 1: 调用 batch-insert 将林志炫歌曲插入到 Album 1945
insert_payload = {
    "artist_name": ARTIST_NAME,
    "album_title": ALBUM_NAME,
    "songs": [
        {
            "title": "夜夜夜夜 - 林志炫",
            "track_index": 20
        }
    ],
    "dry_run": False
}

print("📦 正在向 D1 提交 batch-insert 新曲目...")
ins_res = session.post(f"{API_BASE}/api/admin/ops/songs/batch-insert", json=insert_payload, timeout=25)
print(f"batch-insert 返回状态码: {ins_res.status_code}")
ins_data = ins_res.json()
print("batch-insert 响应:", ins_data)

new_song_id = None
if ins_data.get("success") and ins_data.get("data", {}).get("song_ids"):
    new_song_id = ins_data["data"]["song_ids"][0]
elif ins_data.get("data", {}).get("song_ids"):
    new_song_id = ins_data["data"]["song_ids"][0]
else:
    # 尝试从 album detail 获取 track 20
    det = session.get(f"{API_BASE}/api/admin/albums/detail?album_id={ALBUM_ID}", timeout=15).json()
    for s in det.get("data", {}).get("songs", []):
        if s["track_index"] == 20:
            new_song_id = s["id"]
            break

if not new_song_id:
    raise RuntimeError("无法获取新增曲目的 ID！")

print(f"✅ 成功确认林志炫新增曲目 ID: {new_song_id}")

# Step 2: 压制高保真标准音频
raw_mp3 = "/tmp/audit_user/s_27617_full.mp3"
clean_mp3 = f"/tmp/audit_user/s_{new_song_id}.mp3"
ffmpeg_cmd = [
    "ffmpeg", "-y", "-i", raw_mp3,
    "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
    "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
    clean_mp3
]
print(f"🎵 正在执行 EBU R128 (-14 LUFS) 响度标准化压制...")
subprocess.run(ffmpeg_cmd, check=True)

# Step 3: 获取并清洗 LRC 歌词
lrc_url = "https://music.163.com/api/song/lyric?os=pc&id=26045015&lv=-1&kv=-1&tv=-1"
lrc_res = requests.get(lrc_url, headers=HEADERS, timeout=10).json()
raw_lrc = lrc_res.get("lrc", {}).get("lyric", "")
clean_lines = [l for l in raw_lrc.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
cleaned_lrc = "\n".join(clean_lines).strip()
print(f"📝 成功获取高保真同步 LRC ({len(cleaned_lrc)} 字节)")

# Step 4: 上传至 R2 主力桶
mp3_key = f"music/{ARTIST_NAME}/{ALBUM_NAME}/s_{new_song_id}.mp3"
lrc_key = f"lyrics/{ARTIST_NAME}/{ALBUM_NAME}/s_{new_song_id}.lrc"

print(f"☁️ 上传音频至 R2: {mp3_key}")
s3_client.upload_file(clean_mp3, BUCKET_NAME, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})

print(f"☁️ 上传歌词至 R2: {lrc_key}")
s3_client.put_object(Bucket=BUCKET_NAME, Key=lrc_key, Body=cleaned_lrc.encode("utf-8"), ContentType="text/plain; charset=utf-8")

# Step 5: 提交 D1 batch-light 点亮
mp3_public_url = f"{PUBLIC_BASE}/music/{ENC_ARTIST}/{ENC_ALBUM}/s_{new_song_id}.mp3"
lrc_public_url = f"{PUBLIC_BASE}/lyrics/{ENC_ARTIST}/{ENC_ALBUM}/s_{new_song_id}.lrc"

light_payload = {
    "updates": [
        {
            "id": new_song_id,
            "file_path": mp3_public_url,
            "lrc_path": lrc_public_url
        }
    ]
}

print(f"⚡ 正在向 D1 提交 batch-light 点亮...")
light_res = session.post(f"{API_BASE}/api/admin/songs/batch-light", json=light_payload, timeout=25)
print(f"batch-light 响应: {light_res.status_code} | {light_res.text}")

# Step 6: 终验 HTTP HEAD
print("\n" + "=" * 80)
print("🔍 正在对生产环境进行 1:1 HTTP HEAD 连通性与字节审计...")
print("=" * 80)

r_mp3 = session.head(mp3_public_url, timeout=10)
r_lrc = session.head(lrc_public_url, timeout=10)

print(f"MP3: HTTP {r_mp3.status_code} | {r_mp3.headers.get('Content-Length')} 字节 | URL: {mp3_public_url}")
print(f"LRC: HTTP {r_lrc.status_code} | {r_lrc.headers.get('Content-Length')} 字节 | URL: {lrc_public_url}")

if r_mp3.status_code == 200 and r_lrc.status_code == 200:
    print("\n🎉 林志炫 - 《夜夜夜夜》增量接入 100% 成功！")
else:
    print("\n❌ 终验未完全通过，请检查网络或 R2 状态！")

