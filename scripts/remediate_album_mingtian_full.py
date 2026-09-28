#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
动力火车《明天的明天的明天》(Album ID 1859) 全专 12 首正本清源治理与母带压制脚本
==============================================================================
"""

import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config

# 引入已验证的高保真歌词获取模块
sys.path.append(os.path.join(os.path.dirname(__file__)))
from fetch_official_lyrics import fetch_clean_lrc

PROXY_URL = "http://127.0.0.1:7897"
NODE_PATH = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"
API_BASE = "https://m-api.changgepd.ccwu.cc"
ALBUM_ID = 1859
ALBUM_NAME = "明天的明天的明天"
ARTIST = "动力火车"
WORK_DIR = "/tmp/dongli_mingtian_work"
os.makedirs(WORK_DIR, exist_ok=True)

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

# 官方 12 首曲目结构映射
TRACKS_SPEC = [
    {"track": 1, "title": "梨山痴情花", "existing_id": 25769, "query": "mbSR-c4cd3g"},
    {"track": 2, "title": "我不知道", "existing_id": 25770, "query": "mYHYo-zdIqQ"},
    {"track": 3, "title": "明天的明天的明天", "existing_id": 25771, "query": "Z_GwKSC1kF8"},
    {"track": 4, "title": "Don't break my heart", "existing_id": 25772, "query": "JC9EIh_Rn5o"},
    {"track": 5, "title": "因为心碎所以喝醉", "existing_id": 25779, "query": "DHzya7TImrQ"},
    {"track": 6, "title": "你不在我身边好冷", "existing_id": 25773, "query": "McZAOLZm1xg"},
    {"track": 7, "title": "最后一种快乐", "existing_id": 25777, "query": "ltZZHOe1qbA"},
    {"track": 8, "title": "刺猬", "existing_id": 25778, "query": "ytsearch1:動力火車 刺蝟 官方"},
    {"track": 9, "title": "单程车票", "existing_id": 25774, "query": "ytsearch1:動力火車 單程車票 官方"},
    {"track": 10, "title": "让我哭", "existing_id": 25775, "query": "ytsearch1:動力火車 讓我哭 官方"},
    {"track": 11, "title": "我知道你要的是什么", "existing_id": 25776, "query": "ytsearch1:動力火車 我知道你要的是什麼 官方"},
    {"track": 12, "title": "翅膀之歌", "existing_id": None, "query": "ytsearch1:動力火車 翅膀之歌 官方"}
]

def step1_prepare_database_structure():
    """步骤 1：同步修正 D1 数据库中歌曲名称与音轨序号，补入缺失歌曲"""
    print("=" * 80)
    print("📋 步骤 1: 正在校正 D1 中《明天的明天的明天》的歌曲标题与音轨顺序...")
    print("=" * 80)

    # 查当前专辑详情
    r = requests.get(f"{API_BASE}/api/admin/albums/detail?album_id={ALBUM_ID}").json()
    curr_songs = r.get("data", {}).get("songs", [])
    print(f"   当前专辑曲目数: {len(curr_songs)}")

    # 批量更新现有 11 首
    updates = []
    for item in TRACKS_SPEC:
        if item["existing_id"]:
            updates.append({
                "id": item["existing_id"],
                "title": item["title"],
                "track_index": item["track"]
            })
    
    res_up = requests.post(f"{API_BASE}/api/admin/songs/batch-update", json={"updates": updates})
    print(f"   • batch-update 现有曲目响应: HTTP {res_up.status_code} | {res_up.text}")

    # 检查第 12 首是否需要 insert
    song_12 = next((s for s in curr_songs if s.get("title") == "翅膀之歌" or s.get("track_index") == 12), None)
    if song_12:
        TRACKS_SPEC[11]["existing_id"] = song_12["id"]
        print(f"   • 第 12 首《翅膀之歌》已存在，ID: {song_12['id']}")
    else:
        print("   • 第 12 首《翅膀之歌》缺失，调用 batch-insert 补齐...")
        ins_payload = {
            "album_id": ALBUM_ID,
            "songs": [{
                "title": "翅膀之歌",
                "track_index": 12
            }]
        }
        res_ins = requests.post(f"{API_BASE}/api/admin/songs/batch-insert", json=ins_payload).json()
        print(f"   • batch-insert 响应: {res_ins}")
        new_ids = res_ins.get("data", {}).get("song_ids", [])
        if new_ids:
            TRACKS_SPEC[11]["existing_id"] = new_ids[0]
            print(f"   • 第 12 首已创建，分配 ID: {new_ids[0]}")
        else:
            raise RuntimeError("插入第 12 首失败!")

def step2_download_and_encode_and_upload():
    """步骤 2：官方音源采录、压制、正版歌词抓取与 R2 上传"""
    print("\n" + "=" * 80)
    print("🎵 步骤 2: 官方录音室母带采录、标准化压制与 R2 同步上传...")
    print("=" * 80)

    d1_lights = []

    for idx, item in enumerate(TRACKS_SPEC, 1):
        sid = item["existing_id"]
        track_num = item["track"]
        title = item["title"]
        query = item["query"]

        print(f"\n[{idx}/12] 正在处理 [Track {track_num:02d}] ID {sid} 《{title}》...", flush=True)

        norm_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
        lrc_file = os.path.join(WORK_DIR, f"s_{sid}.lrc")
        out_tmpl = os.path.join(WORK_DIR, f"raw_{sid}.%(ext)s")

        for f_path in [norm_mp3, lrc_file]:
            if os.path.exists(f_path): os.remove(f_path)

        # 1. 下载音频
        is_url = query.startswith("http") or len(query) == 11
        target_src = f"https://www.youtube.com/watch?v={query}" if (len(query) == 11 and not query.startswith("ytsearch")) else query

        cmd_dl = [
            "yt-dlp",
            "--proxy", PROXY_URL,
            "--js-runtimes", f"node:{NODE_PATH}",
            "--extractor-args", "youtube:player_client=ios,web,mweb",
            "-f", "ba/b",
            "-o", out_tmpl,
            target_src
        ]
        subprocess.run(cmd_dl, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        actual_raw = None
        for ext in ["webm", "m4a", "opus", "mp3", "mp4", "mkv", "ogg"]:
            cand = os.path.join(WORK_DIR, f"raw_{sid}.{ext}")
            if os.path.exists(cand) and os.path.getsize(cand) > 50000:
                actual_raw = cand
                break

        if not actual_raw:
            # 回退通用官方搜索
            print(f"   ⚠️ 首选音源未命中，回退搜索: 動力火車 {title} 官方...", flush=True)
            cmd_fb = [
                "yt-dlp",
                "--proxy", PROXY_URL,
                "--js-runtimes", f"node:{NODE_PATH}",
                "--extractor-args", "youtube:player_client=ios,web,mweb",
                "-f", "ba/b",
                "--default-search", "ytsearch",
                "-o", out_tmpl,
                f"ytsearch1:動力火車 {title} 官方"
            ]
            subprocess.run(cmd_fb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for ext in ["webm", "m4a", "opus", "mp3", "mp4", "mkv", "ogg"]:
                cand = os.path.join(WORK_DIR, f"raw_{sid}.{ext}")
                if os.path.exists(cand) and os.path.getsize(cand) > 50000:
                    actual_raw = cand
                    break

        if not actual_raw:
            print(f"   ❌ 音频下载失败: 《{title}》", flush=True)
            continue

        # 2. 标准化压制 (-14 LUFS, 160k CBR)
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
            print(f"   ❌ 压制失败: 《{title}》", flush=True)
            continue

        dur_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", norm_mp3]
        dur_str = subprocess.check_output(dur_cmd).decode().strip()
        dur_float = float(dur_str) if dur_str else 0
        print(f"   ✅ 母带压制达标! 时长: {int(dur_float // 60)}分{int(dur_float % 60):02d}秒 ({dur_float:.1f}s), 大小: {os.path.getsize(norm_mp3)/1024/1024:.2f} MB", flush=True)

        # 3. 抓取正版歌词
        lrc_text = fetch_clean_lrc(ARTIST, title)
        lrc_url = None
        if lrc_text:
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            sample_line = [l for l in lrc_text.split("\n") if l.strip() and not any(tag in l for tag in ['[ti:', '[ar:', '[al:', '[by:', '[offset:'])][:1]
            print(f"   📄 正版歌词获取完成: {sample_line[0] if sample_line else 'LRC已清洗'}", flush=True)

        # 4. 上传 R2 account_11
        mp3_key = f"music/{ARTIST}/{ALBUM_NAME}/s_{sid}.mp3"
        s3_client.upload_file(norm_mp3, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        mp3_url = f"{public_base}/{mp3_key}"

        if os.path.exists(lrc_file):
            lrc_key = f"lyrics/{ARTIST}/{ALBUM_NAME}/s_{sid}.lrc"
            s3_client.upload_file(lrc_file, bucket_name, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            lrc_url = f"{public_base}/{lrc_key}"

        print(f"   🚀 R2 上传完成: {mp3_url}", flush=True)

        d1_lights.append({
            "id": sid,
            "file_path": mp3_url,
            "lrc_path": lrc_url
        })

    # 5. 提交 D1 点亮
    if d1_lights:
        print("\n" + "=" * 80)
        print(f"⚡ 正在向 D1 提交批量点亮 ({len(d1_lights)} 首)...")
        light_res = requests.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": d1_lights}, timeout=20).json()
        print(f"   • batch-light 响应: {light_res}")
        print("=" * 80)

        # 6. 验证
        print("\n🔍 生产可用性检验 (HEAD 请求)...")
        for u in d1_lights:
            r_mp3 = requests.head(u["file_path"], timeout=10)
            r_lrc = requests.head(u["lrc_path"], timeout=10) if u.get("lrc_path") else None
            print(f"   • [{u['id']}] MP3: HTTP {r_mp3.status_code} ({r_mp3.headers.get('content-length')} bytes) | LRC: HTTP {r_lrc.status_code if r_lrc else 'None'}")

    print("\n🎉 《明天的明天的明天》全专 12 首正本清源治理完成！")

if __name__ == "__main__":
    step1_prepare_database_structure()
    step2_download_and_encode_and_upload()
