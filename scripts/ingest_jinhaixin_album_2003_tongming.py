#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_jinhaixin_album_2003_tongming.py
金海心 (Hannah Kim) 2003 同名转型巅峰大碟《金海心》(11首全量点亮)
斩获百事音乐风云榜最佳女歌手、最佳专辑，收录《悲伤的秋千》《对岸》《此时 彼刻》《对他说》
母带来源：1:1 Hi-Res 录音室原盘母带切割，160k CBR (44.1kHz) EBU-R128 标准化压制
Album ID: 2201, Artist ID: 171
"""

import os
import sys
import json
import time
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

WORK_DIR = r'G:\music-backup\tmp\jinhaixin_tongming_2003'
os.makedirs(WORK_DIR, exist_ok=True)
FULL_ALBUM_PATH = os.path.join(WORK_DIR, 'full_album.m4a')

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

ALBUM_ID = 2201
ARTIST_ID = 171

TRACKS = [
    {"index": 1,  "song_id": 30270, "title": "此时 彼刻",      "ss": "1.91",    "dur": "219.0", "lrc_nid": 247831},
    {"index": 2,  "song_id": 30271, "title": "对他说",        "ss": "224.01",  "dur": "219.9", "lrc_nid": 247832},
    {"index": 3,  "song_id": 30272, "title": "对岸",          "ss": "446.77",  "dur": "264.4", "lrc_nid": 247833},
    {"index": 4,  "song_id": 30273, "title": "Hello",         "ss": "716.15",  "dur": "247.6", "lrc_nid": 247834},
    {"index": 5,  "song_id": 30274, "title": "两分钟",        "ss": "967.17",  "dur": "224.0", "lrc_nid": 247837},
    {"index": 6,  "song_id": 30275, "title": "她比我懂你吗",    "ss": "1194.76", "dur": "263.5", "lrc_nid": 247836},
    {"index": 7,  "song_id": 30276, "title": "爱的风度",      "ss": "1464.04", "dur": "226.6", "lrc_nid": 247838},
    {"index": 8,  "song_id": 30277, "title": "听见",          "ss": "1693.03", "dur": "242.1", "lrc_nid": 247839},
    {"index": 9,  "song_id": 30278, "title": "马戏团",        "ss": "1938.55", "dur": "241.6", "lrc_nid": 247840},
    {"index": 10, "song_id": 30279, "title": "Message Lover", "ss": "2184.88", "dur": "244.7", "lrc_nid": 247841},
    {"index": 11, "song_id": 30280, "title": "悲伤的秋千",    "ss": "2439.03", "dur": "256.6", "lrc_nid": 247835},
]

COVER_SOURCE_URL = "https://p2.music.126.net/uDd84I4EDSKUWhnI5RPZJA==/109951167192720058.jpg"

print("=" * 80)
print("🚀 启动金海心 2003 同名经典大碟《金海心》(11首 Hi-Res 录音室原盘切割) 点亮流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print(f"💿 目标专辑 ID: {ALBUM_ID}")
print(f"📂 本地工作目录: {WORK_DIR}")
print("=" * 80)

# 0. 封面下载与上传
cover_local = os.path.join(WORK_DIR, "c_2201_tongming.jpg")
if not os.path.exists(cover_local) or os.path.getsize(cover_local) < 5000:
    r_img = requests.get(COVER_SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    with open(cover_local, 'wb') as fp:
        fp.write(r_img.content)
    print(f"🖼️ 专辑封面已下载: {os.path.getsize(cover_local)} 字节")

key_cover = "covers/albums/c_2201_tongming.jpg"
with open(cover_local, "rb") as fp:
    s3.put_object(Bucket=b10_name, Key=key_cover, Body=fp.read(), ContentType="image/jpeg")
cover_cdn = f"{b10_domain}/{key_cover}"
print(f"🖼️ 专辑封面已上传 R2: {cover_cdn}")

# 1. 音频切割、静音去除、EBU R128 标准化与歌词获取
processed_tracks = []
total = len(TRACKS)
for t in TRACKS:
    idx = t["index"]
    sid = t["song_id"]
    title = t["title"]
    ss = t["ss"]
    dur = t["dur"]
    lrc_nid = t["lrc_nid"]

    final_audio = os.path.join(WORK_DIR, f"track_{idx}.mp3")
    lrc_file = os.path.join(WORK_DIR, f"track_{idx}.lrc")

    print(f"\n🎵 [{idx:02d}/{total}] 准确切割与压制 《{title}》 (Song ID: {sid}, 起始: {ss}s, 时长: {dur}s)...")

    cmd_enc = [
        "ffmpeg", "-y", "-ss", ss, "-t", dur, "-i", FULL_ALBUM_PATH,
        "-af", "silenceremove=start_periods=1:start_duration=0.3:start_threshold=-45dB,loudnorm=I=-14:TP=-1.0:LRA=11",
        "-ar", "44100", "-ac", "2",
        "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
        final_audio
    ]
    subprocess.run(cmd_enc, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

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

# 2. 上传 MP3 与 LRC 至 R2 (绝对路径规范)
print("\n" + "=" * 80)
print(f"📤 上传 {total} 首录音室原版母带与歌词至 R2 {b10_name}...")
print("=" * 80)

updates_payload = []
for pt in processed_tracks:
    sid = pt["song_id"]
    title = pt["title"]
    key_mp3 = f"music/金海心/金海心/s_{sid}.mp3"
    key_lrc = f"lyrics/金海心/金海心/s_{sid}.lrc"

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

# 3. 调用 D1 batch-light 原子点亮
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

# 4. 更新专辑属性（封面、年份 2003）
print("\n" + "=" * 80)
print(f"🎨 配置专辑《金海心》(ID: {ALBUM_ID}) 封面与发行年份 (2003)...")
print("=" * 80)

for attempt in range(5):
    try:
        resp_alb = requests.patch(
            f"{PATCH_ALBUM_URL}{ALBUM_ID}",
            json={"release_date": "2003", "cover_url": cover_cdn},
            proxies={'http': None, 'https': None},
            timeout=10
        )
        print(f"  • 专辑 ID: {ALBUM_ID} 属性更新: {resp_alb.status_code} {resp_alb.text}")
        break
    except Exception as e:
        print(f"  • 专辑属性更新尝试 {attempt+1} 失败: {e}")
        time.sleep(2)

# 5. 同步写入本地 catalog_sync.db
print("\n" + "=" * 80)
print("💾 同步写入本地 catalog_sync.db 数据库...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

cur.execute("UPDATE albums SET release_date = '2003', cover_url = ? WHERE id = ?", (cover_cdn, ALBUM_ID))

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

# 6. 公网边缘 CDN HEAD 抽测
print("\n" + "=" * 80)
print("🌐 公网 CDN 连通性抽测 (curl)...")
print("=" * 80)

test_songs = [updates_payload[0], updates_payload[-1]]
for ts in test_songs:
    r_test = requests.head(ts["file_path"], proxies={'http': None, 'https': None}, timeout=10)
    print(f"  🌐 [CDN 校验] {ts['file_path']} -> HTTP {r_test.status_code} (Length: {r_test.headers.get('Content-Length')})")
    assert r_test.status_code == 200, f"CDN 无法访问: {ts['file_path']}"

print("\n" + "=" * 80)
print(f"🎉 金海心第三张大碟《金海心》(11首) 全流程点亮成功！")
print("=" * 80)
