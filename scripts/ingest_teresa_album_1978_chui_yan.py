#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_teresa_album_1978_chui_yan.py
邓丽君 (Teresa Teng) 1978 宝丽金传世大碟《又见炊烟》(12首全量点亮)
含《又见炊烟》《侬情万缕》《使爱情更美丽》《我心深处》等传世名曲
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

BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
PATCH_ALBUM_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/"

WORK_DIR = os.path.join(BASE_DIR, 'backend', 'tmp', 'teresa_chui_yan_1978')
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

ALBUM_ID = 287

TRACKS = [
    {"index": 1, "song_id": 4415, "title": "裝作不知道", "netease_id": 1397662870, "exp_dur": 217},
    {"index": 2, "song_id": 4416, "title": "相見在明天", "netease_id": 1397663767, "exp_dur": 278},
    {"index": 3, "song_id": 4417, "title": "我不再迷惘", "netease_id": 1397662871, "exp_dur": 202},
    {"index": 4, "song_id": 4418, "title": "多少黎明多少黃昏裡", "netease_id": 1397663768, "exp_dur": 243},
    {"index": 5, "song_id": 4419, "title": "願你來看我", "netease_id": 1397663769, "exp_dur": 199},
    {"index": 6, "song_id": 4420, "title": "儂情萬縷", "netease_id": 1397663770, "exp_dur": 176},
    {"index": 7, "song_id": 4421, "title": "又見炊煙", "netease_id": 1397662872, "yt_id": "zcjPCd08K90", "exp_dur": 174},
    {"index": 8, "song_id": 4422, "title": "使愛情更美麗", "netease_id": 1397662873, "exp_dur": 257},
    {"index": 9, "song_id": 4423, "title": "我心深處", "netease_id": 1397663771, "yt_id": "7IsRnx6qFzw", "exp_dur": 231},
    {"index": 10, "song_id": 4424, "title": "青色的回憶", "netease_id": 1397662874, "exp_dur": 192},
    {"index": 11, "song_id": 4425, "title": "情飄飄", "netease_id": 1397663772, "exp_dur": 220},
    {"index": 12, "song_id": 4426, "title": "夜的投影", "netease_id": 1397662875, "exp_dur": 205}
]

COVER_SOURCE_URL = "https://p1.music.126.net/k6AbZdMEbumlQiPZsbnLaQ==/109951169245205431.jpg"

print("=" * 80)
print("🚀 启动邓丽君 1978 宝丽金传世大碟《又见炊烟》(12首) 录音室原版母带点亮流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print(f"💿 目标专辑 ID: {ALBUM_ID}")
print("=" * 80)

# 0. 封面下载与上传
cover_local = os.path.join(WORK_DIR, "c_287_you_jian_chui_yan.jpg")
if not os.path.exists(cover_local) or os.path.getsize(cover_local) < 5000:
    r_img = requests.get(COVER_SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with open(cover_local, 'wb') as fp:
        fp.write(r_img.content)
    print(f"🖼️ 专辑封面已下载: {os.path.getsize(cover_local)} 字节")

key_cover = "covers/albums/c_287_you_jian_chui_yan.jpg"
with open(cover_local, "rb") as fp:
    s3.put_object(Bucket=b10_name, Key=key_cover, Body=fp.read(), ContentType="image/jpeg")
cover_cdn = f"{b10_domain}/{key_cover}"
print(f"🖼️ 专辑封面已上传 R2: {cover_cdn}")

# 1. 音频下载、静音切除、EBU R128 标准化与歌词获取
processed_tracks = []
for t in TRACKS:
    idx = t["index"]
    sid = t["song_id"]
    title = t["title"]
    nid = t["netease_id"]
    yt_id = t.get("yt_id")
    exp_dur = t["exp_dur"]
    
    raw_audio = os.path.join(WORK_DIR, f"raw_{idx}.mp3")
    final_audio = os.path.join(WORK_DIR, f"track_{idx}.mp3")
    lrc_file = os.path.join(WORK_DIR, f"track_{idx}.lrc")
    
    print(f"\n🎵 [{idx:02d}/12] 采录与压制 《{title}》 (Song ID: {sid}, 预计 {exp_dur}s)...")
    
    if not os.path.exists(final_audio) or os.path.getsize(final_audio) < 10000:
        if not os.path.exists(raw_audio) or os.path.getsize(raw_audio) < 10000:
            if yt_id:
                cmd_dl = [
                    'yt-dlp', '--proxy', 'http://127.0.0.1:10090',
                    '-x', '--audio-format', 'mp3',
                    '-o', raw_audio,
                    f"https://www.youtube.com/watch?v={yt_id}"
                ]
                for attempt in range(3):
                    try:
                        subprocess.run(cmd_dl, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                        break
                    except Exception as e:
                        if attempt == 2: raise e
                        import time; time.sleep(2)
            else:
                dl_url = f"https://music.163.com/song/media/outer/url?id={nid}.mp3"
                r_audio = requests.get(dl_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True)
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
    
    out_dur = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", final_audio
    ]).decode().strip()
    dur_int = round(float(out_dur))
    mp3_sz = os.path.getsize(final_audio)
    
    # 歌词获取
    if not os.path.exists(lrc_file) or os.path.getsize(lrc_file) < 50:
        r_lrc = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1", headers={'User-Agent': 'Mozilla/5.0'}).json()
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

# 2. 上传 MP3 与 LRC 至 R2 (使用绝对路径标准 s_{id}.mp3 命名)
print("\n" + "=" * 80)
print(f"📤 上传 12 首录音室原版母带与歌词至 R2 {b10_name}...")
print("=" * 80)

updates_payload = []
for pt in processed_tracks:
    sid = pt["song_id"]
    title = pt["title"]
    key_mp3 = f"music/邓丽君/又见炊烟/s_{sid}.mp3"
    key_lrc = f"lyrics/邓丽君/又见炊烟/s_{sid}.lrc"
    
    with open(pt["mp3_path"], "rb") as fp:
        s3.put_object(Bucket=b10_name, Key=key_mp3, Body=fp.read(), ContentType="audio/mpeg")
    with open(pt["lrc_path"], "rb") as fp:
        s3.put_object(Bucket=b10_name, Key=key_lrc, Body=fp.read(), ContentType="text/plain; charset=utf-8")
        
    head_mp3 = s3.head_object(Bucket=b10_name, Key=key_mp3)
    head_lrc = s3.head_object(Bucket=b10_name, Key=key_lrc)
    assert head_mp3["ContentLength"] == pt["mp3_size"]
    assert head_lrc["ContentLength"] == pt["lrc_size"]
    
    cdn_mp3 = f"{b10_domain}/{key_mp3}"
    cdn_lrc = f"{b10_domain}/{key_lrc}"
    
    print(f"  ✅ [S3 HEAD OK] 《{title}》 (ID: {sid}) -> {cdn_mp3}")
    
    updates_payload.append({
        "id": sid,
        "file_path": cdn_mp3,
        "lrc_path": cdn_lrc,
        "duration": pt["duration"],
        "is_lit": 1
    })

# 3. 调用 D1 batch-light 更新绝对直链与点亮
print("\n" + "=" * 80)
print("⚡ 调用 D1 batch-light 进行原子点亮与绝对直链切链...")
print("=" * 80)

resp_light = requests.post(
    BATCH_LIGHT_URL,
    json={"updates": updates_payload},
    headers={"Content-Type": "application/json"},
    proxies={'http': None, 'https': None},
    timeout=20
)
print("batch-light 返回:", resp_light.status_code, resp_light.text)
assert resp_light.ok

# 4. 更新专辑属性（封面、年份 1978）
print("\n" + "=" * 80)
print("🎨 配置专辑《又见炊烟》封面与发行年份 (1978)...")
print("=" * 80)

resp_alb = requests.patch(
    f"{PATCH_ALBUM_URL}{ALBUM_ID}",
    json={"release_date": "1978", "cover_url": cover_cdn},
    proxies={'http': None, 'https': None}
)
print(f"  • 专辑 ID: {ALBUM_ID} 属性更新: {resp_alb.status_code} {resp_alb.text}")

# 5. 同步写入本地 catalog_sync.db 数据库
print("\n" + "=" * 80)
print("💾 同步写入本地 catalog_sync.db 数据库...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

# 更新 albums 表
cur.execute("UPDATE albums SET cover_url = ?, release_date = '1978' WHERE id = ?", (cover_cdn, ALBUM_ID))

# 更新 12 首歌曲
for u in updates_payload:
    sid = u["id"]
    cur.execute("""
        UPDATE songs 
        SET file_path = ?, lrc_path = ?, duration = ?
        WHERE id = ?
    """, (u["file_path"], u["lrc_path"], u["duration"], sid))

conn.commit()
conn.close()
print("  ✅ 本地数据库同步成功！")

# 6. 公网边缘 CDN HEAD 抽测
print("\n" + "=" * 80)
print("🌐 公网 CDN 连通性抽测...")
print("=" * 80)
for u in updates_payload:
    p = urllib.parse.urlsplit(u["file_path"])
    u_enc = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), '', ''))
    req = urllib.request.Request(u_enc, headers={'User-Agent': 'Mozilla/5.0'})
    r_chk = urllib.request.urlopen(req, timeout=10)
    print(f"  • ID {u['id']} HEAD [{r_chk.status}] (Content-Length: {r_chk.headers.get('Content-Length')})")

print("\n🎉 邓丽君 1978 宝丽金传世神专《又见炊烟》(12首) 全盘采录压制、上传、入库并成功点亮！")
