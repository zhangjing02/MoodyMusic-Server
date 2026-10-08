#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《蒙面唱将猜猜猜》第二季 (2016) · 《蒙面唱将猜猜猜 第一季》破圈金曲大碟全量重构流水线 (共 12 首)
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
WORK_DIR = "/tmp/masked_singer_s2"
os.makedirs(WORK_DIR, exist_ok=True)

session = requests.Session()
session.trust_env = False

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

ALBUM_ID = 1950
ARTIST_NAME = "蒙面唱将猜猜猜"
ALBUM_NAME = "第二季 (2016)"
ENC_ARTIST = urllib.parse.quote(ARTIST_NAME)
ENC_ALBUM = urllib.parse.quote(ALBUM_NAME)

SEASON_2_TARGETS = [
    {
        "id": 27652,
        "track_index": 1,
        "title": "成全 - 林宥嘉 (帮我消消黑眼圈)",
        "yt_id": "_EXyLX3lSj8",
        "lrc_query": "林宥嘉 成全"
    },
    {
        "id": 31149,
        "track_index": 2,
        "title": "浪费 - 林宥嘉 & 郁可唯",
        "yt_id": "IOR7IFqoMi0",
        "lrc_query": "林宥嘉 郁可唯 浪费"
    },
    {
        "id": 27651,
        "track_index": 3,
        "title": "身骑白马 - 周深 (我可不是什么幺蛾子)",
        "yt_id": "zLLdJgG0HaY",
        "lrc_query": "周深 身骑白马"
    },
    {
        "id": 27653,
        "track_index": 4,
        "title": "搁浅 - 杨丞琳 (一闪一闪亮晶晶的钻石女士)",
        "yt_id": "hHMyljReG0g",
        "lrc_query": "杨丞琳 搁浅"
    },
    {
        "id": 27654,
        "track_index": 5,
        "title": "可惜没如果 - 金海心 (猫黛丽赫本)",
        "yt_id": "x5IE6NdMw7o",
        "lrc_query": "金海心 可惜没如果"
    },
    {
        "id": 31150,
        "track_index": 6,
        "title": "独家记忆 - 郁可唯 (哈哈一笑很倾城)",
        "yt_id": "TZ9PmsXpTAg",
        "lrc_query": "郁可唯 独家记忆"
    },
    {
        "id": 31151,
        "track_index": 7,
        "title": "苍狼大地 - 谭晶 (尖耳朵的阿凡达妹妹)",
        "yt_id": "LuED57qVc_0",
        "lrc_query": "谭晶 苍狼大地"
    },
    {
        "id": 31152,
        "track_index": 8,
        "title": "吉米来吧 - 谭晶 (尖耳朵的阿凡达妹妹)",
        "yt_id": "_3jsedgu8-Y",
        "lrc_query": "谭晶 吉米来吧"
    },
    {
        "id": 31153,
        "track_index": 9,
        "title": "海阔天空 - 谭晶 (尖耳朵的阿凡达妹妹)",
        "yt_id": "gPpffht8vHM",
        "lrc_query": "谭晶 海阔天空"
    },
    {
        "id": 31154,
        "track_index": 10,
        "title": "安静 - 许志安 (铁皮人)",
        "yt_id": "vFumuaiyIcU",
        "lrc_query": "许志安 安静"
    },
    {
        "id": 31155,
        "track_index": 11,
        "title": "淘汰 - 许志安 (铁皮人)",
        "yt_id": "EQLws6aaniE",
        "lrc_query": "许志安 淘汰"
    },
    {
        "id": 31156,
        "track_index": 12,
        "title": "好久不见 - 侧田 (童话里不是骗人的)",
        "yt_id": "ndB6Nx_gIb4",
        "lrc_query": "侧田 好久不见"
    }
]

print("=" * 80)
print("🚀 启动《蒙面唱将猜猜猜》第二季 (2016) 全量重构与采录...")
print("=" * 80)

print("\n🎯 第二季全量 12 首 ID 分配确认:")
for t in sorted(SEASON_2_TARGETS, key=lambda x: x["track_index"]):
    print(f"  Track {t['track_index']:2d} | ID:{t['id']} | {t['title']}")

# 3. 逐首采录、压制、上传、获取歌词
def fetch_clean_lrc(query):
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
    try:
        lrc = syncedlyrics.search(query)
        if lrc and len(lrc) > 50:
            clean_lines = [l for l in lrc.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
            return "\n".join(clean_lines).strip()
    except Exception:
        pass
    return ""

updates = []
for t in sorted(SEASON_2_TARGETS, key=lambda x: x["track_index"]):
    sid = t["id"]
    title = t["title"]
    yt_id = t["yt_id"]
    t_idx = t["track_index"]

    raw_audio = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
    clean_audio = os.path.join(WORK_DIR, f"s_{sid}.mp3")

    if os.path.exists(clean_audio) and os.path.getsize(clean_audio) > 1000000:
        print(f"\n[{t_idx}/12] ⚡ 本地已存在压制音频 ({os.path.getsize(clean_audio)} 字节)，复用并跳过下载...")
    else:
        print(f"\n[{t_idx}/12] ⬇️ 下载采录: {title} (YT: {yt_id})...")
        dl_cmd = f'yt-dlp --proxy http://127.0.0.1:7897 --extractor-args "youtube:player_client=android,web" -x --audio-format mp3 -o "{WORK_DIR}/raw_{sid}.%(ext)s" "https://www.youtube.com/watch?v={yt_id}"'
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
for attempt in range(3):
    try:
        light_res = session.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": updates}, timeout=35)
        print("batch-light 响应:", light_res.status_code, light_res.text)
        if light_res.status_code == 200:
            break
    except Exception as e:
        print(f"batch-light 重试 {attempt+1}: {e}")
        time.sleep(2)

# 5. 终验
print("\n" + "=" * 80)
print("🔍 第二季 12 首生产环境 HTTP HEAD 1:1 强校验...")
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
    print("\n🎉《蒙面唱将猜猜猜》第二季 12 首全量 100% 满格点亮！")
else:
    print("\n⚠️ 存在未通过检验的曲目，需排查。")

