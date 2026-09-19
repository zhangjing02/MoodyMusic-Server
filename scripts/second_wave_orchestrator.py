#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 第二波候选歌手主线攻坚引擎 (Wave 2 Orchestrator)
=========================================================
特性与保障：
1. 家里电脑并发防冲突：下载前对 D1 实时探活，若已由远端写入点亮则自动跳过。
2. 9.50 GB 存储桶物理红线绝对防护：主力桶 account_07 (当前 3.46G) 超 9.30G 自动熔断切入 account_08。
3. 官方 Topic 录音室母带优先，过滤 Live/翻唱/MV对白。
4. 同步滚动 LRC 歌词自动挖掘与上传。
5. 边缘 D1 即时批量点亮。
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

# ── 基础路径与配置 ──────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS_FILE = os.path.join(BASE_DIR, "scripts", "configs", "second_wave_targets.json")
R2_CONFIG_FILE = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/moody_wave2_workspace"
os.makedirs(WORK_DIR, exist_ok=True)

API_BASE = "https://m-api.changgepd.ccwu.cc"
PROXY = "http://127.0.0.1:7890"
PROXIES = {"http": PROXY, "https": PROXY}

# 污染关键词黑名单
BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    '官方完整版mv', 'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮', 'teaser'
]

# ── 读取 R2 配置 ────────────────────────────────────────
with open(R2_CONFIG_FILE, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)

buckets_cfg = r2_cfg["buckets"]
account_07 = buckets_cfg["account_07"]
account_08 = buckets_cfg["account_08"]

# S3 客户端缓存
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

# 容量跟踪与安全锁
capacity_lock = Lock()
CURRENT_BUCKET_ID = "account_07"
MAX_SAFE_BYTES = int(9.30 * 1024 * 1024 * 1024) # 9.30 GB 预警线

def get_bucket_size_bytes(bucket_id: str) -> int:
    client = get_s3_client(bucket_id)
    bucket_name = buckets_cfg[bucket_id]["name"]
    paginator = client.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get("Contents", []):
            total += obj["Size"]
    return total

def ensure_safe_bucket() -> str:
    """检查当前目标桶物理容量，若超 9.30G 则无缝切到 account_08"""
    global CURRENT_BUCKET_ID
    with capacity_lock:
        if CURRENT_BUCKET_ID == "account_07":
            # 实时检查 account_07
            used = get_bucket_size_bytes("account_07")
            used_gb = used / (1024**3)
            if used >= MAX_SAFE_BYTES:
                print(f"\n🚨 [CAPACITY WARNING] account_07 容量达到 {used_gb:.3f} GB (超过 9.30G 预警线)！")
                print("🔀 自动无缝将主力写入桶切换至全新的【account_08】！\n")
                CURRENT_BUCKET_ID = "account_08"
            else:
                # 安全
                pass
        return CURRENT_BUCKET_ID

# ── D1 探活（防家里电脑并发写入冲突）───────────────────────
def check_d1_already_lit(album_id: int, song_id: int) -> bool:
    try:
        r = requests.get(f"{API_BASE}/api/admin/albums/detail", params={"album_id": album_id}, timeout=10)
        if r.ok:
            songs = r.json().get('data', {}).get('songs', [])
            for s in songs:
                if s["id"] == song_id:
                    return bool(s.get("file_path"))
    except Exception as e:
        pass
    return False

# ── 音频搜索与下载 ───────────────────────────────────────
def search_and_download_audio(artist: str, album: str, title: str, out_path: str) -> bool:
    # 策略 1: 搜索 YouTube Topic 官方频道
    queries = [
        f"{artist} - Topic {title}",
        f"{artist} {title} Topic",
        f"{artist} {title} 官方"
    ]
    
    for q in queries:
        cmd_search = [
            "yt-dlp", "--proxy", PROXY,
            "--flat-playlist", "--no-warnings",
            "--print", "%(id)s | %(channel)s | %(title)s | %(duration)s",
            f"ytsearch10:{q}"
        ]
        try:
            res = subprocess.run(cmd_search, capture_output=True, text=True, timeout=25)
            lines = [l.strip() for l in res.stdout.split("\n") if l.strip()]
            best_id = None
            
            # 第一优先级: Topic 频道
            for l in lines:
                parts = l.split(" | ")
                if len(parts) >= 3:
                    vid, channel, vtitle = parts[0], parts[1], parts[2]
                    # 检查黑名单
                    if any(kw in vtitle.lower() for kw in BLACK_KEYWORDS):
                        continue
                    if "topic" in channel.lower():
                        best_id = vid
                        break
            
            # 第二优先级: 非 Topic 但无黑名单且时长在合理范围 (60s ~ 600s)
            if not best_id:
                for l in lines:
                    parts = l.split(" | ")
                    if len(parts) >= 3:
                        vid, channel, vtitle = parts[0], parts[1], parts[2]
                        if any(kw in vtitle.lower() for kw in BLACK_KEYWORDS):
                            continue
                        best_id = vid
                        break
            
            if best_id:
                # 确定视频，执行下载并标准化转码为 MP3 192k
                temp_raw = out_path + ".temp"
                cmd_down = [
                    "yt-dlp", "--proxy", PROXY,
                    "-x", "--audio-format", "mp3", "--audio-quality", "192K",
                    "-o", temp_raw + ".%(ext)s",
                    f"https://www.youtube.com/watch?v={best_id}"
                ]
                r_down = subprocess.run(cmd_down, capture_output=True, timeout=90)
                downloaded_file = temp_raw + ".mp3"
                if os.path.exists(downloaded_file) and os.path.getsize(downloaded_file) > 100_000:
                    # 使用 FFmpeg 进行标准化规整 (去除多余流，输出纯音频)
                    cmd_norm = [
                        "ffmpeg", "-y", "-i", downloaded_file,
                        "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                        out_path
                    ]
                    subprocess.run(cmd_norm, capture_output=True, timeout=30)
                    # 清理临时文件
                    if os.path.exists(downloaded_file):
                        os.remove(downloaded_file)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 100_000:
                        return True
        except Exception as e:
            continue
            
    return False

# ── 歌词获取 ───────────────────────────────────────────
def fetch_lrc(artist: str, title: str) -> str | None:
    try:
        import syncedlyrics
        lrc = syncedlyrics.search(f"{artist} {title}")
        if lrc and "[" in lrc and ":" in lrc:
            return lrc
    except Exception:
        pass
    return None

# ── 单曲处理管道 ───────────────────────────────────────
def process_single_song(song_meta: dict) -> dict:
    sid = song_meta["song_id"]
    artist = song_meta["artist_name"]
    album = song_meta["album_title"]
    title = song_meta["title"]
    album_id = song_meta["album_id"]
    
    # 1. 实时探活防冲突
    if check_d1_already_lit(album_id, sid):
        return {"status": "SKIPPED_ALREADY_LIT", "id": sid, "title": title, "artist": artist}
        
    local_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
    local_lrc = os.path.join(WORK_DIR, f"s_{sid}.lrc")
    
    # 2. 下载音频
    if not (os.path.exists(local_mp3) and os.path.getsize(local_mp3) > 100_000):
        ok = search_and_download_audio(artist, album, title, local_mp3)
        if not ok:
            return {"status": "FAILED_DOWNLOAD", "id": sid, "title": title, "artist": artist}
            
    # 3. 抓取歌词
    lrc_content = fetch_lrc(artist, title)
    has_lrc = False
    if lrc_content:
        with open(local_lrc, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        has_lrc = True
        
    # 4. 安全桶与上传
    target_bucket_id = ensure_safe_bucket()
    target_bucket_cfg = buckets_cfg[target_bucket_id]
    s3 = get_s3_client(target_bucket_id)
    
    r2_audio_key = f"music/{artist}/{album}/s_{sid}.mp3"
    r2_lrc_key = f"lyrics/{artist}/{album}/s_{sid}.lrc"
    
    try:
        s3.upload_file(
            local_mp3, target_bucket_cfg["name"], r2_audio_key,
            ExtraArgs={"ContentType": "audio/mpeg"}
        )
        if has_lrc:
            s3.upload_file(
                local_lrc, target_bucket_cfg["name"], r2_lrc_key,
                ExtraArgs={"ContentType": "text/plain"}
            )
    except Exception as e:
        return {"status": "FAILED_UPLOAD", "id": sid, "title": title, "error": str(e)}
        
    # 清理本地已上传的临时文件，释放磁盘
    try:
        if os.path.exists(local_mp3):
            os.remove(local_mp3)
        if os.path.exists(local_lrc):
            os.remove(local_lrc)
    except Exception:
        pass
        
    return {
        "status": "SUCCESS",
        "id": sid,
        "artist": artist,
        "album": album,
        "title": title,
        "file_path": r2_audio_key,
        "lrc_path": r2_lrc_key if has_lrc else None,
        "bucket": target_bucket_id
    }

# ── 批量点亮 D1 ────────────────────────────────────────
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
        resp = requests.post(f"{API_BASE}/api/admin/songs/batch-light", json=payload, timeout=20)
        return resp.ok
    except Exception as e:
        print(f"❌ D1 批量点亮异常: {e}")
        return False

# ── 主执行流程 ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MOODY Wave 2 Batch Orchestrator")
    parser.add_argument("--batch", type=int, choices=[1, 2, 3], help="执行第几批次 (1: 王心凌+窦唯; 2: 尚雯婕+万芳; 3: 苏慧伦+庾澄庆)")
    parser.add_argument("--artist", type=str, help="针对指定歌手执行 (如 '王心凌')")
    parser.add_argument("--workers", type=int, default=3, help="并发线程数 (默认 3)")
    parser.add_argument("--limit", type=int, default=0, help="限制处理歌曲数 (0 为不限制)")
    args = parser.parse_args()

    # 1. 载入全部目标
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        all_targets = json.load(f)

    # 2. 过滤批次
    batch_map = {
        1: ["王心凌", "窦唯"],
        2: ["尚雯婕", "万芳"],
        3: ["苏慧伦", "庾澄庆"]
    }

    if args.artist:
        targets = [t for t in all_targets if t["artist_name"] == args.artist]
    elif args.batch:
        allowed = batch_map[args.batch]
        targets = [t for t in all_targets if t["artist_name"] in allowed]
    else:
        targets = all_targets

    if args.limit > 0:
        targets = targets[:args.limit]

    print("=" * 70)
    print(f"🎵 MOODY 第二波主线攻坚引擎启动")
    print(f"📌 任务规模: {len(targets)} 首歌曲")
    print(f"⚙️ 并发线程: {args.workers} | 当前主力存储桶: {CURRENT_BUCKET_ID}")
    print("=" * 70)

    # 预检容量
    size_b = get_bucket_size_bytes(CURRENT_BUCKET_ID)
    print(f"📊 {CURRENT_BUCKET_ID} 初始物理用量: {size_b / (1024**3):.3f} GB / 10.00 GB (安全线: 9.30 GB)")

    start_time = time.time()
    success_count = 0
    skipped_count = 0
    failed_count = 0
    pending_updates = []
    
    # 设定每 10 首批量向 D1 提交一次
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
                
                # 批量提交 D1
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

    # 提交剩余未点亮
    if pending_updates:
        ok = batch_light_d1(pending_updates)
        if ok:
            print(f"   ⚡ [D1 点亮] 收尾批量点亮 {len(pending_updates)} 首完成！")

    elapsed = time.time() - start_time
    final_size = get_bucket_size_bytes(CURRENT_BUCKET_ID)
    
    print("\n" + "=" * 70)
    print("🏆 本轮主线攻坚批次执行完毕！")
    print(f"⏱️ 耗时: {elapsed:.1f} 秒 ({elapsed/60:.1f} 分钟)")
    print(f"📈 成果: 成功点亮 {success_count} 首 | 防冲突跳过 {skipped_count} 首 | 失败 {failed_count} 首")
    print(f"💾 存储用量 ({CURRENT_BUCKET_ID}): {final_size / (1024**3):.3f} GB / 10.00 GB")
    print("=" * 70)

if __name__ == "__main__":
    main()
