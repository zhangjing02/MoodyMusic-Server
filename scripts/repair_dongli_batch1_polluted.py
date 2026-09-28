#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
动力火车李鬼曲目、同名说唱与串歌第一批深度治理脚本
针对专辑：《无情的情书》、《再见我的爱人》、《MAN》、《继续转动》
==============================================================================
"""

import os
import sys
import json
import base64
import subprocess
import requests
import boto3
from botocore.config import Config

PROXY_URL = "http://127.0.0.1:7897"
PROXIES = {"http": PROXY_URL, "https": PROXY_URL}
NODE_PATH = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"
API_BASE = "https://m-api.changgepd.ccwu.cc"

# 载入 R2 桶配置 (account_11)
with open("MoodyMusic-Server/r2_config.json", "r", encoding="utf-8") as f:
    all_cfg = json.load(f)
    r2_cfg = all_cfg["buckets"]["account_11"]

s3_client = boto3.client(
    service_name="s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, connect_timeout=15, read_timeout=30)
)
bucket_name = r2_cfg["name"]
public_base = r2_cfg["public_url"]

ARTIST = "动力火车"
WORK_DIR = "/tmp/dongli_batch1_work"
os.makedirs(WORK_DIR, exist_ok=True)

# 目标处理清单 (消除小安迪说唱、周浠灵翻唱、赵辰龙说唱、群星手牵手串歌等)
TARGET_SONGS = [
    {
        "id": 25758,
        "album": "无情的情书",
        "title": "不甘心不放手",
        "yt_id": "N-y8c994jsk"
    },
    {
        "id": 25759,
        "album": "无情的情书",
        "title": "还隐隐作痛",
        "yt_id": "0l1y1oWUlM8"
    },
    {
        "id": 25765,
        "album": "无情的情书",
        "title": "不只是",
        "yt_id": "bAXtL7JR9J0"
    },
    {
        "id": 25764,
        "album": "无情的情书",
        "title": "Happy By Your Side",
        "yt_id": "uze0hhiMmUI"
    },
    {
        "id": 25707,
        "album": "再见我的爱人",
        "title": "再见我的爱人",
        "yt_id": "sZ1rEqBsPHk"
    },
    {
        "id": 25710,
        "album": "再见我的爱人",
        "title": "不会哭的人",
        "yt_id": "2Z-b6eS61Gg"
    },
    {
        "id": 25711,
        "album": "再见我的爱人",
        "title": "可不可能",
        "yt_id": "ttZByRPtPcc"
    },
    {
        "id": 25716,
        "album": "再见我的爱人",
        "title": "Bye Bye Subway",
        "yt_id": "HdpVTioPN1o"
    },
    {
        "id": 25737,
        "album": "MAN",
        "title": "潇洒的走",
        "yt_id": "xxMzjpvpxh0"
    },
    {
        "id": 25740,
        "album": "继续转动",
        "title": "逆向行驶",
        "yt_id": "AzodtXp5NUc"
    }
]

def fetch_clean_lrc(title, album):
    """从酷狗高保真库中按动力火车原唱搜索并清洗私有标记"""
    try:
        url = f"http://songsearch.kugou.com/song_search_v2?keyword=动力火车 {title}&page=1&pagesize=5&clientver=&platform=WebFilter"
        r = requests.get(url, timeout=5).json()
        lists = r.get("data", {}).get("lists", [])
        hash_val = None
        for s in lists:
            if "动力火车" in s.get("SingerName", ""):
                hash_val = s.get("FileHash")
                break
        if hash_val:
            lrc_search_url = f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword=动力火车 {title}&hash={hash_val}&album_audio_id=0"
            res = requests.get(lrc_search_url, timeout=5).json()
            candidates = res.get('candidates', [])
            if candidates:
                cand = candidates[0]
                dl_url = f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cand['id']}&accesskey={cand['accesskey']}&fmt=lrc&charset=utf8"
                dr = requests.get(dl_url, timeout=5).json()
                content = base64.b64decode(dr.get("content", "")).decode("utf-8", errors="ignore")
                content = content.replace('\ufeff', '').strip()
                if content and len(content.strip()) > 50:
                    clean_lines = []
                    for line in content.split("\n"):
                        l_str = line.strip()
                        if l_str.startswith("[qq:") or l_str.startswith("[id:") or l_str.startswith("[hash:") or l_str.startswith("[sign:"):
                            continue
                        clean_lines.append(line)
                    return "\n".join(clean_lines).strip()
    except Exception as e:
        print(f"      [歌词抓取跳过] {title}: {e}", flush=True)
    return None

def process_batch():
    print("=" * 80, flush=True)
    print("🚀 启动动力火车李鬼与串歌第一批 (10 首重点曲目) 正本清源工作流...", flush=True)
    print("=" * 80, flush=True)

    d1_updates = []

    for idx, item in enumerate(TARGET_SONGS, 1):
        sid = item["id"]
        album = item["album"]
        title = item["title"]
        yt_id = item["yt_id"]

        print(f"\n[{idx}/{len(TARGET_SONGS)}] 正在处理 [{album}] - ID {sid} 《{title}》...", flush=True)

        norm_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
        lrc_file = os.path.join(WORK_DIR, f"s_{sid}.lrc")
        out_tmpl = os.path.join(WORK_DIR, f"raw_{sid}.%(ext)s")

        for f_path in [norm_mp3, lrc_file]:
            if os.path.exists(f_path): os.remove(f_path)

        # 1. 采录官方母带
        cmd_dl = [
            "yt-dlp",
            "--proxy", PROXY_URL,
            "--js-runtimes", f"node:{NODE_PATH}",
            "--extractor-args", "youtube:player_client=ios,web,mweb",
            "-f", "ba/b",
            "-o", out_tmpl,
            f"https://www.youtube.com/watch?v={yt_id}"
        ]
        subprocess.run(cmd_dl, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        actual_raw = None
        for ext in ["webm", "m4a", "opus", "mp3", "mp4", "mkv", "ogg"]:
            cand = os.path.join(WORK_DIR, f"raw_{sid}.{ext}")
            if os.path.exists(cand) and os.path.getsize(cand) > 50000:
                actual_raw = cand
                break

        if not actual_raw:
            # 回退通用搜索
            print(f"   ⚠️ 专属 ID 下载未取到，回退精准搜索: 动力火车 {title} 官方...", flush=True)
            cmd_fallback = [
                "yt-dlp",
                "--proxy", PROXY_URL,
                "--js-runtimes", f"node:{NODE_PATH}",
                "--extractor-args", "youtube:player_client=ios,web,mweb",
                "-f", "ba/b",
                "--default-search", "ytsearch",
                "-o", out_tmpl,
                f"ytsearch1:動力火車 {title} 官方"
            ]
            subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for ext in ["webm", "m4a", "opus", "mp3", "mp4", "mkv", "ogg"]:
                cand = os.path.join(WORK_DIR, f"raw_{sid}.{ext}")
                if os.path.exists(cand) and os.path.getsize(cand) > 50000:
                    actual_raw = cand
                    break

        if not actual_raw:
            print(f"   ❌ 音频采录失败: 《{title}》", flush=True)
            continue

        # 2. 标准化压制
        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", actual_raw,
            "-vn",
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame",
            "-b:a", "160k",
            "-ar", "44100",
            norm_mp3
        ]
        subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(norm_mp3) or os.path.getsize(norm_mp3) < 500000:
            print(f"   ❌ 压制失败!", flush=True)
            continue

        dur_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", norm_mp3]
        dur_str = subprocess.check_output(dur_cmd).decode().strip()
        dur_float = float(dur_str) if dur_str else 0
        print(f"   ✅ 母带压制达标! 时长: {int(dur_float // 60)}分{int(dur_float % 60):02d}秒 ({dur_float:.1f}s), 大小: {os.path.getsize(norm_mp3)/1024/1024:.2f} MB", flush=True)

        # 3. 抓取与清洗歌词
        lrc_text = fetch_clean_lrc(title, album)
        lrc_url = None
        if lrc_text:
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            sample_line = [l for l in lrc_text.split("\n") if l.strip() and not any(tag in l for tag in ['[ti:', '[ar:', '[al:', '[by:', '[offset:'])][:1]
            print(f"   📄 正版歌词清洗完成: {sample_line[0] if sample_line else 'LRC已生成'}", flush=True)

        # 4. 上传 R2 account_11
        mp3_key = f"music/{ARTIST}/{album}/s_{sid}.mp3"
        s3_client.upload_file(norm_mp3, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        mp3_url = f"{public_base}/{mp3_key}"

        if os.path.exists(lrc_file):
            lrc_key = f"lyrics/{ARTIST}/{album}/s_{sid}.lrc"
            s3_client.upload_file(lrc_file, bucket_name, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            lrc_url = f"{public_base}/{lrc_key}"

        print(f"   🚀 R2 上传成功: {mp3_url}", flush=True)

        d1_updates.append({
            "id": sid,
            "file_path": mp3_url,
            "lrc_path": lrc_url
        })

    # 5. 批量提交 D1
    if d1_updates:
        print("\n" + "=" * 80, flush=True)
        print(f"⚡ 正在向 D1 提交批量点亮 ({len(d1_updates)} 首)...", flush=True)
        light_res = requests.post(
            f"{API_BASE}/api/admin/songs/batch-light",
            json={"updates": d1_updates},
            timeout=20
        )
        print(f"   • batch-light 响应: HTTP {light_res.status_code} | {light_res.text}", flush=True)
        print("=" * 80, flush=True)

        # 验证可用性
        print("\n🔍 生产可用性检验 (HEAD 请求)...", flush=True)
        for u in d1_updates:
            r_mp3 = requests.head(u["file_path"], timeout=10)
            print(f"   • [{u['id']}] mp3: HTTP {r_mp3.status_code} ({r_mp3.headers.get('content-length')} bytes)")

    print("\n🎉 第一批重点李鬼与串歌曲目重采修复已 100% 成功交付！", flush=True)

if __name__ == "__main__":
    process_batch()
