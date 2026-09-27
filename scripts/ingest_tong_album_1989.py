#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_tong_album_1989.py
童安格 (Angus Tung) 歌手档案创建与 1989 宝丽金传世神专《其实你不懂我的心》(12首) 录音室母带全盘入库点亮流水线
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

CREATE_FULL_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/create-full"
BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
PATCH_ALBUM_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/"

WORK_DIR = os.path.join(BASE_DIR, 'backend', 'tmp', 'tong_1989')
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
    {"index": 1, "title": "其实你不懂我的心", "yt_id": "ttiuVmonjTw", "netease_id": 150992, "exp_dur": 195},
    {"index": 2, "title": "让生命等候", "yt_id": "zD9ifymB69k", "netease_id": 150994, "exp_dur": 257},
    {"index": 3, "title": "明天你是否依然爱我", "yt_id": "3f-jLzwTwLY", "netease_id": 150996, "exp_dur": 256},
    {"index": 4, "title": "飞雪", "yt_id": "qO0Zd0WoKSY", "netease_id": 150999, "exp_dur": 301},
    {"index": 5, "title": "别离歌", "yt_id": "HvyHtLXqJR4", "netease_id": 151002, "exp_dur": 233},
    {"index": 6, "title": "忘不了", "yt_id": "gX7p7znIlhA", "netease_id": 151005, "exp_dur": 254},
    {"index": 7, "title": "干燥花", "yt_id": "HgIGCfxpzXs", "netease_id": 151007, "exp_dur": 215},
    {"index": 8, "title": "永远不要说放弃", "yt_id": "-U8P-uy04cw", "netease_id": 151009, "exp_dur": 263},
    {"index": 9, "title": "看不清的未来", "yt_id": "8VTdWf-l_zA", "netease_id": 151011, "exp_dur": 298},
    {"index": 10, "title": "爱,让世界更美", "yt_id": "bslbM34armc", "netease_id": 151014, "exp_dur": 226},
    {"index": 11, "title": "扑克先生", "yt_id": "gWhlvDopHh8", "netease_id": 151017, "exp_dur": 259},
    {"index": 12, "title": "灯", "yt_id": "xVdmMWHftCU", "netease_id": 151021, "exp_dur": 214}
]

print("=" * 80)
print("🚀 启动童安格建档与 1989 宝丽金《其实你不懂我的心》(12首) 录音室原版母带入库流水线...")
print(f"📦 目标存储桶: {b10_name} ({b10_domain})")
print("=" * 80)

# 1. 下载、压制与歌词获取
processed_tracks = []
for t in TRACKS:
    idx = t["index"]
    title = t["title"]
    yt_id = t["yt_id"]
    nid = t["netease_id"]
    exp_dur = t["exp_dur"]
    
    raw_audio = os.path.join(WORK_DIR, f"raw_{idx}.mp3")
    final_audio = os.path.join(WORK_DIR, f"track_{idx}.mp3")
    lrc_file = os.path.join(WORK_DIR, f"track_{idx}.lrc")
    
    print(f"\n🎵 [{idx:02d}/12] 采录与压制 《{title}》 (预计 {exp_dur}s)...")
    
    # 如果已处理完成，直接复用
    if not os.path.exists(final_audio) or os.path.getsize(final_audio) < 10000:
        # 下载源音频（带重试机制）
        if not os.path.exists(raw_audio) or os.path.getsize(raw_audio) < 10000:
            cmd_dl = [
                'yt-dlp', '--proxy', 'http://127.0.0.1:10090',
                '-x', '--audio-format', 'mp3',
                '-o', raw_audio,
                f"https://www.youtube.com/watch?v=http://youtube.com/watch?v={yt_id}" if "http" in yt_id else f"https://www.youtube.com/watch?v={yt_id}"
            ]
            for attempt in range(3):
                try:
                    subprocess.run(cmd_dl, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    break
                except Exception as e:
                    if attempt == 2: raise e
                    import time; time.sleep(2)
            
        # 音频前置静音切除 + EBU R128 + 160k CBR Xing MP3
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
    print(f"   ✅ 完成: 实际时长 {dur_int}s | MP3体积: {mp3_sz} 字节 | LRC体积: {lrc_sz} 字节")
    
    processed_tracks.append({
        "index": idx,
        "title": title,
        "duration": dur_int,
        "mp3_path": final_audio,
        "lrc_path": lrc_file,
        "mp3_size": mp3_sz,
        "lrc_size": lrc_sz
    })

# 2. 调用 D1 创建艺人、专辑及歌曲名录
print("\n" + "=" * 80)
print("⚡ 调用 D1 create-full 创建童安格歌手档案、专辑与 12 首歌曲...")
print("=" * 80)

create_payload = {
    "songs": [
        {
            "title": pt["title"],
            "artist_name": "童安格",
            "album_title": "其实你不懂我的心",
            "file_path": f"pending_upload_{pt['index']}",
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

# 3. 上传 MP3 与 LRC 至 R2 (使用标准 s_{id}.mp3 命名)
print("\n" + "=" * 80)
print(f"📤 上传 12 首官方录音室母带与歌词至 R2 {b10_name}...")
print("=" * 80)

updates_payload = []
for pt, sid in zip(processed_tracks, assigned_song_ids):
    title = pt["title"]
    key_mp3 = f"music/童安格/其实你不懂我的心/s_{sid}.mp3"
    key_lrc = f"lyrics/童安格/其实你不懂我的心/s_{sid}.lrc"
    
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

# 5. 更新专辑封面与发行年份，更新歌手分类
print("\n" + "=" * 80)
print("🎨 配置专辑封面、发行年份与艺人档案属性...")
print("=" * 80)

# 查询刚创建的专辑 ID 和艺人 ID
r_query = requests.get('https://m-api.changgepd.ccwu.cc/api/admin/albums/search?keyword=其实你不懂我的心', proxies={'http': None, 'https': None}).json()
al_list = r_query.get('data', {}).get('albums', [])
assert len(al_list) > 0, f"Album not found: {r_query}"
new_album_id = al_list[0]['id']
new_artist_id = al_list[0]['artist_id']

print(f"  • 童安格 Artist ID: {new_artist_id}")
print(f"  • 《其实你不懂我的心》 Album ID: {new_album_id}")

cover_cdn = f"{b10_domain}/covers/albums/c_qi_shi_ni_bu_dong_wo_de_xin.jpg"
if new_album_id:
    resp_alb = requests.patch(
        f"{PATCH_ALBUM_URL}{new_album_id}",
        json={"release_date": "1989", "cover_url": cover_cdn},
        proxies={'http': None, 'https': None}
    )
    print("  • 专辑属性更新:", resp_alb.status_code, resp_alb.json())

# 6. 同步写入本地 catalog_sync.db 数据库
print("\n" + "=" * 80)
print("💾 同步写入本地 catalog_sync.db 数据库...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

# 确保本地 artists 表有童安格
cur.execute("SELECT id FROM artists WHERE name = '童安格'")
row_art = cur.fetchone()
if not row_art:
    photo_cdn = f"{b10_domain}/covers/artists/a_tong_an_ge.jpg"
    cur.execute("INSERT INTO artists (id, name, genre, avatar_url) VALUES (?, ?, ?, ?)", (new_artist_id, '童安格', '港台', photo_cdn))
else:
    new_artist_id = row_art[0]

# 确保本地 albums 表有专辑
cur.execute("SELECT id FROM albums WHERE id = ?", (new_album_id,))
if not cur.fetchone():
    cur.execute("INSERT INTO albums (id, artist_id, title, release_date, cover_url, storage_id) VALUES (?, ?, ?, ?, ?, ?)",
                (new_album_id, new_artist_id, '其实你不懂我的心', '1989', cover_cdn, 'primary'))

# 写入 12 首歌曲
for u in updates_payload:
    sid = u["id"]
    t_item = next(item for item in processed_tracks if assigned_song_ids[item["index"]-1] == sid)
    cur.execute("DELETE FROM songs WHERE id = ?", (sid,))
    cur.execute("""
        INSERT INTO songs (id, album_id, title, track_index, duration, file_path, lrc_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sid, new_album_id, t_item["title"], t_item["index"], u["duration"], u["file_path"], u["lrc_path"]))

conn.commit()
conn.close()
print("  ✅ 本地数据库同步成功！")

# 7. 公网 CDN HEAD 验收抽测
print("\n" + "=" * 80)
print("🌐 公网 CDN 连通性抽测...")
print("=" * 80)
for u in updates_payload:
    p = urllib.parse.urlsplit(u["file_path"])
    u_enc = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), '', ''))
    req = urllib.request.Request(u_enc, headers={'User-Agent': 'Mozilla/5.0'})
    r_chk = urllib.request.urlopen(req, timeout=10)
    print(f"  • ID {u['id']} HEAD [{r_chk.status}] (Content-Length: {r_chk.headers.get('Content-Length')})")

print("\n🎉 童安格歌手档案创建完成，1989《其实你不懂我的心》全专辑 12 首录音室原版母带已全面压制、上云、入库并成功点亮！")
