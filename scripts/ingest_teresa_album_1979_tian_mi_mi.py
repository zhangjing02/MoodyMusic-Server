#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_teresa_album_1979_tian_mi_mi.py
邓丽君 (Teresa Teng) 1979 宝丽金传世神专《甜蜜蜜》(12首全量点亮)
含《甜蜜蜜》《你在我梦里》《翠湖寒》《古树下》《野生花》《阵阵春风柔》等传世名曲
"""

import os
import sys
import json
import time
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

CREATE_FULL_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/create-full"
BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
PATCH_ALBUM_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/"

WORK_DIR = os.path.join(BASE_DIR, 'backend', 'tmp', 'teresa_tian_mi_mi_1979')
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

TRACKS = [
    {"index": 1, "title": "甜蜜蜜", "netease_id": 229744, "yt_id": "Uc7MYu0BRdg", "exp_dur": 211},
    {"index": 2, "title": "你在我梦里", "netease_id": 229745, "exp_dur": 245},
    {"index": 3, "title": "寄语多情人", "netease_id": 229746, "exp_dur": 161},
    {"index": 4, "title": "挥别", "netease_id": 229748, "exp_dur": 182},
    {"index": 5, "title": "遗忘", "netease_id": 229750, "exp_dur": 198},
    {"index": 6, "title": "梦向何处寻", "netease_id": 229752, "exp_dur": 176},
    {"index": 7, "title": "难忘的一天", "netease_id": 229754, "exp_dur": 232},
    {"index": 8, "title": "爱在我心中", "netease_id": 229756, "exp_dur": 192},
    {"index": 9, "title": "翠湖寒", "netease_id": 229758, "exp_dur": 170},
    {"index": 10, "title": "古树下", "netease_id": 229760, "exp_dur": 193},
    {"index": 11, "title": "野生花", "netease_id": 229762, "exp_dur": 146},
    {"index": 12, "title": "阵阵春风柔", "netease_id": 229764, "exp_dur": 194}
]

COVER_SOURCE_URL = "https://p1.music.126.net/8E2XpulhIjrkt08QSdchlg==/109951169245212725.jpg"

print("=" * 80)
print("🚀 启动邓丽君 1979 宝丽金传世大碟《甜蜜蜜》(12首) 录音室原版母带点亮流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print("=" * 80)

# 0. 封面下载与上传
cover_local = os.path.join(WORK_DIR, "c_tian_mi_mi_1979.jpg")
if not os.path.exists(cover_local) or os.path.getsize(cover_local) < 5000:
    r_img = requests.get(COVER_SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with open(cover_local, 'wb') as fp:
        fp.write(r_img.content)
    print(f"🖼️ 专辑封面已下载: {os.path.getsize(cover_local)} 字节")

key_cover = "covers/albums/c_tian_mi_mi_1979.jpg"
with open(cover_local, "rb") as fp:
    s3.put_object(Bucket=b10_name, Key=key_cover, Body=fp.read(), ContentType="image/jpeg")
cover_cdn = f"{b10_domain}/{key_cover}"
print(f"🖼️ 专辑封面已上传 R2: {cover_cdn}")

# 1. 音频下载、静音切除、EBU R128 标准化与歌词获取
processed_tracks = []
for t in TRACKS:
    idx = t["index"]
    title = t["title"]
    nid = t["netease_id"]
    yt_id = t.get("yt_id")
    exp_dur = t["exp_dur"]
    
    raw_audio = os.path.join(WORK_DIR, f"raw_{idx}.mp3")
    final_audio = os.path.join(WORK_DIR, f"track_{idx}.mp3")
    lrc_file = os.path.join(WORK_DIR, f"track_{idx}.lrc")
    
    print(f"\n🎵 [{idx:02d}/12] 采录与压制 《{title}》 (预计 {exp_dur}s)...")
    
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
                        time.sleep(2)
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
        "title": title,
        "duration": dur_int,
        "mp3_path": final_audio,
        "lrc_path": lrc_file,
        "mp3_size": mp3_sz,
        "lrc_size": lrc_sz
    })

# 2. 调用 D1 创建专辑《甜蜜蜜》与 12 首歌曲名录
print("\n" + "=" * 80)
print("⚡ 调用 D1 create-full 创建专辑《甜蜜蜜》与 12 首歌曲名录...")
print("=" * 80)

create_payload = {
    "songs": [
        {
            "title": pt["title"],
            "artist_name": "邓丽君",
            "album_title": "甜蜜蜜",
            "file_path": f"pending_upload_tmm_{pt['index']}",
            "track_index": pt["index"],
            "duration": pt["duration"]
        }
        for pt in processed_tracks
    ]
}

resp_create = requests.post(
    CREATE_FULL_URL,
    json=create_payload,
    headers={"Content-Type": "application/json"},
    proxies={'http': None, 'https': None},
    timeout=20
)
print("create-full 返回:", resp_create.status_code, resp_create.text)
assert resp_create.ok
create_data = resp_create.json().get('data', {})
assigned_song_ids = create_data.get('song_ids', [])
assert len(assigned_song_ids) == 12
print("  ✅ 成功获得 12 首歌曲 D1 主键 ID:", assigned_song_ids)

# 3. 上传 MP3 与 LRC 至 R2 (使用绝对路径标准 s_{id}.mp3 命名)
print("\n" + "=" * 80)
print(f"📤 上传 12 首录音室原版母带与歌词至 R2 {b10_name}...")
print("=" * 80)

updates_payload = []
for pt, sid in zip(processed_tracks, assigned_song_ids):
    title = pt["title"]
    key_mp3 = f"music/邓丽君/甜蜜蜜/s_{sid}.mp3"
    key_lrc = f"lyrics/邓丽君/甜蜜蜜/s_{sid}.lrc"
    
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

# 4. 调用 D1 batch-light 更新绝对直链与点亮
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

# 5. 更新专辑属性（封面、年份 1979）
print("\n" + "=" * 80)
print("🎨 配置专辑《甜蜜蜜》封面与发行年份 (1979)...")
print("=" * 80)

tmm_album_id = None
artist_id = 15
for attempt in range(5):
    try:
        r_query = requests.get('https://m-api.changgepd.ccwu.cc/api/admin/albums/search?keyword=甜蜜蜜', proxies={'http': None, 'https': None}, timeout=10).json()
        al_list = r_query.get('data', {}).get('albums', [])
        if al_list:
            tmm_album_id = al_list[0]['id']
            artist_id = al_list[0]['artist_id']
            break
    except Exception as e:
        print(f"  • 查询尝试 {attempt} 失败: {e}")
        time.sleep(2)

assert tmm_album_id is not None, "Failed to get album ID for 甜蜜蜜"
print(f"  • 成功查得《甜蜜蜜》Album ID: {tmm_album_id}")

for attempt in range(5):
    try:
        resp_alb = requests.patch(
            f"{PATCH_ALBUM_URL}{tmm_album_id}",
            json={"release_date": "1979", "cover_url": cover_cdn},
            proxies={'http': None, 'https': None},
            timeout=10
        )
        print(f"  • 专辑 ID: {tmm_album_id} 属性更新: {resp_alb.status_code} {resp_alb.text}")
        break
    except Exception as e:
        print(f"  • 更新尝试 {attempt} 失败: {e}")
        time.sleep(2)

# 6. 同步写入本地 catalog_sync.db 数据库
print("\n" + "=" * 80)
print("💾 同步写入本地 catalog_sync.db 数据库...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

# 确保本地 albums 表有专辑
cur.execute("SELECT id FROM albums WHERE id = ?", (tmm_album_id,))
if not cur.fetchone():
    cur.execute("INSERT INTO albums (id, artist_id, title, release_date, cover_url, storage_id) VALUES (?, ?, ?, ?, ?, ?)",
                (tmm_album_id, artist_id, '甜蜜蜜', '1979', cover_cdn, 'primary'))

for u in updates_payload:
    sid = u["id"]
    t_item = next(item for item in processed_tracks if assigned_song_ids[item["index"]-1] == sid)
    cur.execute("DELETE FROM songs WHERE id = ?", (sid,))
    cur.execute("""
        INSERT INTO songs (id, album_id, title, track_index, duration, file_path, lrc_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sid, tmm_album_id, t_item["title"], t_item["index"], u["duration"], u["file_path"], u["lrc_path"]))

conn.commit()
conn.close()
print("  ✅ 本地数据库同步成功！")

# 7. 公网边缘 CDN HEAD 抽测
print("\n" + "=" * 80)
print("🌐 公网 CDN 连通性抽测...")
print("=" * 80)
for u in updates_payload:
    p = urllib.parse.urlsplit(u["file_path"])
    u_enc = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), '', ''))
    req = urllib.request.Request(u_enc, headers={'User-Agent': 'Mozilla/5.0'})
    r_chk = urllib.request.urlopen(req, timeout=10)
    print(f"  • ID {u['id']} HEAD [{r_chk.status}] (Content-Length: {r_chk.headers.get('Content-Length')})")

print("\n🎉 邓丽君 1979 宝丽金传世神专《甜蜜蜜》(12首) 全盘采录压制、上传、入库并成功点亮！")
