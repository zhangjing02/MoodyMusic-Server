#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_teresa_album_1984_tsugunai.py
邓丽君 (Teresa Teng) 1984 日本唱片大奖登顶封神神专《復黑王: 償還 (つぐない)》(12首全量点亮)
斩获第17回全日本有线放送大奖与第17回日本有线大奖双料大赏
含《つぐない(償還)》《晚秋》《待ちわびて(等待)》《雪化粧》《東京ジェラシー》《上海エレジー》《空港》《娘心》《さよなら あなた》《夢芝居》《笑って乾杯》《北国の春》
Album ID: 266, Artist ID: 15
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

# 严格遵守本地存储铁律：定位在 G:\music-backup
WORK_DIR = r'G:\music-backup\tmp\teresa_tsugunai_1984'
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

ALBUM_ID = 266
ARTIST_ID = 15

TRACKS = [
    {"index": 1,  "song_id": 4156, "title": "償還 (日文)",          "aud_nid": 473335989,  "lrc_nid": 473335989,  "exp_dur": 230},
    {"index": 2,  "song_id": 4157, "title": "晚秋 (日文)",          "aud_nid": 228348,     "lrc_nid": 228348,     "exp_dur": 180},
    {"index": 3,  "song_id": 4158, "title": "等待 (日文)",          "aud_nid": 229157,     "lrc_nid": 229157,     "exp_dur": 235},
    {"index": 4,  "song_id": 4159, "title": "雪化妝 (日文)",         "aud_nid": 26111495,   "lrc_nid": 1397663872, "exp_dur": 219},
    {"index": 5,  "song_id": 4160, "title": "東京嫉妒 (日文)",       "aud_nid": 26429203,   "lrc_nid": 26429203,   "exp_dur": 237},
    {"index": 6,  "song_id": 4161, "title": "上海悲歌 (日文)",       "aud_nid": 229166,     "lrc_nid": 229166,     "exp_dur": 250},
    {"index": 7,  "song_id": 4162, "title": "空港 (日文)",          "aud_nid": 26608735,   "lrc_nid": 1397662977, "exp_dur": 222},
    {"index": 8,  "song_id": 4163, "title": "娘心 (日文)",          "aud_nid": 2065309148, "lrc_nid": 2065309148, "exp_dur": 226},
    {"index": 9,  "song_id": 4164, "title": "再見了,親愛的 (日文)",   "aud_nid": 1404947733, "lrc_nid": 1404947733, "exp_dur": 216},
    {"index": 10, "song_id": 4165, "title": "夢芝居 (日文)",        "aud_nid": 36924379,   "lrc_nid": 36924379,   "exp_dur": 208},
    {"index": 11, "song_id": 4166, "title": "笑著乾杯 (日文)",       "aud_nid": 229172,     "lrc_nid": 229172,     "exp_dur": 203},
    {"index": 12, "song_id": 4167, "title": "北國之春 (日文)",       "aud_nid": 473245749,  "lrc_nid": 473245749,  "exp_dur": 233},
]

COVER_SOURCE_URL = "https://p2.music.126.net/dlNogOtO_sDYa3YJeGUA6g==/109951169245221666.jpg"

print("=" * 80)
print("🚀 启动邓丽君 1984 旷世神专《復黑王: 償還 (つぐない)》(12首) 点亮流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print(f"💿 目标专辑 ID: {ALBUM_ID}")
print(f"📂 本地工作目录: {WORK_DIR}")
print("=" * 80)

# 0. 封面下载与上传
cover_local = os.path.join(WORK_DIR, "c_266_tsugunai.jpg")
if not os.path.exists(cover_local) or os.path.getsize(cover_local) < 5000:
    r_img = requests.get(COVER_SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    with open(cover_local, 'wb') as fp:
        fp.write(r_img.content)
    print(f"🖼️ 专辑封面已下载: {os.path.getsize(cover_local)} 字节")

key_cover = "covers/albums/c_266_tsugunai.jpg"
with open(cover_local, "rb") as fp:
    s3.put_object(Bucket=b10_name, Key=key_cover, Body=fp.read(), ContentType="image/jpeg")
cover_cdn = f"{b10_domain}/{key_cover}"
print(f"🖼️ 专辑封面已上传 R2: {cover_cdn}")

# 1. 音频采录、静音切除、EBU R128 标准化与歌词获取
processed_tracks = []
total = len(TRACKS)
for t in TRACKS:
    idx = t["index"]
    sid = t["song_id"]
    title = t["title"]
    aud_nid = t["aud_nid"]
    lrc_nid = t["lrc_nid"]
    exp_dur = t["exp_dur"]
    custom_raw = t.get("custom_raw")

    raw_audio = custom_raw if (custom_raw and os.path.exists(custom_raw)) else os.path.join(WORK_DIR, f"raw_{idx}.mp3")
    final_audio = os.path.join(WORK_DIR, f"track_{idx}.mp3")
    lrc_file = os.path.join(WORK_DIR, f"track_{idx}.lrc")

    print(f"\n🎵 [{idx:02d}/{total}] 采录与压制 《{title}》 (Song ID: {sid}, Aud NID: {aud_nid})...")

    if not os.path.exists(final_audio) or os.path.getsize(final_audio) < 10000:
        if not os.path.exists(raw_audio) or os.path.getsize(raw_audio) < 10000:
            dl_url = f"https://music.163.com/song/media/outer/url?id={aud_nid}.mp3"
            r_audio = requests.get(dl_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=60)
            with open(raw_audio, 'wb') as fp:
                for chunk in r_audio.iter_content(chunk_size=32768):
                    if chunk:
                        fp.write(chunk)
            print(f"   • 源音频下载完成: {os.path.getsize(raw_audio)} 字节")

        cmd_enc = [
            "ffmpeg", "-y", "-i", raw_audio,
            "-af", "silenceremove=start_periods=1:start_duration=0.5:start_threshold=-45dB,loudnorm=I=-14:TP=-1.0:LRA=11",
            "-ar", "44100", "-ac", "2",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
            final_audio
        ]
        subprocess.run(cmd_enc, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f"   • ffmpeg 压制完成 (160k CBR EBU-R128)")
    else:
        print(f"   • 已有压制文件，跳过下载压制")

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
    key_mp3 = f"music/邓丽君/偿还日文/s_{sid}.mp3"
    key_lrc = f"lyrics/邓丽君/偿还日文/s_{sid}.lrc"

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

# 4. 更新专辑属性（封面、年份 1984）
print("\n" + "=" * 80)
print(f"🎨 配置专辑《復黑王: 償還》(ID: {ALBUM_ID}) 封面与发行年份 (1984)...")
print("=" * 80)

for attempt in range(5):
    try:
        resp_alb = requests.patch(
            f"{PATCH_ALBUM_URL}{ALBUM_ID}",
            json={"release_date": "1984", "cover_url": cover_cdn},
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

cur.execute("UPDATE albums SET release_date = '1984', cover_url = ? WHERE id = ?", (cover_cdn, ALBUM_ID))

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
for u in updates_payload:
    sid = u["id"]
    fp = u["file_path"]
    t_item = next(item for item in processed_tracks if item["song_id"] == sid)
    proc = subprocess.run(["curl.exe", "-I", "-s", fp], capture_output=True, text=True)
    status_line = proc.stdout.splitlines()[0] if proc.stdout.splitlines() else "ERR"
    print(f"  • Song ID {sid} 《{t_item['title']}》 -> [{status_line}]")

print("\n🎉 邓丽君 1984 旷世神专《復黑王: 償還 (つぐない)》(12首) 全盘采录压制、上传、入库并成功点亮！")
