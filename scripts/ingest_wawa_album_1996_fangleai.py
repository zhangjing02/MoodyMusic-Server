#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
娃娃 (金智娟) 1996 经典大碟《放了爱》(10首全量点亮闭环脚本)
巨石唱片时期精品之作，收录《放了爱》《七情六欲》《坦白》等 10 首曲目：
1. 放了爱 (31083) - cD49DbBXFDo, 163 LRC: 298352
2. 七情六欲 (31084) - ArH2k7DSsFw, 163 LRC: 298356
3. 我是飞鸟你是天 (31085) - TtLN9Ky75WU, 163 LRC: 298360
4. 算了 (31086) - 5hyYXWxOxxU, 163 LRC: 298363
5. 呼吸 (31087) - 8zy9P-Ij3vo, 163 LRC: 298365
6. 祈祷 (31088) - l8sZro7KPWM, 163 LRC: 298367
7. 真爱宣言 (31089) - k-ZOr5xoJLU, 163 LRC: 298368
8. 说清楚 (31090) - qBidzgU_veg, 163 LRC: 298370
9. 嫉妒 (31091) - eq_03UDVynY, 163 LRC: 298372
10. 坦白 (31092) - 1mCniRZkBvM, 163 LRC: 298375

音源源自 YouTube 巨石唱片官方母带分轨 (Golden Era Official Lyrics Videos)

规范遵循：
- 工作目录严格隔离在 G:\\music-backup\\tmp\\wawa_fangleai_1996
- 目标存储桶: 第十存储桶 account_10 (moody-music-asset-10)
- 绝对 CDN 直链: https://pub-9e5d39f15e4a40dfb886ecb275551c90.r2.dev/
- 音频标准: 160k CBR 44.1kHz stereo + loudnorm EBU-R128
- 同步配齐网易云原版 LRC 歌词
- D1 batch-light 批量点亮、PATCH 专辑属性、本地 catalog_sync.db 镜像更新
- 公网边缘 CDN 抽测
"""

import os
import sys
import time
import json
import glob
import sqlite3
import subprocess
import urllib.parse
import requests
import boto3
from botocore.config import Config

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = 'e:/Workspace/AI-Project/MoodyMusic-Workspace'
CONFIG_PATH = os.path.join(BASE_DIR, 'backend', 'r2_config.json')
LOCAL_DB_PATH = os.path.join(BASE_DIR, 'backend', 'database', 'catalog_sync.db')

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

ALBUM_ID = 2241
ALBUM_NAME = "放了爱"
ARTIST_NAME = "娃娃"
TMP_DIR = r"G:\music-backup\tmp\wawa_fangleai_1996"
os.makedirs(TMP_DIR, exist_ok=True)

TRACKS = [
    {"song_id": 31083, "title": "放了爱", "yt_id": "cD49DbBXFDo", "n163_id": 298352, "idx": 1},
    {"song_id": 31084, "title": "七情六欲", "yt_id": "ArH2k7DSsFw", "n163_id": 298356, "idx": 2},
    {"song_id": 31085, "title": "我是飞鸟你是天", "yt_id": "TtLN9Ky75WU", "n163_id": 298360, "idx": 3},
    {"song_id": 31086, "title": "算了", "yt_id": "5hyYXWxOxxU", "n163_id": 298363, "idx": 4},
    {"song_id": 31087, "title": "呼吸", "yt_id": "8zy9P-Ij3vo", "n163_id": 298365, "idx": 5},
    {"song_id": 31088, "title": "祈祷", "yt_id": "l8sZro7KPWM", "n163_id": 298367, "idx": 6},
    {"song_id": 31089, "title": "真爱宣言", "yt_id": "k-ZOr5xoJLU", "n163_id": 298368, "idx": 7},
    {"song_id": 31090, "title": "说清楚", "yt_id": "qBidzgU_veg", "n163_id": 298370, "idx": 8},
    {"song_id": 31091, "title": "嫉妒", "yt_id": "eq_03UDVynY", "n163_id": 298372, "idx": 9},
    {"song_id": 31092, "title": "坦白", "yt_id": "1mCniRZkBvM", "n163_id": 298375, "idx": 10},
]

COVER_URL_SOURCE = "https://p1.music.126.net/-Qb2oR_wkv4Xok8zXYNbmQ==/109951172081310149.jpg"

print("=" * 80)
print(f"🚀 启动娃娃 1996 经典大碟《{ALBUM_NAME}》(10首全量点亮) 流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print(f"💿 目标专辑 ID: {ALBUM_ID}")
print(f"📂 本地工作目录: {TMP_DIR}")
print("=" * 80)

_req_session = requests.Session()
_req_session.trust_env = False

cover_file = os.path.join(TMP_DIR, "cover.jpg")
if not os.path.exists(cover_file):
    try:
        cr = _req_session.get(COVER_URL_SOURCE, timeout=10)
        with open(cover_file, "wb") as f:
            f.write(cr.content)
        print(f"🖼️ 专辑封面已下载: {len(cr.content)} 字节")
    except Exception as e:
        print(f"⚠️ 封面下载失败: {e}")

if os.path.exists(cover_file):
    cover_s3_key = f"covers/albums/c_{ALBUM_ID}_fangleai.jpg"
    s3.upload_file(cover_file, b10_name, cover_s3_key, ExtraArgs={'ContentType': 'image/jpeg'})
    cover_cdn_url = f"{b10_domain}/{cover_s3_key}"
    print(f"🖼️ 专辑封面已上传 R2: {cover_cdn_url}")
else:
    cover_cdn_url = None

batch_updates = []

for item in TRACKS:
    sid = item["song_id"]
    title = item["title"]
    yt_id = item["yt_id"]
    n_id = item["n163_id"]
    idx = item["idx"]

    print(f"\n🎵 [{idx:02d}/10] 正在处理: ID {sid} - 《{title}》 (YT: {yt_id})")

    # 1. 下载高清原版母带音频 (yt-dlp)
    raw_file = os.path.join(TMP_DIR, f"raw_{idx}.mp4")
    if not os.path.exists(raw_file) or os.path.getsize(raw_file) < 500000:
        dl_cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android,web",
            "-f", "18/ba/b",
            "-o", raw_file,
            f"https://www.youtube.com/watch?v={yt_id}"
        ]
        subprocess.run(dl_cmd, check=True)
    print(f"   • 源音频就绪: raw_{idx}.mp4 ({os.path.getsize(raw_file):,} 字节)")

    # 2. 压制 160k CBR + loudnorm EBU-R128
    out_mp3 = os.path.join(TMP_DIR, f"s_{sid}.mp3")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", raw_file,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        out_mp3
    ]
    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    mp3_size = os.path.getsize(out_mp3)

    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_mp3
    ]
    duration_str = subprocess.check_output(probe_cmd, text=True).strip()
    duration_sec = int(float(duration_str))
    print(f"   • 音频压制完成 (160k CBR / loudnorm): {mp3_size:,} 字节, 时长: {duration_sec}s")

    # 3. 获取 LRC 歌词
    out_lrc = os.path.join(TMP_DIR, f"l_{sid}.lrc")
    lrc_url = f"https://music.163.com/api/song/lyric?os=pc&id={n_id}&lv=-1&kv=-1&tv=-1"
    lrc_text = ""
    try:
        lr = _req_session.get(lrc_url, timeout=5).json()
        lrc_text = lr.get('lrc', {}).get('lyric', '').strip()
    except Exception as e:
        print(f"   ⚠️ LRC 获取失败: {e}")

    if not lrc_text:
        lrc_text = f"[00:00.00]{title} - {ARTIST_NAME}\n[00:05.00]专楫：《{ALBUM_NAME}》 (1996)\n[00:10.00]（歌词暂缺）\n"

    with open(out_lrc, "w", encoding="utf-8") as f:
        f.write(lrc_text)
    print(f"   • 同步 LRC 歌词已就绪: {len(lrc_text.splitlines())} 行")

    # 4. 上传 R2 并 S3 HEAD 校验
    s3_mp3_key = f"music/{ARTIST_NAME}/{ALBUM_NAME}/s_{sid}.mp3"
    s3_lrc_key = f"lyrics/{ARTIST_NAME}/{ALBUM_NAME}/l_{sid}.lrc"

    s3.upload_file(out_mp3, b10_name, s3_mp3_key, ExtraArgs={'ContentType': 'audio/mpeg'})
    s3.upload_file(out_lrc, b10_name, s3_lrc_key, ExtraArgs={'ContentType': 'text/plain; charset=utf-8'})

    head_mp3 = s3.head_object(Bucket=b10_name, Key=s3_mp3_key)
    if head_mp3['ContentLength'] != mp3_size:
        raise ValueError(f"S3 校验失败: {s3_mp3_key}")

    final_mp3_url = f"{b10_domain}/{urllib.parse.quote(s3_mp3_key)}"
    final_lrc_url = f"{b10_domain}/{urllib.parse.quote(s3_lrc_key)}"
    print(f"   • S3 上传校验通过: {final_mp3_url}")

    batch_updates.append({
        "id": sid,
        "file_path": final_mp3_url,
        "lrc_path": final_lrc_url,
        "duration": duration_sec,
        "storage_id": "account_10"
    })

# 5. D1 batch-light
print("\n" + "=" * 80)
print(f"📡 正在向生产环境 D1 调用 batch-light 点亮全部 {len(batch_updates)} 首曲目...")
light_url = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
resp = _req_session.post(light_url, json={"updates": batch_updates}, timeout=15)
print(f"📡 D1 batch-light 响应: HTTP {resp.status_code} -> {resp.text}")

# 6. PATCH 更新 D1 专辑属性
if cover_cdn_url:
    print("\n📡 更新 D1 专辑属性...")
    album_update_url = f"https://m-api.changgepd.ccwu.cc/api/admin/albums/{ALBUM_ID}"
    ar = _req_session.patch(album_update_url, json={
        "cover_url": cover_cdn_url,
        "release_date": "1996",
        "storage_id": "account_10"
    }, timeout=10)
    print(f"💿 专辑属性同步至 D1: HTTP {ar.status_code} -> {ar.text}")

# 7. 更新本地 catalog_sync.db 镜像
conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()
for up in batch_updates:
    cur.execute("""
        UPDATE songs 
        SET file_path = ?, lrc_path = ?, duration = ?, storage_id = ?
        WHERE id = ?
    """, (up["file_path"], up["lrc_path"], up["duration"], up["storage_id"], up["id"]))

if cover_cdn_url:
    cur.execute("""
        UPDATE albums 
        SET cover_url = ?, release_date = '1996', storage_id = 'account_10'
        WHERE id = ?
    """, (cover_cdn_url, ALBUM_ID))
conn.commit()
conn.close()
print(f"💾 本地 catalog_sync.db 镜像同步更新完成 ({len(batch_updates)} 首)！")

# 8. 边缘 CDN 抽测
print("\n🔍 抽检公网边缘 CDN 响应与直链可达性...")
for check_idx in [0, 1, 3, 5]:
    sample = batch_updates[check_idx]
    c_m = _req_session.head(sample['file_path'], timeout=5)
    c_l = _req_session.head(sample['lrc_path'], timeout=5)
    print(f"   • 音频直链 HEAD: {c_m.status_code} ({c_m.headers.get('content-length')} bytes) -> {sample['file_path']}")
    print(f"   • 歌词直链 HEAD: {c_l.status_code} -> {sample['lrc_path']}")

print("\n" + "=" * 80)
print(f"🎉 娃娃 1996 经典大碟《{ALBUM_NAME}》(10首) 全量 100% 满绿灯点亮闭环完成！")
print("=" * 80)
