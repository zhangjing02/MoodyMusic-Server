#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《中国好声音》第一季 (Album 1941, 16首) 工业级全自动化高保真采录与全专点亮
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

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/voice_of_china_s1_work"
os.makedirs(WORK_DIR, exist_ok=True)

NODE_PATH = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"
PROXY_URL = "http://127.0.0.1:7897"
API_BASE = "https://m-api.changgepd.ccwu.cc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

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

session = requests.Session()
session.trust_env = False

# 第一季 16 首曲目配置: (sid, track_index, singer, song_name, yt_id, lrc_query)
SEASON_1_TASKS = [
    (27591, 1, "梁博", "长安 长安", "Desjd6ZOx4Q", "梁博 长安长安"),
    (27586, 2, "吴莫愁", "Price Tag", "7VWk6REyF8A", "吴莫愁 Price Tag"),
    (31121, 3, "吉克隽逸", "i feel good", "2mGYyJ40Fb8", "吉克隽逸 I Feel Good"),
    (27588, 4, "金志文", "为爱痴狂", "13flRz7fho8", "金志文 为爱痴狂"),
    (27585, 5, "李代沫", "我的歌声里", "6gJPwdnUeP4", "李代沫 我的歌声里"),
    (27583, 6, "张玮", "High歌", "NQjJUwUAwI0", "张玮 High歌"),
    (31122, 7, "丁丁", "爱要坦荡荡", "4hwlxqMgMnI", "丁丁 爱要坦荡荡"),
    (27592, 8, "平安", "我爱你中国", "coTrfiEYpmE", "平安 我爱你中国"),
    (27590, 9, "多亮", "小情歌", "wtkASuGru9o", "多亮 小情歌"),
    (27593, 10, "张赫宣", "你是我心爱的姑娘", "x7CM47nL83s", "张赫宣 你是我心爱的姑娘"),
    (31123, 11, "关喆", "领悟", "d-Cn8ubzW5M", "关喆 领悟"),
    (27587, 12, "袁娅维", "弯弯的月亮", "E55dLUqBcLA", "弯弯的月亮 刘欢"),
    (31124, 13, "王韵壹", "被遗忘的时光", "YDyxFxJ-jVs", "被遗忘的时光 蔡琴"),
    (27584, 14, "徐海星", "自己", "aF29IyQQ1eU", "李玟 自己"),
    (27589, 15, "郑虹", "Someone Like You", "3oGY5jcodlM", "郑虹 Someone Like You"),
    (31125, 16, "金池", "夜夜夜夜", "Ofr4aRMAPRk", "金池 夜夜夜夜"),
]

def check_r2_object_size(key: str) -> int:
    try:
        res = s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
        return int(res.get("ContentLength", 0))
    except Exception:
        return 0

def fetch_clean_lrc(query: str) -> str:
    try:
        r = session.get(f"https://music.163.com/api/search/get/web?s={query}&type=1&limit=3", headers=HEADERS, timeout=6).json()
        songs = r.get("result", {}).get("songs", [])
        if songs:
            for s in songs:
                sid = s["id"]
                lr = session.get(f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1", headers=HEADERS, timeout=6).json()
                lrc_text = lr.get("lrc", {}).get("lyric", "")
                if lrc_text and len(lrc_text.strip()) > 50:
                    clean_lines = [l for l in lrc_text.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
                    return "\n".join(clean_lines).strip()
    except Exception as e:
        print(f"   ⚠️ 歌词抓取网络异常: {e}")
    return ""

def main():
    album_id = 1941
    album_name = "第一季 (2012)"
    artist_name = "中国好声音"
    enc_artist = urllib.parse.quote(artist_name)
    enc_album = urllib.parse.quote(album_name)

    print("=" * 80)
    print(f"🚀 开始处理《中国好声音》{album_name} (共 {len(SEASON_1_TASKS)} 首)")
    print("=" * 80)

    for sid, t_idx, singer, song_name, yt_id, lrc_q in SEASON_1_TASKS:
        mp3_key = f"music/{artist_name}/{album_name}/s_{sid}.mp3"
        lrc_key = f"lyrics/{artist_name}/{album_name}/s_{sid}.lrc"

        existing_mp3_size = check_r2_object_size(mp3_key)
        if existing_mp3_size > 500000:
            print(f"⏩ Track {t_idx:02d} | [{sid}] {song_name} - {singer} 音频已存在 ({existing_mp3_size/1024/1024:.2f}MB)，跳过下载压制")
        else:
            print(f"▶ Track {t_idx:02d} | [{sid}] 正在采录压制: {song_name} - {singer} (YT: {yt_id})...")
            raw_path = f"{WORK_DIR}/raw_{sid}.webm"
            norm_mp3 = f"{WORK_DIR}/s_{sid}.mp3"

            # 1. 下载
            cmd_dl = [
                "yt-dlp", "--proxy", PROXY_URL,
                "--js-runtimes", f"node:{NODE_PATH}",
                "-f", "ba/b",
                "-o", raw_path,
                f"https://www.youtube.com/watch?v={yt_id}"
            ]
            subprocess.run(cmd_dl, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if not os.path.exists(raw_path) or os.path.getsize(raw_path) < 100000:
                print(f"   ⚠️ 首选音源下载不满足条件，重试下载...")
                subprocess.run(cmd_dl, check=True)

            # 2. FFmpeg 压制
            subprocess.run([
                "ffmpeg", "-y", "-i", raw_path,
                "-vn", "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
                "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1", "-ar", "44100",
                norm_mp3
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            # 3. 上传 R2
            s3_client.upload_file(norm_mp3, BUCKET_NAME, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
            uploaded_size = check_r2_object_size(mp3_key)
            print(f"   ✅ 音频上传成功: {mp3_key} ({uploaded_size/1024/1024:.2f}MB)")

        # 4. LRC 处理
        existing_lrc_size = check_r2_object_size(lrc_key)
        if existing_lrc_size > 200:
            print(f"   📄 LRC 已存在 ({existing_lrc_size}B)，跳过抓取")
        else:
            lrc_content = fetch_clean_lrc(lrc_q)
            if lrc_content:
                s3_client.put_object(
                    Bucket=BUCKET_NAME,
                    Key=lrc_key,
                    Body=lrc_content.encode("utf-8"),
                    ContentType="text/plain; charset=utf-8"
                )
                print(f"   📄 LRC 上传成功: {lrc_key} ({len(lrc_content)}B)")
            else:
                print(f"   ⚠️ 警告: 未获取到 LRC: {lrc_q}")

    # 5. 提交批量点亮
    print("\n⚡ 提交第一季 16 首曲目生产端 batch-light...")
    updates = []
    for sid, t_idx, singer, song_name, yt_id, lrc_q in SEASON_1_TASKS:
        mp3_url = f"{PUBLIC_BASE}/music/{enc_artist}/{enc_album}/s_{sid}.mp3"
        lrc_url = f"{PUBLIC_BASE}/lyrics/{enc_artist}/{enc_album}/s_{sid}.lrc"
        updates.append({"id": sid, "file_path": mp3_url, "lrc_path": lrc_url})

    res_lit = session.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": updates}, timeout=25)
    print(f"   • batch-light 响应: {res_lit.status_code} | {res_lit.text}")

    # 6. 1:1 强校验
    print("\n" + "=" * 80)
    print("🔍 正在对第一季 16 首曲目发起生产端 1:1 物理字节审计...")
    print("=" * 80)
    final_detail = session.get(f"{API_BASE}/api/admin/albums/detail?album_id={album_id}", timeout=15).json()
    final_songs = final_detail.get("data", {}).get("songs", [])

    all_pass = True
    for s in sorted(final_songs, key=lambda x: x["track_index"]):
        sid = s["id"]
        title = s["title"]
        t_idx = s["track_index"]
        fpath = s.get("file_path")
        lpath = s.get("lrc_path")

        mp3_ok, mp3_size = False, 0
        if fpath:
            try:
                hr = session.head(fpath, headers=HEADERS, timeout=8)
                if hr.status_code == 200:
                    mp3_ok = True
                    mp3_size = int(hr.headers.get("Content-Length", 0))
            except Exception:
                pass

        lrc_ok, lrc_size = False, 0
        if lpath:
            try:
                lr = session.head(lpath, headers=HEADERS, timeout=8)
                if lr.status_code == 200:
                    lrc_ok = True
                    lrc_size = int(lr.headers.get("Content-Length", 0))
            except Exception:
                pass

        status_str = "✅ PASS" if (mp3_ok and mp3_size > 500000 and lrc_ok and lrc_size > 200) else "❌ FAIL"
        if "FAIL" in status_str:
            all_pass = False

        print(f"Track {t_idx:02d} | [{sid}] {title:<30} | {status_str} | MP3: {mp3_size/1024/1024:.2f}MB | LRC: {lrc_size}B")

    print("=" * 80)
    if all_pass and len(final_songs) == 16:
        print("🎉 《中国好声音》第一季 16 首全专 100% 验收通过！")
    else:
        print(f"⚠️ 第一季验收未完全通过，状态={all_pass}, 曲目数={len(final_songs)}")

if __name__ == "__main__":
    main()
