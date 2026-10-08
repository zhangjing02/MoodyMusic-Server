#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《蒙面唱将猜猜猜》第一季 (2015) · 《蒙面歌王》黄金歌王大碟全量重构流水线 (共 12 首)
标准规范：歌名 - 真实歌手 (面具名)
"""

import os
import sys
import json
import time
import urllib.parse
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
API_BASE = "https://m-api.changgepd.ccwu.cc"
HEADERS = {"User-Agent": "Mozilla/5.0"}
WORK_DIR = "/tmp/masked_singer_s1"
os.makedirs(WORK_DIR, exist_ok=True)

session = requests.Session()
session.trust_env = False  # 直连 Worker API

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfgs = json.load(f)["buckets"]

r2_cfg = r2_cfgs["account_12"]
s3_client = boto3.client(
    "s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4", connect_timeout=15, read_timeout=30)
)
BUCKET_NAME = r2_cfg["name"]
PUBLIC_BASE = r2_cfg["public_url"].rstrip("/")

ALBUM_ID = 1949
ARTIST_NAME = "蒙面唱将猜猜猜"
ALBUM_NAME = "第一季 (2015)"
ENC_ARTIST = urllib.parse.quote(ARTIST_NAME)
ENC_ALBUM = urllib.parse.quote(ALBUM_NAME)

SEASON_1_TARGETS = [
    # 既有 6 首复用重塑
    {
        "mode": "reuse",
        "id": 27645,
        "track_index": 1,
        "title": "富士山下 - 李克勤 (白棱镜)",
        "yt_id": "uYowfw3_cf4",
        "lrc_query": "李克勤 富士山下"
    },
    {
        "mode": "reuse",
        "id": 27646,
        "track_index": 2,
        "title": "忘记你我做不到 - 李克勤 (白棱镜)",
        "yt_id": "osxBroW5XDQ",
        "lrc_query": "李克勤 忘记你我做不到"
    },
    {
        "mode": "reuse",
        "id": 27647,
        "track_index": 3,
        "title": "拯救 - 丁当 (黑天鹅)",
        "yt_id": "k3FJPcw9NnU",
        "lrc_query": "丁当 拯救"
    },
    {
        "mode": "reuse",
        "id": 27648,
        "track_index": 4,
        "title": "千年之恋 - 丁当 (黑天鹅)",
        "yt_id": "IpdahWvwDNU",
        "lrc_query": "丁当 千年之恋"
    },
    {
        "mode": "reuse",
        "id": 27649,
        "track_index": 5,
        "title": "白天不懂夜的黑 - 孙楠 (羊驼)",
        "yt_id": "vY8NYBEdzx0",
        "lrc_query": "孙楠 白天不懂夜的黑"
    },
    {
        "mode": "reuse",
        "id": 27650,
        "track_index": 6,
        "title": "爱情三十六计 - 许茹芸 (铁扇奥特曼)",
        "yt_id": "5E5q0MFghKA",
        "lrc_query": "许茹芸 爱情三十六计"
    },
    # 增量插入 6 首
    {
        "mode": "insert",
        "track_index": 7,
        "title": "Someone Like You - 曹格 (齐天大圣)",
        "yt_id": "TSSwzyfH79M",
        "lrc_query": "曹格 Someone Like You"
    },
    {
        "mode": "insert",
        "track_index": 8,
        "title": "野子 - 沙宝亮 (流浪者)",
        "yt_id": "5InKckoDyLQ",
        "lrc_query": "沙宝亮 野子"
    },
    {
        "mode": "insert",
        "track_index": 9,
        "title": "要死就一定要死在你手里 - 沙宝亮 (流浪者)",
        "yt_id": "j3m7ZLaSinQ",
        "lrc_query": "沙宝亮 要死就一定要死在你手里"
    },
    {
        "mode": "insert",
        "track_index": 10,
        "title": "斑马斑马 - 沙宝亮 (流浪者)",
        "yt_id": "H7klQi-4n9M",
        "lrc_query": "沙宝亮 斑马斑马"
    },
    {
        "mode": "insert",
        "track_index": 11,
        "title": "轮回 - 谭维维 (野草)",
        "yt_id": "cvdcgHx_aU0",
        "lrc_query": "谭维维 轮回"
    },
    {
        "mode": "insert",
        "track_index": 12,
        "title": "我要你的爱 - 黄小琥 (千面娇娃)",
        "yt_id": "dVQnrPElFTs",
        "lrc_query": "黄小琥 我要你的爱"
    }
]

print("=" * 80)
print("🚀 启动《蒙面唱将猜猜猜》第一季 (2015) 全量重构与采录...")
print("=" * 80)

# 1. 批量更名既有 6 首
update_payload = {
    "updates": [
        {"id": t["id"], "title": t["title"], "track_index": t["track_index"]}
        for t in SEASON_1_TARGETS if t["mode"] == "reuse"
    ]
}
print("📝 更新既有 6 首曲目骨架...")
up_res = session.post(f"{API_BASE}/api/admin/songs/batch-update", json=update_payload, timeout=25)
print("batch-update 响应:", up_res.json())

# 2. 插入增量 6 首
insert_songs = [
    {"title": t["title"], "track_index": t["track_index"]}
    for t in SEASON_1_TARGETS if t["mode"] == "insert"
]
insert_payload = {
    "artist_name": ARTIST_NAME,
    "album_title": ALBUM_NAME,
    "songs": insert_songs,
    "dry_run": False
}
print("📦 提交增量 6 首曲目 batch-insert...")
ins_res = session.post(f"{API_BASE}/api/admin/ops/songs/batch-insert", json=insert_payload, timeout=25)
ins_data = ins_res.json()
print("batch-insert 响应:", ins_data)

new_song_ids = ins_data.get("data", {}).get("song_ids", [])
if not new_song_ids:
    det = session.get(f"{API_BASE}/api/admin/albums/detail?album_id={ALBUM_ID}", timeout=15).json()
    new_song_ids = [s["id"] for s in sorted(det.get("data", {}).get("songs", []), key=lambda x: x["track_index"]) if s["track_index"] >= 7]

insert_idx = 0
for t in SEASON_1_TARGETS:
    if t["mode"] == "insert":
        t["id"] = new_song_ids[insert_idx]
        insert_idx += 1

print("\n🎯 全量 12 首 ID 分配确认:")
for t in SEASON_1_TARGETS:
    print(f"  Track {t['track_index']:2d} | ID:{t['id']} | {t['title']}")

# 3. 逐首采录、压制、上传、获取歌词
def fetch_clean_lrc(query):
    # 网易云优先
    try:
        r = requests.get(f"https://music.163.com/api/search/get/web?s={urllib.parse.quote(query)}&type=1&limit=3", headers=HEADERS, timeout=6).json()
        songs = r.get("result", {}).get("songs", [])
        if songs:
            sid = songs[0]["id"]
            lr = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1", headers=HEADERS, timeout=6).json()
            lrc_text = lr.get("lrc", {}).get("lyric", "")
            if lrc_text and len(lrc_text.strip()) > 50:
                clean_lines = [l for l in lrc_text.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
                return "\n".join(clean_lines).strip()
    except Exception:
        pass
    # syncedlyrics 兜底
    try:
        lrc = syncedlyrics.search(query)
        if lrc and len(lrc) > 50:
            clean_lines = [l for l in lrc.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
            return "\n".join(clean_lines).strip()
    except Exception:
        pass
    return ""

updates = []
for t in SEASON_1_TARGETS:
    sid = t["id"]
    title = t["title"]
    yt_id = t["yt_id"]
    t_idx = t["track_index"]

    raw_audio = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
    clean_audio = os.path.join(WORK_DIR, f"s_{sid}.mp3")

    print(f"\n[{t_idx}/12] ⬇️ 下载采录: {title} (YT: {yt_id})...")
    dl_cmd = f"yt-dlp --proxy http://127.0.0.1:7897 -x --audio-format mp3 -o \"{WORK_DIR}/raw_{sid}.%(ext)s\" https://www.youtube.com/watch?v={yt_id}"
    subprocess.run(dl_cmd, shell=True, check=True)

    print(f"[{t_idx}/12] 🎵 执行 EBU R128 标准化压制...")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", raw_audio,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
        clean_audio
    ]
    subprocess.run(ffmpeg_cmd, check=True)

    # 上传音频
    mp3_key = f"music/{ARTIST_NAME}/{ALBUM_NAME}/s_{sid}.mp3"
    print(f"[{t_idx}/12] ☁️ 上传音频至 R2: {mp3_key}")
    s3_client.upload_file(clean_audio, BUCKET_NAME, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})

    # 获取并上传歌词
    lrc_text = fetch_clean_lrc(t["lrc_query"])
    if not lrc_text:
        lrc_text = f"[00:00.00]{title}\n[00:05.00]（蒙面经典现场纯享，暂无歌词）"
    lrc_key = f"lyrics/{ARTIST_NAME}/{ALBUM_NAME}/s_{sid}.lrc"
    print(f"[{t_idx}/12] 📝 上传歌词至 R2: {lrc_key} ({len(lrc_text)} 字节)")
    s3_client.put_object(Bucket=BUCKET_NAME, Key=lrc_key, Body=lrc_text.encode("utf-8"), ContentType="text/plain; charset=utf-8")

    mp3_public_url = f"{PUBLIC_BASE}/music/{ENC_ARTIST}/{ENC_ALBUM}/s_{sid}.mp3"
    lrc_public_url = f"{PUBLIC_BASE}/lyrics/{ENC_ARTIST}/{ENC_ALBUM}/s_{sid}.lrc"
    updates.append({
        "id": sid,
        "file_path": mp3_public_url,
        "lrc_path": lrc_public_url
    })

# 4. 提交 batch-light 点亮
print(f"\n⚡ 正在向 D1 提交全量 12 首 batch-light 点亮...")
light_res = session.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": updates}, timeout=25)
print("batch-light 响应:", light_res.status_code, light_res.text)

# 5. 终验
print("\n" + "=" * 80)
print("🔍 第一季 12 首生产环境 HTTP HEAD 1:1 强校验...")
print("=" * 80)
all_pass = True
for u in updates:
    r_m = session.head(u["file_path"], timeout=10)
    r_l = session.head(u["lrc_path"], timeout=10)
    ok = (r_m.status_code == 200 and r_l.status_code == 200)
    print(f"ID {u['id']} | MP3: {r_m.status_code} ({r_m.headers.get('Content-Length')}B) | LRC: {r_l.status_code} ({r_l.headers.get('Content-Length')}B) | {'✅' if ok else '❌'}")
    if not ok:
        all_pass = False

if all_pass:
    print("\n🎉《蒙面唱将猜猜猜》第一季 12 首全量 100% 满格点亮！")
else:
    print("\n⚠️ 存在未通过检验的曲目，需排查。")

