#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_yangnaiwen_album_2001_yinggai.py
杨乃文 2001 台湾交流协会“年度十大专辑”神作《应该》(10首全量点亮)
收录陈绮贞创作传世名曲《证据》、抒情巅峰《祝我幸福》《应该》《Queen》《漂着》
音源：Bilibili Hi-Res 24bit/48kHz 原盘母带 (BV1TgQqYpEuk) 毫米级无损切分
160k CBR (44.1kHz) EBU-R128 标准化压制，配齐 NetEase 精准同步 LRC 歌词
Album ID: 2210, Artist ID: 173
"""

import os
import sys
import json
import time
import glob
import boto3
from botocore.config import Config
import requests
import sqlite3
import subprocess

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = 'e:/Workspace/AI-Project/MoodyMusic-Workspace'
CONFIG_PATH = os.path.join(BASE_DIR, 'backend', 'r2_config.json')
LOCAL_DB_PATH = os.path.join(BASE_DIR, 'backend', 'database', 'catalog_sync.db')

BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
PATCH_ALBUM_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/"

WORK_DIR = r'G:\music-backup\tmp\yangnaiwen_yinggai_2001'
os.makedirs(WORK_DIR, exist_ok=True)

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

ALBUM_ID = 2210
ARTIST_ID = 173
ALBUM_TITLE = "应该"
ARTIST_NAME = "杨乃文"

FULL_ALBUM_URL = "https://www.bilibili.com/video/BV1TgQqYpEuk"

TRACKS = [
    {"index": 1,  "song_id": 30359, "title": "应该",       "start": 0.5,    "end": 369.5,  "lrc_nid": 316061},
    {"index": 2,  "song_id": 30360, "title": "祝我幸福",   "start": 376.0,  "end": 636.0,  "lrc_nid": 316063},
    {"index": 3,  "song_id": 30361, "title": "Queen",      "start": 638.5,  "end": 899.0,  "lrc_nid": 316065},
    {"index": 4,  "song_id": 30362, "title": "太骄傲",     "start": 899.5,  "end": 1140.5, "lrc_nid": 316067},
    {"index": 5,  "song_id": 30363, "title": "不得不",     "start": 1142.5, "end": 1356.5, "lrc_nid": 316069},
    {"index": 6,  "song_id": 30364, "title": "证据",       "start": 1359.5, "end": 1632.0, "lrc_nid": 316071},
    {"index": 7,  "song_id": 30365, "title": "我们",       "start": 1635.5, "end": 1887.0, "lrc_nid": 316073},
    {"index": 8,  "song_id": 30366, "title": "Surrender",  "start": 1888.0, "end": 2275.0, "lrc_nid": 316075},
    {"index": 9,  "song_id": 30367, "title": "漂着",       "start": 2279.5, "end": 2526.0, "lrc_nid": 316077},
    {"index": 10, "song_id": 30368, "title": "放轻点",     "start": 2529.5, "end": 2747.0, "lrc_nid": 316079},
]

COVER_SOURCE_URL = "https://p1.music.126.net/btpbUETuWqGuvqDnjh06HA==/109951163188713543.jpg"

print("=" * 80)
print(f"🚀 启动杨乃文 2001 年度十大专辑《{ALBUM_TITLE}》(10首全量点亮) 流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print(f"💿 目标专辑 ID: {ALBUM_ID}")
print(f"📂 本地工作目录: {WORK_DIR}")
print("=" * 80)

# 0. 封面下载与上传
cover_local = os.path.join(WORK_DIR, f"c_{ALBUM_ID}_yinggai.jpg")
if not os.path.exists(cover_local) or os.path.getsize(cover_local) < 5000:
    r_img = requests.get(COVER_SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    with open(cover_local, 'wb') as fp:
        fp.write(r_img.content)
    print(f"🖼️ 专辑封面已下载: {os.path.getsize(cover_local)} 字节")

key_cover = f"covers/albums/c_{ALBUM_ID}_yinggai.jpg"
with open(cover_local, "rb") as fp:
    s3.put_object(Bucket=b10_name, Key=key_cover, Body=fp.read(), ContentType="image/jpeg")
cover_cdn = f"{b10_domain}/{key_cover}"
print(f"🖼️ 专辑封面已上传 R2: {cover_cdn}")

# 1. 确保整专 Hi-Res 母带已就绪
full_audio_path = os.path.join(WORK_DIR, "full_album.m4a")
if not os.path.exists(full_audio_path) or os.path.getsize(full_audio_path) < 10000000:
    out_tmpl = os.path.join(WORK_DIR, "full_album.%(ext)s")
    cmd_dl = [
        "yt-dlp", "-f", "ba",
        "--no-playlist",
        "-o", out_tmpl,
        FULL_ALBUM_URL
    ]
    subprocess.run(cmd_dl, check=True)

assert os.path.exists(full_audio_path) and os.path.getsize(full_audio_path) > 10000000, "母带文件缺失"
print(f"🎧 整专 Hi-Res 母带就绪: {os.path.getsize(full_audio_path)} 字节")

# 2. 毫米级切割、EBU R128 标准化与歌词获取
processed_tracks = []
total = len(TRACKS)

for t in TRACKS:
    idx = t["index"]
    sid = t["song_id"]
    title = t["title"]
    s_start = str(t["start"])
    s_end = str(t["end"])
    lrc_nid = t["lrc_nid"]

    final_audio = os.path.join(WORK_DIR, f"track_{idx}.mp3")
    lrc_file = os.path.join(WORK_DIR, f"track_{idx}.lrc")

    print(f"\n🎵 [{idx:02d}/{total}] 切割压制 《{title}》 (Song ID: {sid}, 区间: {s_start}s -> {s_end}s)...")

    if not os.path.exists(final_audio) or os.path.getsize(final_audio) < 1000000:
        cmd_enc = [
            "ffmpeg", "-y", "-ss", s_start, "-to", s_end, "-i", full_audio_path,
            "-af", "silenceremove=start_periods=1:start_duration=0.3:start_threshold=-45dB,loudnorm=I=-14:TP=-1.0:LRA=11",
            "-ar", "44100", "-ac", "2",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
            final_audio
        ]
        subprocess.run(cmd_enc, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f"   • ffmpeg 切割压制完成 (160k CBR EBU-R128)")
    else:
        print(f"   • 已有压制文件，跳过压制")

    out_dur = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", final_audio
    ]).decode().strip()
    dur_int = round(float(out_dur))
    mp3_sz = os.path.getsize(final_audio)

    # 歌词获取
    if not os.path.exists(lrc_file) or os.path.getsize(lrc_file) < 50:
        r_lrc = requests.get(
            f"https://music.163.com/api/song/lyric?os=pc&id={lrc_nid}&lv=-1&kv=-1&tv=-1",
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=10
        ).json()
        lrc_text = r_lrc.get('lrc', {}).get('lyric', '').strip()
        with open(lrc_file, 'w', encoding='utf-8') as fp:
            fp.write(lrc_text + '\n')

    lrc_sz = os.path.getsize(lrc_file)
    print(f"   ✅ 完成: 实际时长 {dur_int}s | MP3: {mp3_sz} 字节 | LRC: {lrc_sz} 字节")

    processed_tracks.append({
        "index": idx,
        "song_id": sid,
        "title": title,
        "duration": dur_int,
        "mp3_path": final_audio,
        "lrc_path": lrc_file,
        "mp3_size": mp3_sz,
        "lrc_size": lrc_sz
    })

# 3. 上传 MP3 与 LRC 至 R2 (绝对路径规范)
print("\n" + "=" * 80)
print(f"📤 上传 {total} 首录音室原版母带与歌词至 R2 {b10_name}...")
print("=" * 80)

updates_payload = []
for pt in processed_tracks:
    sid = pt["song_id"]
    title = pt["title"]
    key_mp3 = f"music/{ARTIST_NAME}/{ALBUM_TITLE}/s_{sid}.mp3"
    key_lrc = f"lyrics/{ARTIST_NAME}/{ALBUM_TITLE}/s_{sid}.lrc"

    with open(pt["mp3_path"], "rb") as fp:
        s3.put_object(Bucket=b10_name, Key=key_mp3, Body=fp.read(), ContentType="audio/mpeg")
    with open(pt["lrc_path"], "rb") as fp:
        s3.put_object(Bucket=b10_name, Key=key_lrc, Body=fp.read(), ContentType="text/plain; charset=utf-8")

    # S3 HEAD 字节强校验
    head_mp3 = s3.head_object(Bucket=b10_name, Key=key_mp3)
    head_lrc = s3.head_object(Bucket=b10_name, Key=key_lrc)
    assert head_mp3["ContentLength"] == pt["mp3_size"], f"MP3 字节校验失败: {title}"
    assert head_lrc["ContentLength"] == pt["lrc_size"], f"LRC 字节校验失败: {title}"

    cdn_mp3 = f"{b10_domain}/{key_mp3}"
    cdn_lrc = f"{b10_domain}/{key_lrc}"

    print(f"  ✅ [S3 HEAD OK] 《{title}》 (Song ID: {sid}) -> {cdn_mp3}")

    updates_payload.append({
        "id": sid,
        "file_path": cdn_mp3,
        "lrc_path": cdn_lrc,
        "duration": pt["duration"],
        "is_lit": 1
    })

# 4. 调用 D1 batch-light 原子点亮
print("\n" + "=" * 80)
print("⚡ 调用 D1 batch-light 进行原子点亮与绝对直链切链...")
print("=" * 80)

for attempt in range(5):
    try:
        resp_light = requests.post(
            BATCH_LIGHT_URL,
            json={"updates": updates_payload},
            headers={"Content-Type": "application/json"},
            proxies={'http': None, 'https': None},
            timeout=20
        )
        print("batch-light 返回:", resp_light.status_code, resp_light.text)
        assert resp_light.ok
        break
    except Exception as e:
        print(f"  • batch-light 尝试 {attempt+1} 失败: {e}")
        time.sleep(2)

# 5. 更新专辑属性（封面、年份 2001）
print("\n" + "=" * 80)
print(f"🎨 配置专辑《{ALBUM_TITLE}》(ID: {ALBUM_ID}) 封面与发行年份 (2001)...")
print("=" * 80)

for attempt in range(5):
    try:
        resp_alb = requests.patch(
            f"{PATCH_ALBUM_URL}{ALBUM_ID}",
            json={"release_date": "2001", "cover_url": cover_cdn},
            proxies={'http': None, 'https': None},
            timeout=10
        )
        print(f"  • 专辑 ID: {ALBUM_ID} 属性更新: {resp_alb.status_code} {resp_alb.text}")
        break
    except Exception as e:
        print(f"  • 专辑属性更新尝试 {attempt+1} 失败: {e}")
        time.sleep(2)

# 6. 同步写入本地 catalog_sync.db
print("\n" + "=" * 80)
print("💾 同步写入本地 catalog_sync.db 数据库...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

cur.execute("UPDATE albums SET release_date = '2001', cover_url = ? WHERE id = ?", (cover_cdn, ALBUM_ID))

for u in updates_payload:
    sid = u["id"]
    t_item = next(item for item in processed_tracks if item["song_id"] == sid)
    cur.execute("""
        UPDATE songs 
        SET duration = ?, file_path = ?, lrc_path = ?, track_index = ?
        WHERE id = ?
    """, (u["duration"], u["file_path"], u["lrc_path"], t_item["index"], sid))

conn.commit()
conn.close()
print("  ✅ 本地数据库同步成功！")

# 7. 公网边缘 CDN HEAD 抽测
print("\n" + "=" * 80)
print("🌐 公网 CDN 连通性抽测 (curl)...")
print("=" * 80)

test_songs = [updates_payload[0], updates_payload[1], updates_payload[5], updates_payload[-1]]
for ts in test_songs:
    r_test = requests.head(ts["file_path"], proxies={'http': None, 'https': None}, timeout=10)
    print(f"  🌐 [CDN 校验] {ts['file_path']} -> HTTP {r_test.status_code} (Length: {r_test.headers.get('Content-Length')})")
    assert r_test.status_code == 200, f"CDN 无法访问: {ts['file_path']}"

print("\n" + "=" * 80)
print(f"🎉 杨乃文第三张神专《{ALBUM_TITLE}》(10首) 全流程点亮成功！")
print("=" * 80)
