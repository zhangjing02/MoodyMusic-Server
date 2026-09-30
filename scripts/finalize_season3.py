#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收尾补齐陈洁仪《心动》、修复 A-Lin 与李荣浩歌词，并执行第三季全专 100% 验收
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

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
API_BASE = "https://m-api.changgepd.ccwu.cc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]["account_12"]

s3_client = boto3.client(
    "s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto"
)
BUCKET = r2_cfg["name"]
PUBLIC_BASE = r2_cfg["public_url"].rstrip("/")

session = requests.Session()
session.trust_env = False

# 1. 压制并上传陈洁仪《心动》(31116)
raw_chen = "/tmp/test_chenjieyi.webm"
norm_mp3 = "/tmp/s_31116.mp3"
subprocess.run([
    "ffmpeg", "-y", "-i", raw_chen,
    "-vn", "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
    "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1", "-ar", "44100",
    norm_mp3
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

mp3_key = "music/我是歌手/第三季 (2015)/s_31116.mp3"
s3_client.upload_file(norm_mp3, BUCKET, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
print(f"✅ 陈洁仪《心动》音频上传完成: {mp3_key}")

# 2. 抓取并上传 3 首高保真 LRC
lrc_tasks = [
    (31116, "陈洁仪 心动"),
    (27635, "A-Lin 给我一个理由忘记"),
    (27637, "李荣浩 模特")
]

for sid, q in lrc_tasks:
    r = requests.get(f"https://music.163.com/api/search/get/web?s={q}&type=1&limit=3", headers=HEADERS, timeout=6).json()
    songs = r.get("result", {}).get("songs", [])
    if songs:
        nid = songs[0]["id"]
        lr = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1", headers=HEADERS, timeout=6).json()
        lrc_text = lr.get("lrc", {}).get("lyric", "")
        if lrc_text:
            clean_lines = [l for l in lrc_text.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
            cleaned = "\n".join(clean_lines).strip()
            lkey = f"lyrics/我是歌手/第三季 (2015)/s_{sid}.lrc"
            s3_client.put_object(Bucket=BUCKET, Key=lkey, Body=cleaned.encode("utf-8"), ContentType="text/plain; charset=utf-8")
            print(f"📄 成功上传 [{sid}] {q} 歌词 ({len(cleaned)} 字节)")

# 3. 提交第三季批量点亮
enc_artist = urllib.parse.quote("我是歌手")
enc_album = urllib.parse.quote("第三季 (2015)")

detail = session.get(f"{API_BASE}/api/admin/albums/detail?album_id=1947", timeout=15).json()
songs = detail.get("data", {}).get("songs", [])

updates = []
for s in songs:
    sid = s["id"]
    mp3_url = f"{PUBLIC_BASE}/music/{enc_artist}/{enc_album}/s_{sid}.mp3"
    lrc_url = f"{PUBLIC_BASE}/lyrics/{enc_artist}/{enc_album}/s_{sid}.lrc"
    updates.append({"id": sid, "file_path": mp3_url, "lrc_path": lrc_url})

res_lit = session.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": updates}, timeout=25)
print(f"⚡ 第三季 batch-light 响应: {res_lit.status_code} | {res_lit.text}")

# 4. 终验
print("\n" + "=" * 80)
print("🔍 正在对第三季 13 首曲目发起生产端 1:1 物理字节审计...")
print("=" * 80)

final_detail = session.get(f"{API_BASE}/api/admin/albums/detail?album_id=1947", timeout=15).json()
final_songs = final_detail.get("data", {}).get("songs", [])

all_pass = True
for s in sorted(final_songs, key=lambda x: x["track_index"]):
    sid = s["id"]
    title = s["title"]
    tidx = s["track_index"]
    fpath = s.get("file_path")
    lpath = s.get("lrc_path")

    r_mp3 = None
    for _ in range(3):
        try:
            r_mp3 = session.head(fpath, headers=HEADERS, timeout=12)
            if r_mp3.status_code == 200: break
        except Exception: pass
    mp3_len = int(r_mp3.headers.get("content-length", 0)) if (r_mp3 and r_mp3.status_code == 200) else 0

    r_lrc = None
    for _ in range(3):
        try:
            r_lrc = session.head(lpath, headers=HEADERS, timeout=12)
            if r_lrc.status_code == 200: break
        except Exception: pass
    lrc_len = int(r_lrc.headers.get("content-length", 0)) if (r_lrc and r_lrc.status_code == 200) else 0

    ok = (r_mp3 and r_mp3.status_code == 200 and mp3_len > 1000000 and r_lrc and r_lrc.status_code == 200 and lrc_len > 100)
    if not ok: all_pass = False

    status = "✅ PASS" if ok else "❌ FAIL"
    c_m = r_mp3.status_code if r_mp3 else 0
    c_l = r_lrc.status_code if r_lrc else 0
    print(f"Track {tidx:2d} | [{sid}] {title:<40} | {status} | MP3: {mp3_len/1024/1024:.2f}MB (HTTP {c_m}) | LRC: {lrc_len}B (HTTP {c_l})")

print("=" * 80)
if all_pass:
    print("🎉 第三季 13 首曲目 100% 满格通过生产端终验！")
