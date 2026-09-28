#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
动力火车《都是因为爱》(ID 345) 与《结伴》(ID 343) 正本清源治理与母带压制脚本
==============================================================================
"""

import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config

sys.path.append(os.path.join(os.path.dirname(__file__)))
from fetch_official_lyrics import fetch_clean_lrc

PROXY_URL = "http://127.0.0.1:7897"
NODE_PATH = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"
API_BASE = "https://m-api.changgepd.ccwu.cc"
ARTIST = "动力火车"
WORK_DIR = "/tmp/dongli_ai_jieban_work"
os.makedirs(WORK_DIR, exist_ok=True)

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

ALBUM_PLANS = [
    {
        "album_id": 345,
        "album_name": "都是因为爱",
        "tracks": [
            {"track": 1, "title": "I'll Be Back", "existing_id": 25749, "query": "g9rWdzNEDkA"},
            {"track": 2, "title": "我很好骗", "existing_id": 25750, "query": "3HsIaWuNeX0"},
            {"track": 3, "title": "救世主", "existing_id": 25751, "query": "-CLbnOCCExU"},
            {"track": 4, "title": "我陪你面对", "existing_id": 25752, "query": "tol9WYN2oQ4"},
            {"track": 5, "title": "远远的泪", "existing_id": 25753, "query": "IdfKY3OE3DE"},
            {"track": 6, "title": "不必说哈啰", "existing_id": 25754, "query": "6Xy8-A-aIyY"},
            {"track": 7, "title": "完美遗憾", "existing_id": 25755, "query": "9TNh-aqLLAQ"},
            {"track": 8, "title": "跳上车子离开伤心的台北", "existing_id": 25756, "query": "wcYstYvQGbU"},
            {"track": 9, "title": "谢谢别再联络", "existing_id": None, "query": "TS4kee1DY88"},
            {"track": 10, "title": "如果海能够", "existing_id": None, "query": "s9ju4E7JI4A"},
            {"track": 11, "title": "二月", "existing_id": None, "query": "gv5C9so3QaE"}
        ]
    },
    {
        "album_id": 343,
        "album_name": "结伴",
        "tracks": [
            {"track": 1, "title": "嗨歌万万岁", "existing_id": 25790, "query": "Fyuxj7vcOTI"},
            {"track": 2, "title": "俯冲的灵魂 (feat. 林俊杰)", "existing_id": 25791, "query": "8zeXS7s7jok"},
            {"track": 3, "title": "催眠", "existing_id": 25792, "query": "fmdyzjeRq14"},
            {"track": 4, "title": "趁少年 (feat. 玖壹壹)", "existing_id": 25793, "query": "Sj8vtJYlHOg"},
            {"track": 5, "title": "看着你看着他", "existing_id": 25794, "query": "df0DrUIKWAU"},
            {"track": 6, "title": "我不该哭 (feat. 告五人)", "existing_id": 25795, "query": "u67qCBLAIB4"},
            {"track": 7, "title": "摇滚区", "existing_id": 25796, "query": "Q1BdVtEk-Wc"},
            {"track": 8, "title": "到底我算什么 (feat. 麋先生)", "existing_id": 25797, "query": "zFqfYVSnwvM"},
            {"track": 9, "title": "你骂的都对", "existing_id": None, "query": "Zou7ugzTgbg"},
            {"track": 10, "title": "一直都在那里", "existing_id": None, "query": "6OO1vb_HLRA"}
        ]
    }
]

def remediate_single_album(plan):
    aid = plan["album_id"]
    aname = plan["album_name"]
    tracks = plan["tracks"]

    print("=" * 80, flush=True)
    print(f"🚀 开始治理专辑 [{aid}] 《{aname}》 共 {len(tracks)} 首曲目...", flush=True)
    print("=" * 80, flush=True)

    # 1. 结构检查与同步
    r = requests.get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}").json()
    curr_songs = r.get("data", {}).get("songs", [])
    curr_song_map = {s.get("title"): s for s in curr_songs}
    curr_id_map = {s.get("id"): s for s in curr_songs}

    # 更新现有曲目
    updates = []
    missing_tracks = []
    for t in tracks:
        if t["existing_id"] and t["existing_id"] in curr_id_map:
            updates.append({
                "id": t["existing_id"],
                "title": t["title"],
                "track_index": t["track"]
            })
        else:
            # 查看当前是否已有同名或未分配
            matching = curr_song_map.get(t["title"])
            if matching:
                t["existing_id"] = matching["id"]
                updates.append({
                    "id": matching["id"],
                    "title": t["title"],
                    "track_index": t["track"]
                })
            else:
                missing_tracks.append(t)

    if updates:
        res_up = requests.post(f"{API_BASE}/api/admin/songs/batch-update", json={"updates": updates}).json()
        print(f"   • batch-update 现有曲目响应: {res_up}", flush=True)

    if missing_tracks:
        ins_payload = {
            "album_id": aid,
            "songs": [{"title": mt["title"], "track_index": mt["track"]} for mt in missing_tracks]
        }
        res_ins = requests.post(f"{API_BASE}/api/admin/songs/batch-insert", json=ins_payload).json()
        print(f"   • batch-insert 缺失曲目响应: {res_ins}", flush=True)
        new_ids = res_ins.get("data", {}).get("song_ids", [])
        for mt, nid in zip(missing_tracks, new_ids):
            mt["existing_id"] = nid
            print(f"   • 已插入曲目 《{mt['title']}》 -> ID {nid}", flush=True)

    # 2. 采录、压制、正版歌词与上传
    d1_lights = []
    for idx, item in enumerate(tracks, 1):
        sid = item["existing_id"]
        tnum = item["track"]
        title = item["title"]
        query = item["query"]

        print(f"\n[{idx}/{len(tracks)}] 正在处理 [{aname}] Track {tnum:02d} ID {sid} 《{title}》...", flush=True)

        norm_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
        lrc_file = os.path.join(WORK_DIR, f"s_{sid}.lrc")
        out_tmpl = os.path.join(WORK_DIR, f"raw_{sid}.%(ext)s")

        for f_path in [norm_mp3, lrc_file]:
            if os.path.exists(f_path): os.remove(f_path)

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
            print(f"   ⚠️ 首选音源未命中，回退官方搜索: 動力火車 {title} 官方...", flush=True)
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

        # 清洗标题搜索歌词
        clean_tit_for_lrc = title.split("(")[0].split("（")[0].strip()
        lrc_text = fetch_clean_lrc(ARTIST, clean_tit_for_lrc)
        lrc_url = None
        if lrc_text:
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            sample_line = [l for l in lrc_text.split("\n") if l.strip() and not any(tag in l for tag in ['[ti:', '[ar:', '[al:', '[by:', '[offset:'])][:1]
            print(f"   📄 正版歌词获取完成: {sample_line[0] if sample_line else 'LRC已清洗'}", flush=True)

        mp3_key = f"music/{ARTIST}/{aname}/s_{sid}.mp3"
        s3_client.upload_file(norm_mp3, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        mp3_url = f"{public_base}/{mp3_key}"

        if os.path.exists(lrc_file):
            lrc_key = f"lyrics/{ARTIST}/{aname}/s_{sid}.lrc"
            s3_client.upload_file(lrc_file, bucket_name, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            lrc_url = f"{public_base}/{lrc_key}"

        print(f"   🚀 R2 上传完成: {mp3_url}", flush=True)

        d1_lights.append({
            "id": sid,
            "file_path": mp3_url,
            "lrc_path": lrc_url
        })

    if d1_lights:
        print("\n" + "=" * 80, flush=True)
        print(f"⚡ 正在向 D1 提交批量点亮 ({len(d1_lights)} 首)...", flush=True)
        light_res = requests.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": d1_lights}, timeout=20).json()
        print(f"   • batch-light 响应: {light_res}", flush=True)
        print("=" * 80, flush=True)

        print("\n🔍 生产可用性检验 (HEAD 请求)...", flush=True)
        for u in d1_lights:
            r_mp3 = requests.head(u["file_path"], timeout=10)
            r_lrc = requests.head(u["lrc_path"], timeout=10) if u.get("lrc_path") else None
            print(f"   • [{u['id']}] MP3: HTTP {r_mp3.status_code} ({r_mp3.headers.get('content-length')} bytes) | LRC: HTTP {r_lrc.status_code if r_lrc else 'None'}", flush=True)

    print(f"\n🎉 专辑 [{aid}] 《{aname}》 治理完成！\n", flush=True)

def main():
    for plan in ALBUM_PLANS:
        remediate_single_album(plan)

if __name__ == "__main__":
    main()
