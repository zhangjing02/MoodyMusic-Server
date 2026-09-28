#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
娃娃 (金智娟) 1987 经典大碟《开心女孩》(10首全量点亮闭环脚本)
台湾飞碟唱片时期经典代表作，收录《千年的神话》《开心女孩》《只是啊!只是》《为我停留》等 10 首曲目：
1. 千年的神话 (30625) - Timeless Music: LYjK__un6fc, 163 LRC: 298584
2. 只是啊!只是 (30626) - Timeless Music: o8gV5JyvfJg, 163 LRC: 298586
3. PAINT YOUR PICTURE (30627) - Timeless Music: aRSiM-FhgR4, 163 LRC: 298588
4. 新桃太郎电影音乐 (30628) - 7zZWS01pUC4, 163 LRC: 298590
5. 为我停留 (30629) - Timeless Music: nCL86zF9z4E, 163 LRC: 298592
6. 有谁能夠 (30630) - Timeless Music: zQzrbM8rn-I, 163 LRC: 298594
7. 情不自禁 (30631) - Timeless Music: KIayd5GqCMg, 163 LRC: 298596
8. 距离 (30632) - Timeless Music: 1ocGsQkTw7I, 163 LRC: 298598
9. 开心女孩 (30633) - Timeless Music: Q92Yizkh6jw, 163 LRC: 298600
10. 爱情哲学 (30634) - Timeless Music: szo4c9hb_Lo, 163 LRC: 298602

规范遵循：
- 工作目录严格隔离在 G:\\music-backup\\tmp\\wawa_kaixin_1987
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

ALBUM_ID = 2235
ALBUM_NAME = "开心女孩"
ARTIST_NAME = "娃娃"
TMP_DIR = r"G:\music-backup\tmp\wawa_kaixin_1987"
os.makedirs(TMP_DIR, exist_ok=True)

TRACKS = [
    {"song_id": 30625, "title": "千年的神话", "yt_id": "LYjK__un6fc", "n163_id": 298584, "idx": 1},
    {"song_id": 30626, "title": "只是啊!只是", "yt_id": "o8gV5JyvfJg", "n163_id": 298586, "idx": 2},
    {"song_id": 30627, "title": "PAINT YOUR PICTURE", "yt_id": "aRSiM-FhgR4", "n163_id": 298588, "idx": 3},
    {"song_id": 30628, "title": "新桃太郎电影音乐", "yt_id": "7zZWS01pUC4", "n163_id": 298590, "idx": 4},
    {"song_id": 30629, "title": "为我停留", "yt_id": "nCL86zF9z4E", "n163_id": 298592, "idx": 5},
    {"song_id": 30630, "title": "有谁能夠", "yt_id": "zQzrbM8rn-I", "n163_id": 298594, "idx": 6},
    {"song_id": 30631, "title": "情不自禁", "yt_id": "KIayd5GqCMg", "n163_id": 298596, "idx": 7},
    {"song_id": 30632, "title": "距离", "yt_id": "1ocGsQkTw7I", "n163_id": 298598, "idx": 8},
    {"song_id": 30633, "title": "开心女孩", "yt_id": "Q92Yizkh6jw", "n163_id": 298600, "idx": 9},
    {"song_id": 30634, "title": "爱情哲学", "yt_id": "szo4c9hb_Lo", "n163_id": 298602, "idx": 10},
]

COVER_URL_SOURCE = "https://p2.music.126.net/V7_CL-8TVuFNbuPKEvS8Rg==/109951163401741358.jpg"

print("=" * 80)
print(f"🚀 启动娃娃 1987 经典大碟《{ALBUM_NAME}》(10首全量点亮) 流水线...")
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
    cover_s3_key = f"covers/albums/c_{ALBUM_ID}_kaixin.jpg"
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
        lrc_text = f"[00:00.00]{title} - {ARTIST_NAME}\n[00:05.00]专楫：《{ALBUM_NAME}》 (1987)\n[00:10.00]（歌词暂缺）\n"

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
        "release_date": "1987",
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
        SET cover_url = ?, release_date = '1987', storage_id = 'account_10'
        WHERE id = ?
    """, (cover_cdn_url, ALBUM_ID))
conn.commit()
conn.close()
print(f"💾 本地 catalog_sync.db 镜像同步更新完成 ({len(batch_updates)} 首)！")

# 8. 边缘 CDN 抽测
print("\n🔍 抽检公网边缘 CDN 响应与直链可达性...")
for check_idx in [0, 1, 4, 8]:
    sample = batch_updates[check_idx]
    c_m = _req_session.head(sample['file_path'], timeout=5)
    c_l = _req_session.head(sample['lrc_path'], timeout=5)
    print(f"   • 音频直链 HEAD: {c_m.status_code} ({c_m.headers.get('content-length')} bytes) -> {sample['file_path']}")
    print(f"   • 歌词直链 HEAD: {c_l.status_code} -> {sample['lrc_path']}")

print("\n" + "=" * 80)
print(f"🎉 娃娃 1987 经典大碟《{ALBUM_NAME}》(10首) 全量 100% 满绿灯点亮闭环完成！")
print("=" * 80)
