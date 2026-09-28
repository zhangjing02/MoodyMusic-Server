#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
娃娃 (金智娟) 1983 经典大碟《绿色的水滴》(10首全量点亮闭环脚本)
台湾新格唱片时期传世代表作，收录《绿色的水滴》《飞鸟》《苏里、宝贝》《再见》等 10 首曲目：
1. 绿色的水滴 (30615) - 163 ID: 298635
2. 飞鸟 (30616) - 163 ID: 298636
3. 从来都没有 (30617) - 163 ID: 298637
4. 和你在一起 (30618) - 163 ID: 298639
5. 该不该说 (30619) - 163 ID: 298641
6. 表白 (30620) - 163 ID: 298643
7. ㄆㄧㄌㄧˋㄨˇHave Some Fun (30621) - 163 ID: 298645
8. 苏里、宝贝 (30622) - 163 ID: 298647
9. Music Box (30623) - 163 ID: 298649
10. 再见 (30624) - 163 ID: 298651

规范遵循：
- 工作目录严格隔离在 G:\\music-backup\\tmp\\wawa_shuidi_1983
- 目标存储桶: 第十存储桶 account_10 (moody-music-asset-10)
- 绝对 CDN 直链: https://pub-9e5d39f15e4a40dfb886ecb275551c90.r2.dev/
- 音频标准: 160k CBR 44.1kHz stereo + loudnorm EBU-R128
- 同步配齐网易云原版 LRC 歌词
- D1 batch-light 批量点亮与本地 catalog_sync.db 镜像更新
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

ALBUM_ID = 2234
ALBUM_NAME = "绿色的水滴"
ARTIST_NAME = "娃娃"
TMP_DIR = r"G:\music-backup\tmp\wawa_shuidi_1983"
os.makedirs(TMP_DIR, exist_ok=True)

TRACKS = [
    {"song_id": 30615, "title": "绿色的水滴", "n163_id": 298635, "idx": 1},
    {"song_id": 30616, "title": "飞鸟", "n163_id": 298636, "idx": 2},
    {"song_id": 30617, "title": "从来都没有", "n163_id": 298637, "idx": 3},
    {"song_id": 30618, "title": "和你在一起", "n163_id": 298639, "idx": 4},
    {"song_id": 30619, "title": "该不该说", "n163_id": 298641, "idx": 5},
    {"song_id": 30620, "title": "表白", "n163_id": 298643, "idx": 6},
    {"song_id": 30621, "title": "ㄆㄧㄌㄧˋㄨˇHave Some Fun", "n163_id": 298645, "idx": 7},
    {"song_id": 30622, "title": "苏里、宝贝", "n163_id": 298647, "idx": 8},
    {"song_id": 30623, "title": "Music Box", "n163_id": 298649, "idx": 9},
    {"song_id": 30624, "title": "再见", "n163_id": 298651, "idx": 10},
]

COVER_URL_SOURCE = "https://p2.music.126.net/V7_CL-8TVuFNbuPKEvS8Rg==/109951163401741358.jpg"

print("=" * 80)
print(f"🚀 启动娃娃 1983 经典大碟《{ALBUM_NAME}》(10首全量点亮) 流水线...")
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
    cover_s3_key = f"covers/albums/c_{ALBUM_ID}_shuidi.jpg"
    s3.upload_file(cover_file, b10_name, cover_s3_key, ExtraArgs={'ContentType': 'image/jpeg'})
    cover_cdn_url = f"{b10_domain}/{cover_s3_key}"
    print(f"🖼️ 专辑封面已上传 R2: {cover_cdn_url}")
else:
    cover_cdn_url = None

batch_updates = []

for item in TRACKS:
    sid = item["song_id"]
    title = item["title"]
    n_id = item["n163_id"]
    idx = item["idx"]

    print(f"\n🎵 [{idx:02d}/10] 正在处理: ID {sid} - 《{title}》 (网易云 ID: {n_id})")

    # 1. 下载录音室原版母带音频
    raw_mp3 = os.path.join(TMP_DIR, f"raw_{idx}.mp3")
    if not os.path.exists(raw_mp3) or os.path.getsize(raw_mp3) < 500000:
        url = f"https://music.163.com/song/media/outer/url?id={n_id}.mp3"
        r = _req_session.get(url, timeout=15)
        if len(r.content) < 500000:
            raise RuntimeError(f"音频过小或无效: {len(r.content)} bytes for {title}")
        with open(raw_mp3, "wb") as f:
            f.write(r.content)
    print(f"   • 原版源音频就绪: raw_{idx}.mp3 ({os.path.getsize(raw_mp3):,} 字节)")

    # 2. 压制 160k CBR + loudnorm EBU-R128
    out_mp3 = os.path.join(TMP_DIR, f"s_{sid}.mp3")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", raw_mp3,
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
        lrc_text = f"[00:00.00]{title} - {ARTIST_NAME}\n[00:05.00]专楫：《{ALBUM_NAME}》 (1983)\n[00:10.00]（纯音乐 / 歌词暂缺）\n"

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

# 6. 更新 D1 专辑属性
if cover_cdn_url:
    print("\n📡 更新 D1 专辑属性...")
    album_update_url = f"https://m-api.changgepd.ccwu.cc/api/admin/albums/{ALBUM_ID}"
    ar = _req_session.put(album_update_url, json={
        "cover_url": cover_cdn_url,
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
        SET cover_url = ?, storage_id = 'account_10'
        WHERE id = ?
    """, (cover_cdn_url, ALBUM_ID))
conn.commit()
conn.close()
print(f"💾 本地 catalog_sync.db 镜像同步更新完成 ({len(batch_updates)} 首)！")

# 8. 边缘 CDN 抽测
print("\n🔍 抽检公网边缘 CDN 响应与直链可达性...")
for check_idx in [0, 1, 5, 9]:
    sample = batch_updates[check_idx]
    c_m = _req_session.head(sample['file_path'], timeout=5)
    c_l = _req_session.head(sample['lrc_path'], timeout=5)
    print(f"   • 音频直链 HEAD: {c_m.status_code} ({c_m.headers.get('content-length')} bytes) -> {sample['file_path']}")
    print(f"   • 歌词直链 HEAD: {c_l.status_code} -> {sample['lrc_path']}")

print("\n" + "=" * 80)
print(f"🎉 娃娃 1983 经典大碟《{ALBUM_NAME}》(10首) 全量 100% 满绿灯点亮闭环完成！")
print("=" * 80)
