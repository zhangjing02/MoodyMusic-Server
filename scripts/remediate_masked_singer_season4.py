#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《蒙面唱将猜猜猜》第四季 (2018/2019) · 《蒙面唱将猜猜猜》精选篇全量创建与采录流水线 (共 12 首)
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
WORK_DIR = "/tmp/masked_singer_s4"
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

ARTIST_NAME = "蒙面唱将猜猜猜"
ALBUM_NAME = "第四季 (2018)"
ENC_ARTIST = urllib.parse.quote(ARTIST_NAME)
ENC_ALBUM = urllib.parse.quote(ALBUM_NAME)

SEASON_4_TARGETS = [
    {
        "track_index": 1,
        "title": "雪落下的声音 - 周深 (宫廷背包客)",
        "yt_id": "nFHscxCLVnE",
        "lrc_query": "周深 雪落下的声音"
    },
    {
        "track_index": 2,
        "title": "逆光 - 吴青峰 (没事别老学我叫)",
        "yt_id": "96DbPz5jGgA",
        "lrc_query": "吴青峰 逆光"
    },
    {
        "track_index": 3,
        "title": "世界末日 - 萧敬腾 & 吴青峰",
        "yt_id": "Ot18ZB3myWg",
        "lrc_query": "萧敬腾 吴青峰 世界末日"
    },
    {
        "track_index": 4,
        "title": "空心 - 冯提莫 (小了白了兔)",
        "yt_id": "Q0cvf-EXIKk",
        "lrc_query": "冯提莫 空心"
    },
    {
        "track_index": 5,
        "title": "画心 - 冯提莫 (小了白了兔)",
        "yt_id": "0d9eheoIf5Y",
        "lrc_query": "冯提莫 画心"
    },
    {
        "track_index": 6,
        "title": "慢慢 - 刘宇宁 & 朱桦",
        "yt_id": "eo6Hb8UZApg",
        "lrc_query": "刘宇宁 慢慢"
    },
    {
        "track_index": 7,
        "title": "雨爱 - 范丞丞 (哥只是个传说)",
        "yt_id": "L_0fQPuG1jo",
        "lrc_query": "范丞丞 雨爱"
    },
    {
        "track_index": 8,
        "title": "白桦林 - 大张伟 (这一只代号叫008)",
        "yt_id": "5Zny7SgdC9E",
        "lrc_query": "朴树 白桦林"
    },
    {
        "track_index": 9,
        "title": "红玫瑰 - 刘宇宁 (超级变变变)",
        "yt_id": "5xPA0Ddnp3E",
        "lrc_query": "陈奕迅 红玫瑰"
    },
    {
        "track_index": 10,
        "title": "一生何求 - 钟镇涛 (煎蛋宝宝)",
        "yt_id": "gds9zMCpESY",
        "lrc_query": "陈百强 一生何求"
    },
    {
        "track_index": 11,
        "title": "灰色 - 徐佳莹 (给一点颜色)",
        "yt_id": "xtSdgGHqnls",
        "lrc_query": "徐佳莹 灰色"
    },
    {
        "track_index": 12,
        "title": "暗香 - 周深 & 白雪 (宫廷背包客 & 人鱼公主)",
        "yt_id": "R8_muCmzMRo",
        "lrc_query": "沙宝亮 暗香"
    }
]

print("=" * 80)
print("🚀 启动《蒙面唱将猜猜猜》第四季 (2018) 全量创建与采录流水线...")
print("=" * 80)

# 1. 调用 batch-insert 创建第四季专辑与 12 首骨架
insert_songs = [{"title": t["title"], "track_index": t["track_index"]} for t in SEASON_4_TARGETS]
insert_payload = {
    "artist_name": ARTIST_NAME,
    "album_title": ALBUM_NAME,
    "songs": insert_songs,
    "dry_run": False
}
print("📦 提交第四季 batch-insert 创建大碟与骨架...")
ins_res = session.post(f"{API_BASE}/api/admin/ops/songs/batch-insert", json=insert_payload, timeout=25)
ins_data = ins_res.json()
print("batch-insert 响应:", ins_data)

album_id = ins_data.get("data", {}).get("album_id")
song_ids = ins_data.get("data", {}).get("song_ids", [])

for idx, t in enumerate(SEASON_4_TARGETS):
    t["id"] = song_ids[idx]

print(f"\n🎯 确认第四季新建大碟 ID: {album_id}，全量 12 首 ID 分配:")
for t in SEASON_4_TARGETS:
    print(f"  Track {t['track_index']:2d} | ID:{t['id']} | {t['title']}")

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
for t in SEASON_4_TARGETS:
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

    mp3_key = f"music/{ARTIST_NAME}/{ALBUM_NAME}/s_{sid}.mp3"
    print(f"[{t_idx}/12] ☁️ 上传音频至 R2: {mp3_key}")
    s3_client.upload_file(clean_audio, BUCKET_NAME, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})

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
print(f"\n⚡ 正在向 D1 提交第四季全量 12 首 batch-light 点亮...")
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
print("🔍 第四季 12 首生产环境 HTTP HEAD 1:1 强校验...")
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
    print("\n🎉《蒙面唱将猜猜猜》第四季 12 首全量 100% 满格点亮！")
else:
    print("\n⚠️ 存在未通过检验的曲目，需排查。")

