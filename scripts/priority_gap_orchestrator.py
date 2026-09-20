#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 严重缺失歌手（飞儿乐团、那英、古巨基）短板专项补齐调度引擎
==================================================================
特性与安全边界：
1. 目标写入桶：主力锁定全新的【account_08】（当前 0.937 GB，上限 9.00 GB 安全线）。
2. 家里电脑防并发冲突：单曲下载前实时对 D1 探活，若远端已点亮自动跳过。
3. 智能本地代理探测：自动识别 7897 / 7890 端口，保障母带与 LRC 秒级拉取。
4. 官方录音室 Topic 母带优先，过滤 Live/翻唱/对白。
5. 同步滚动时间轴 LRC 歌词挖掘并上传。
6. D1 批量即时点亮（每 10 首批量提交一次）。
"""

import os
import sys
import json
import time
import re
import argparse
import subprocess
import requests
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from syncedlyrics import search as search_lrc

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS_FILE = os.path.join(BASE_DIR, "scripts", "configs", "priority_missing_targets.json")
R2_CONFIG_FILE = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/moody_priority_gap_workspace"
os.makedirs(WORK_DIR, exist_ok=True)

API_BASE = "https://m-api.changgepd.ccwu.cc"

def get_local_proxy() -> str:
    for port in [7897, 7890, 10808, 10809]:
        try:
            r = requests.get("https://www.google.com", proxies={"https": f"http://127.0.0.1:{port}"}, timeout=1.5)
            if r.status_code == 200:
                return f"http://127.0.0.1:{port}"
        except Exception:
            pass
    return "http://127.0.0.1:7897"

PROXY = get_local_proxy()
PROXIES = {"http": PROXY, "https": PROXY}

BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    '官方完整版mv', 'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮', 'teaser'
]

with open(R2_CONFIG_FILE, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)

buckets_cfg = r2_cfg["buckets"]
account_08 = buckets_cfg["account_08"]

s3_clients = {}
def get_s3_client(bucket_id: str):
    if bucket_id not in s3_clients:
        b = buckets_cfg[bucket_id]
        s3_clients[bucket_id] = boto3.client(
            "s3",
            endpoint_url=b["endpoint_url"],
            aws_access_key_id=b["access_key_id"],
            aws_secret_access_key=b["secret_access_key"],
            region_name="auto"
        )
    return s3_clients[bucket_id]

# 容量跟踪与安全锁 (主力锁定 account_08)
capacity_lock = Lock()
CURRENT_BUCKET_ID = "account_08"
MAX_SAFE_BYTES = int(9.00 * 1024 * 1024 * 1024) # 9.00 GB 安全熔断线
CURRENT_BUCKET_BYTES = 0

def get_bucket_size_bytes(bucket_id: str) -> int:
    client = get_s3_client(bucket_id)
    bucket_name = buckets_cfg[bucket_id]["name"]
    paginator = client.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get("Contents", []):
            total += obj["Size"]
    return total

def init_capacity_tracker():
    global CURRENT_BUCKET_BYTES
    with capacity_lock:
        CURRENT_BUCKET_BYTES = get_bucket_size_bytes(CURRENT_BUCKET_ID)

def ensure_safe_bucket(added_bytes: int = 0) -> str:
    global CURRENT_BUCKET_ID, CURRENT_BUCKET_BYTES
    with capacity_lock:
        CURRENT_BUCKET_BYTES += added_bytes
        if CURRENT_BUCKET_BYTES >= MAX_SAFE_BYTES:
            print(f"\n🚨 [CAPACITY WARNING] account_08 达到 9.00 GB 安全预警线！已暂停额外写入！\n")
        return CURRENT_BUCKET_ID

def check_d1_already_lit(album_id: int, song_id: int) -> bool:
    try:
        r = requests.get(f"{API_BASE}/api/admin/albums/detail", params={"album_id": album_id}, timeout=10)
        if r.ok:
            songs = r.json().get('data', {}).get('songs', [])
            for s in songs:
                if s["id"] == song_id:
                    return bool(s.get("file_path"))
    except Exception:
        pass
    return False

ARTIST_ALIASES = {
    "邓丽君": ["邓丽君", "鄧麗君", "Teresa Teng", "テレサ・テン"],
    "飞儿乐团": ["飞儿乐团", "F.I.R.", "飛兒樂團"],
    "那英": ["那英", "Na Ying"],
    "古巨基": ["古巨基", "Leo Ku"],
    "张雨生": ["张雨生", "張雨生", "Tom Chang"],
    "动力火车": ["动力火车", "動力火車", "Power Station"],
    "张靓颖": ["张靓颖", "張靚穎", "Jane Zhang"],
    "戴佩妮": ["戴佩妮", "Penny Tai"],
    "汪峰": ["汪峰", "Wang Feng"],
    "陈粒": ["陈粒", "Chen Li"],
    "李圣杰": ["李圣杰", "李聖傑", "Sam Lee"],
    "周华健": ["周华健", "周華健", "Wakin Chau", "Emil Chau"],
    "苏打绿": ["苏打绿", "蘇打綠", "Sodagreen", "鱼丁糸", "魚丁糸"],
    "Beyond": ["Beyond", "黄家驹", "黃家駒"],
    "张信哲": ["张信哲", "張信哲", "Jeff Chang"],
    "张惠妹": ["张惠妹", "張惠妹", "A-Mei", "阿妹", "AMIT"],
    "梁静茹": ["梁静茹", "梁靜茹", "Fish Leong"],
}

def clean_song_title(title: str) -> str:
    cleaned = re.sub(r'[\(（].*?[\)）]', '', title).strip()
    return cleaned if cleaned else title

def search_and_download_audio(artist: str, album: str, title: str, out_path: str) -> bool:
    aliases = ARTIST_ALIASES.get(artist, [artist])
    cleaned_title = clean_song_title(title)
    
    queries = []
    # 1. 优先别名 + Topic 组合
    for a_name in aliases[:2]:
        queries.append(f"{a_name} - Topic {cleaned_title}")
        queries.append(f"{a_name} {cleaned_title} Topic")
    # 2. 官方频道或通用检索
    queries.append(f"{aliases[0]} {cleaned_title}")
    if cleaned_title != title:
        queries.append(f"{aliases[0]} {title}")
    if len(aliases) > 1:
        queries.append(f"{aliases[1]} {cleaned_title}")
    
    for q in queries:
        cmd_search = [
            "yt-dlp", "--proxy", PROXY,
            "--flat-playlist", "--no-warnings",
            "--print", "%(id)s | %(channel)s | %(title)s | %(duration)s",
            f"ytsearch8:{q}"
        ]
        try:
            res = subprocess.run(cmd_search, capture_output=True, text=True, timeout=25)
            lines = [l.strip() for l in res.stdout.split("\n") if l.strip()]
            best_id = None
            
            # 第一优先级: Topic 官方母带频道
            for l in lines:
                parts = l.split(" | ")
                if len(parts) >= 3:
                    vid, channel, vtitle = parts[0], parts[1], parts[2]
                    if any(kw in vtitle.lower() for kw in BLACK_KEYWORDS):
                        continue
                    if "topic" in channel.lower():
                        best_id = vid
                        break
            
            # 第二优先级: 歌手认证/官方唱片频道 (简繁及外文别名匹配)
            if not best_id:
                for l in lines:
                    parts = l.split(" | ")
                    if len(parts) >= 3:
                        vid, channel, vtitle = parts[0], parts[1], parts[2]
                        if any(kw in vtitle.lower() for kw in BLACK_KEYWORDS):
                            continue
                        ch_lower = channel.lower()
                        if any(alias.lower() in ch_lower for alias in aliases) or any(rec in ch_lower for rec in ["warner", "universal", "polydor", "rock records", "滾石", "環球", "华纳", "宝丽金", "eeg"]):
                            best_id = vid
                            break
                            
            # 第三优先级: 标题吻合且时长合理
            if not best_id:
                for l in lines:
                    parts = l.split(" | ")
                    if len(parts) >= 3:
                        vid, channel, vtitle = parts[0], parts[1], parts[2]
                        if any(kw in vtitle.lower() for kw in BLACK_KEYWORDS):
                            continue
                        try:
                            dur_str = parts[3]
                            if dur_str and dur_str != "NA":
                                dur_sec = float(dur_str)
                                if 120 <= dur_sec <= 450:
                                    best_id = vid
                                    break
                        except Exception:
                            best_id = vid
                            break
                            
            if best_id:
                temp_raw = f"{out_path}.raw"
                cmd_dl = [
                    "yt-dlp", "--proxy", PROXY,
                    "-x", "--audio-format", "mp3",
                    "--audio-quality", "0",
                    "-o", f"{temp_raw}.%(ext)s",
                    f"https://www.youtube.com/watch?v={best_id}"
                ]
                subprocess.run(cmd_dl, capture_output=True, text=True, timeout=90)
                
                raw_file = None
                for ext in ["mp3", "m4a", "webm", "opus", "mp4", "mkv"]:
                    candidate = f"{temp_raw}.{ext}"
                    if os.path.exists(candidate) and os.path.getsize(candidate) > 50 * 1024:
                        raw_file = candidate
                        break
                        
                if raw_file:
                    cmd_ffmpeg = [
                        "ffmpeg", "-y", "-i", raw_file,
                        "-vn",
                        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
                        "-c:a", "libmp3lame",
                        "-b:a", "192k",
                        "-ar", "44100",
                        "-id3v2_version", "3",
                        "-metadata", f"title={title}",
                        "-metadata", f"artist={artist}",
                        "-metadata", f"album={album}",
                        out_path
                    ]
                    subprocess.run(cmd_ffmpeg, capture_output=True, timeout=40)
                    
                    for ext in ["mp3", "m4a", "webm", "opus", "mp4", "mkv", "raw"]:
                        c_file = f"{temp_raw}.{ext}"
                        if os.path.exists(c_file):
                            try: os.remove(c_file)
                            except: pass
                            
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 100 * 1024:
                        return True
        except Exception:
            pass
            
    return False

def fetch_lrc_content(artist: str, title: str) -> str | None:
    cleaned = clean_song_title(title)
    search_titles = [title] if cleaned == title else [title, cleaned]
    aliases = ARTIST_ALIASES.get(artist, [artist])

    for st in search_titles:
        for an in aliases[:2]:
            # 策略 1: syncedlyrics
            try:
                lrc_text = search_lrc(f"{an} {st}", allow_plain_format=False)
                if lrc_text and "[" in lrc_text and "]" in lrc_text:
                    return lrc_text
            except Exception:
                pass
                
            # 策略 2: 网易云 API
            try:
                search_url = f"https://music.163.com/api/search/get/web?s={an}+{st}&type=1&offset=0&total=true&limit=1"
                r = requests.get(search_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if r.ok:
                    songs = r.json().get("result", {}).get("songs", [])
                    if songs:
                        song_id = songs[0]["id"]
                        lrc_url = f"https://music.163.com/api/song/lyric?os=pc&id={song_id}&lv=-1&kv=-1&tv=-1"
                        lr = requests.get(lrc_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                        if lr.ok:
                            lrc = lr.json().get("lrc", {}).get("lyric", "")
                            if lrc and "[" in lrc:
                                return lrc
            except Exception:
                pass
        
    return None

def process_single_song(item: dict) -> dict:
    song_id = item["song_id"]
    artist = item["artist_name"]
    album = item["album_title"]
    album_id = item["album_id"]
    title = item["title"]

    if check_d1_already_lit(album_id, song_id):
        return {"status": "SKIPPED_ALREADY_LIT", "id": song_id, "artist": artist, "title": title}

    local_mp3 = os.path.join(WORK_DIR, f"s_{song_id}.mp3")
    local_lrc = os.path.join(WORK_DIR, f"s_{song_id}.lrc")

    if not (os.path.exists(local_mp3) and os.path.getsize(local_mp3) > 100_000):
        ok = search_and_download_audio(artist, album, title, local_mp3)
        if not ok:
            return {"status": "FAILED_DOWNLOAD", "id": song_id, "artist": artist, "title": title}

    lrc_text = fetch_lrc_content(artist, title)
    has_lrc = False
    if lrc_text:
        with open(local_lrc, "w", encoding="utf-8") as f:
            f.write(lrc_text)
        has_lrc = True

    # 锁定写入 account_08
    target_bucket_id = CURRENT_BUCKET_ID
    target_bucket_cfg = buckets_cfg[target_bucket_id]
    s3 = get_s3_client(target_bucket_id)

    r2_audio_key = f"music/{artist}/{album}/s_{song_id}.mp3"
    r2_lrc_key = f"lyrics/{artist}/{album}/s_{song_id}.lrc"

    upload_size = os.path.getsize(local_mp3) + (os.path.getsize(local_lrc) if has_lrc and os.path.exists(local_lrc) else 0)
    try:
        s3.upload_file(
            local_mp3, target_bucket_cfg["name"], r2_audio_key,
            ExtraArgs={"ContentType": "audio/mpeg"}
        )
        if has_lrc:
            s3.upload_file(
                local_lrc, target_bucket_cfg["name"], r2_lrc_key,
                ExtraArgs={"ContentType": "text/plain; charset=utf-8"}
            )
        ensure_safe_bucket(upload_size)
    except Exception as e:
        return {"status": "FAILED_UPLOAD", "id": song_id, "artist": artist, "title": title, "error": str(e)}

    if os.path.exists(local_mp3):
        try: os.remove(local_mp3)
        except: pass
    if os.path.exists(local_lrc):
        try: os.remove(local_lrc)
        except: pass

    b_cfg = buckets_cfg[target_bucket_id]
    cdn_domain = b_cfg.get("public_url", b_cfg.get("public_domain", "")).rstrip('/')
    abs_audio_url = f"{cdn_domain}/{r2_audio_key}"
    abs_lrc_url = f"{cdn_domain}/{r2_lrc_key}" if has_lrc and r2_lrc_key else None

    return {
        "status": "SUCCESS",
        "id": song_id,
        "artist": artist,
        "album": album,
        "title": title,
        "file_path": abs_audio_url,
        "lrc_path": abs_lrc_url,
        "bucket": target_bucket_id
    }

def batch_light_d1(updates: list[dict]) -> bool:
    if not updates:
        return True
    payload = {
        "updates": [
            {"id": u["id"], "file_path": u["file_path"], "lrc_path": u["lrc_path"]}
            for u in updates
        ]
    }
    try:
        r = requests.post(f"{API_BASE}/api/admin/songs/batch-light", json=payload, timeout=20)
        return r.ok
    except Exception as e:
        print(f"❌ 批量更新 D1 异常: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="MOODY Priority Missing Songs Orchestrator")
    parser.add_argument("--targets-file", type=str, default=TARGETS_FILE, help="自定义 targets JSON 路径")
    parser.add_argument("--artist", type=str, help="针对指定歌手执行 (如 '张雨生' / '动力火车' / '张靓颖')")
    parser.add_argument("--workers", type=int, default=4, help="并发线程数 (默认 4)")
    parser.add_argument("--limit", type=int, default=0, help="限制处理歌曲数 (0 为不限制)")
    args = parser.parse_args()

    targets_file_path = args.targets_file
    with open(targets_file_path, "r", encoding="utf-8") as f:
        targets = json.load(f)

    if args.artist:
        targets = [t for t in targets if args.artist.lower() in t["artist_name"].lower()]

    if args.limit > 0:
        targets = targets[:args.limit]

    print("=" * 70)
    print(f"🎵 MOODY 重点缺失歌手短板专项攻坚引擎启动")
    print(f"📌 任务规模: {len(targets)} 首歌曲")
    print(f"⚙️ 并发线程: {args.workers} | 主力写入存储桶: {CURRENT_BUCKET_ID} | 代理: {PROXY}")
    print("=" * 70)

    init_capacity_tracker()
    print(f"📊 {CURRENT_BUCKET_ID} 初始物理用量: {CURRENT_BUCKET_BYTES / (1024**3):.3f} GB / 10.00 GB (安全线: 9.00 GB)")

    start_time = time.time()
    success_count = 0
    skipped_count = 0
    failed_count = 0
    pending_updates = []
    
    BATCH_COMMIT_SIZE = 10

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_single_song, t): t for t in targets}
        
        for future in as_completed(futures):
            res = future.result()
            status = res["status"]
            
            if status == "SUCCESS":
                success_count += 1
                pending_updates.append(res)
                print(f"   ✅ [{res['artist']}] 《{res['title']}》成功上传 ({res['bucket']}) (歌词: {'有' if res['lrc_path'] else '无'})")
                
                if len(pending_updates) >= BATCH_COMMIT_SIZE:
                    ok = batch_light_d1(pending_updates)
                    if ok:
                        print(f"   ⚡ [D1 点亮] 批量点亮 {len(pending_updates)} 首完成！")
                    else:
                        print(f"   ⚠️ [D1 点亮] 批量提交出现警告")
                    pending_updates = []

            elif status == "SKIPPED_ALREADY_LIT":
                skipped_count += 1
                print(f"   ⏭️ [防冲突跳过] 《{res['title']}》- {res['artist']} 已由远端点亮，自动跳过！")
            else:
                failed_count += 1
                print(f"   ❌ [抓取失败] 《{res['title']}》- {res['artist']}")

    if pending_updates:
        ok = batch_light_d1(pending_updates)
        if ok:
            print(f"   ⚡ [D1 点亮] 收尾批量点亮 {len(pending_updates)} 首完成！")

    elapsed = time.time() - start_time
    final_size = get_bucket_size_bytes(CURRENT_BUCKET_ID)
    
    print("\n" + "=" * 70)
    print("🏆 重点缺失短板攻坚执行完毕！")
    print(f"⏱️ 耗时: {elapsed:.1f} 秒 ({elapsed/60:.1f} 分钟)")
    print(f"📈 成果: 成功点亮 {success_count} 首 | 防冲突跳过 {skipped_count} 首 | 失败 {failed_count} 首")
    print(f"💾 存储用量 ({CURRENT_BUCKET_ID}): {final_size / (1024**3):.3f} GB / 10.00 GB")
    print("=" * 70)

if __name__ == "__main__":
    main()
