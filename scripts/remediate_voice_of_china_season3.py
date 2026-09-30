#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《中国好声音》第三季 (Album 1943, 12首) 工业级全自动化高保真采录与全专点亮
"""
import os
import sys
import json
import time
import urllib.parse
import subprocess
import requests
import base64
import boto3
from botocore.config import Config

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/voice_of_china_s3_work"
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

# 第三季 12 首曲目配置: (sid, track_index, singer, song_name, yt_id, lrc_query)
SEASON_3_TASKS = [
    (27601, 1, "张碧晨", "她说", "co9vu09sIaY", "她说 张碧晨"),
    (27603, 2, "帕尔哈提", "你怎么舍得我难过", "hVC4ZOZUdZY", "你怎么舍得我难过 黄品源"),
    (27608, 3, "余枫", "有多少爱可以重来", "PMgLwRguPoI", "有多少爱可以重来 迪克牛仔"),
    (27605, 4, "秦宇子", "I Love Rock 'N Roll", "LQC8YfQJojM", "I Love Rock 'N Roll"),
    (27607, 5, "周深", "欢颜", "frFlekDE6ZA", "欢颜 周深"),
    (27602, 6, "陈冰", "盛夏光年", "MJI-_wlE9xw", "盛夏光年 五月天"),
    (27606, 7, "陈乐基", "月半小夜曲", "b5R-fBTaLhY", "月半小夜曲 李克勤"),
    (27604, 8, "刘明湘", "漂洋过海来看你", "cbT84M9GQ8A", "漂洋过海来看你 刘明湘"),
    (31132, 9, "李嘉格", "普通朋友", "utprmjLMt7Y", "普通朋友 陶喆"),
    (31133, 10, "耿斯汉", "美丽世界的孤儿", "OlKuM98aR08", "美丽世界的孤儿 汪峰"),
    (31134, 11, "魏雪漫", "我是真的爱你", "GVlD-k08HcY", "我是真的爱你 张信哲"),
    (31135, 12, "张心杰", "大惊小怪", "ule07AIgIjg", "大惊小怪 信乐团"),
]

def check_r2_object_size(key: str) -> int:
    try:
        res = s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
        return int(res.get("ContentLength", 0))
    except Exception:
        return 0

def fetch_clean_lrc(query: str) -> str:
    # 通道 1: 酷狗音乐搜索 + 下载
    try:
        r = session.get(f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={urllib.parse.quote(query)}&page=1&pagesize=2", headers=HEADERS, timeout=6).json()
        info_list = r.get("data", {}).get("info", [])
        if info_list:
            info = info_list[0]
            h = info["hash"]
            dur = info.get("duration", 0)
            lr = session.get(f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword={urllib.parse.quote(query)}&duration={dur}&hash={h}", headers=HEADERS, timeout=6).json()
            candidates = lr.get("candidates", [])
            if candidates:
                cid = candidates[0]["id"]
                ckey = candidates[0]["accesskey"]
                dl = session.get(f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cid}&accesskey={ckey}&fmt=lrc&charset=utf8", headers=HEADERS, timeout=6).json()
                b64_content = dl.get("content", "")
                if b64_content:
                    lrc_text = base64.b64decode(b64_content).decode("utf-8", errors="ignore")
                    if lrc_text and len(lrc_text.strip()) > 50:
                        clean_lines = [l for l in lrc_text.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:", "[total:"])]
                        return "\n".join(clean_lines).strip()
    except Exception as e:
        print(f"   ⚠️ 酷狗歌词通道异常: {e}")

    # 通道 2: 网易云原生接口
    try:
        r = session.get(f"https://music.163.com/api/search/get/web?s={urllib.parse.quote(query)}&type=1&limit=3", headers=HEADERS, timeout=6).json()
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
        print(f"   ⚠️ 网易云歌词通道异常: {e}")

    return ""

def main():
    album_id = 1943
    album_name = "第三季 (2014)"
    artist_name = "中国好声音"
    enc_artist = urllib.parse.quote(artist_name)
    enc_album = urllib.parse.quote(album_name)

    print("=" * 80)
    print(f"🚀 开始处理《中国好声音》{album_name} (共 {len(SEASON_3_TASKS)} 首)")
    print("=" * 80)

    for sid, t_idx, singer, song_name, yt_id, lrc_q in SEASON_3_TASKS:
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
    print("\n⚡ 提交第三季 12 首曲目生产端 batch-light...")
    updates = []
    for sid, t_idx, singer, song_name, yt_id, lrc_q in SEASON_3_TASKS:
        mp3_url = f"{PUBLIC_BASE}/music/{enc_artist}/{enc_album}/s_{sid}.mp3"
        lrc_url = f"{PUBLIC_BASE}/lyrics/{enc_artist}/{enc_album}/s_{sid}.lrc"
        updates.append({"id": sid, "file_path": mp3_url, "lrc_path": lrc_url})

    res_lit = session.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": updates}, timeout=25)
    print(f"   • batch-light 响应: {res_lit.status_code} | {res_lit.text}")

    # 6. 1:1 强校验
    print("\n" + "=" * 80)
    print("🔍 正在对第三季 12 首曲目发起生产端 1:1 物理字节审计...")
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
    if all_pass and len(final_songs) == 12:
        print("🎉 《中国好声音》第三季 12 首全专 100% 验收通过！")
    else:
        print(f"⚠️ 第三季验收未完全通过，状态={all_pass}, 曲目数={len(final_songs)}")

if __name__ == "__main__":
    main()
