#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 存量曲库歌词全量补齐与 R2 批量点亮程序
(Batch Backfill Lyrics to Cloudflare R2 and D1 - Enhanced with syncedlyrics)

功能：
1. 从本地 catalog_sync.db 扫描所有有 MP3 音频但缺少 LRC 歌词的歌曲
2. 使用 syncedlyrics (多源 NetEase + Lrclib + 智能多候选回退) 获取高精度时间轴歌词
3. Windows 路径安全转义，并在本地 storage/lyrics 目录保留备份
4. 使用 boto3 直传至 Cloudflare R2 (moody-music-asset-02 存储桶)
5. 批量调用 Worker 接口 (/api/admin/songs/batch-light) 毫秒级点亮 Cloudflare D1 数据库
6. 同步回写本地 catalog_sync.db，更新 r2_lrc_key 和 local_lrc
"""

import os
import sys
import re
import time
import json
import sqlite3
import urllib.parse
import requests
import boto3
from botocore.config import Config
import syncedlyrics

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
LOCAL_LYRICS_DIR = os.path.join(BASE_DIR, "storage", "lyrics")
API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

os.makedirs(LOCAL_LYRICS_DIR, exist_ok=True)

# ----------------- R2 客户端加载 -----------------
def get_r2_client():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    b_info = cfg["buckets"]["account_02"]
    s3 = boto3.client(
        service_name="s3",
        endpoint_url=b_info["endpoint_url"],
        aws_access_key_id=b_info["access_key_id"],
        aws_secret_access_key=b_info["secret_access_key"],
        region_name="auto",
        config=Config(s3={"addressing_style": "path"})
    )
    return s3, b_info["name"]

# ----------------- 高级歌词检索模块 -----------------
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/',
}

def clean_song_title(title: str) -> list[str]:
    candidates = [title]
    t1 = re.sub(r'\(.*?\)|（.*?）|\[.*?\]|【.*?】', '', title).strip()
    if t1 and t1 not in candidates:
        candidates.append(t1)
    t2 = re.sub(r'^\d+[\s\.\-_]+', '', title).strip()
    if t2 and t2 not in candidates:
        candidates.append(t2)
    t3 = re.sub(r'^\d+[\s\.\-_]+', '', t1).strip()
    if t3 and t3 not in candidates:
        candidates.append(t3)
    return candidates

def fetch_lrc_robust(artist: str, title: str) -> str | None:
    # 策略 1: syncedlyrics 组合 artist + title
    clean_titles = clean_song_title(title)
    for ct in clean_titles:
        try:
            lrc = syncedlyrics.search(f"{artist} {ct}", providers=['NetEase', 'Lrclib'])
            if lrc and len(lrc) > 100 and '[' in lrc and ':' in lrc:
                return lrc
        except Exception:
            pass
            
    # 策略 2: syncedlyrics 单搜 title
    for ct in clean_titles:
        if len(ct) >= 2:
            try:
                lrc = syncedlyrics.search(ct, providers=['NetEase', 'Lrclib'])
                if lrc and len(lrc) > 100 and '[' in lrc and ':' in lrc:
                    return lrc
            except Exception:
                pass

    # 策略 3: 网易云底层 API 多搜索回退
    queries = [f"{artist} {title}"] + [f"{artist} {ct}" for ct in clean_titles]
    seen = set()
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        try:
            search_url = f"http://music.163.com/api/search/get/web?s={urllib.parse.quote(q)}&type=1&offset=0&limit=5"
            resp = requests.get(search_url, headers=HEADERS, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                songs = data.get('result', {}).get('songs', [])
                for s in songs:
                    sid = s['id']
                    lrc_url = f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1"
                    lr = requests.get(lrc_url, headers=HEADERS, timeout=6)
                    if lr.status_code == 200:
                        lrc_text = lr.json().get('lrc', {}).get('lyric', '')
                        if lrc_text and len(lrc_text) > 80 and '[' in lrc_text and ':' in lrc_text:
                            return lrc_text
        except Exception:
            pass
        time.sleep(0.2)

    return None

def sanitize_folder_name(name: str) -> str:
    """消除 Windows 非法字符，防止写盘崩溃"""
    return re.sub(r'[\/:*?"<>|]', '_', name).strip()

# ----------------- 核心主流程 -----------------
def run_backfill():
    print("=" * 80)
    print("🚀 MOODY - 存量曲库缺失歌词全量自动补齐任务启动 (Enhanced)")
    print(f"📂 状态数据库: {DB_PATH}")
    print("=" * 80)

    if not os.path.exists(DB_PATH):
        print("❌ 错误: catalog_sync.db 数据库不存在！")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 扫描待补齐歌词清单
    cur.execute("""
        SELECT song_id, artist_name, album_title, song_title, r2_mp3_key
        FROM tracks_sync_state
        WHERE (r2_mp3_key IS NOT NULL AND r2_mp3_key != '')
          AND (r2_lrc_key IS NULL OR r2_lrc_key = '')
        ORDER BY artist_name, album_title, song_id
    """)
    tracks_to_process = cur.fetchall()
    total = len(tracks_to_process)

    if total == 0:
        print("🎉 恭喜！当前曲库中所有已点亮歌曲均已拥有歌词，无需补齐！")
        conn.close()
        return

    print(f"📋 共检索到 {total} 首歌曲需要补齐歌词。")
    s3_client, bucket_name = get_r2_client()
    print(f"☁️ R2 目标存储桶: {bucket_name}")
    print("=" * 80)

    success_items = []
    failed_items = []
    start_time = time.time()

    for idx, (song_id, artist, album, title, r2_mp3_key) in enumerate(tracks_to_process, 1):
        r2_lrc_key = r2_mp3_key[:-4] + ".lrc"
        print(f"[{idx}/{total}] 🎵 处理: {artist} - 《{title}》 (专辑: 《{album}》)...")

        # 抓取高精度歌词
        lrc_text = fetch_lrc_robust(artist, title)
        if not lrc_text:
            print(f"   ⚠️ 未能检索到可用歌词，跳过")
            failed_items.append((song_id, artist, title, "未找到歌词"))
            time.sleep(0.2)
            continue

        # 本地备份安全写盘 (防止 Windows 特殊字符报错)
        safe_artist = sanitize_folder_name(artist)
        safe_album = sanitize_folder_name(album)
        local_album_dir = os.path.join(LOCAL_LYRICS_DIR, safe_artist, safe_album)
        os.makedirs(local_album_dir, exist_ok=True)
        local_file_path = os.path.join(local_album_dir, f"s_{song_id}.lrc")
        try:
            with open(local_file_path, "w", encoding="utf-8") as lf:
                lf.write(lrc_text)
        except Exception as e:
            print(f"   ⚠️ 本地写盘异常: {e}")

        # 上传至 Cloudflare R2
        try:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=r2_lrc_key,
                Body=lrc_text.encode('utf-8'),
                ContentType="text/plain; charset=utf-8"
            )
            print(f"   ✅ [R2 写入成功] {r2_lrc_key} ({len(lrc_text)} 字节)")
            success_items.append({
                "id": song_id,
                "file_path": r2_mp3_key,
                "lrc_path": r2_lrc_key,
                "local_lrc": local_file_path,
                "artist": artist,
                "title": title
            })
        except Exception as e:
            print(f"   ❌ [R2 上传失败] {e}")
            failed_items.append((song_id, artist, title, f"R2上传错误: {e}"))

        time.sleep(0.25)

    print("\n" + "=" * 80)
    print(f"📦 歌词抓取与 R2 上传阶段结束！成功: {len(success_items)} 首 | 失败: {len(failed_items)} 首")
    print("=" * 80)

    # 批量点亮 Cloudflare D1 数据库
    if success_items:
        print(f"\n⚡ 开始向 Cloudflare D1 执行批量点亮 ({len(success_items)} 首)...")
        batch_size = 50
        total_lit = 0
        
        for i in range(0, len(success_items), batch_size):
            chunk = success_items[i:i + batch_size]
            payload = {
                "updates": [
                    {
                        "id": item["id"],
                        "file_path": item["file_path"],
                        "lrc_path": item["lrc_path"]
                    }
                    for item in chunk
                ]
            }

            try:
                t0 = time.time()
                resp = requests.post(API_BATCH_LIGHT_URL, json=payload, timeout=20)
                if resp.status_code == 200:
                    for item in chunk:
                        cur.execute("""
                            UPDATE tracks_sync_state
                            SET r2_lrc_key = ?,
                                local_lrc = ?,
                                status = 'D1_LIT',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE song_id = ?
                        """, (item["lrc_path"], item["local_lrc"], item["id"]))
                    conn.commit()
                    total_lit += len(chunk)
                    print(f"  ✨ [批次成功 {i//batch_size + 1}/{(len(success_items)-1)//batch_size + 1}] 已点亮 {len(chunk)} 首 (耗时: {time.time()-t0:.2f}s) | 累计: {total_lit}/{len(success_items)}")
                else:
                    print(f"  ❌ [批次失败] HTTP {resp.status_code}: {resp.text[:120]}")
            except Exception as e:
                print(f"  ⚠️ [批次异常] {e}")

            time.sleep(0.2)

        print(f"🎉 Cloudflare D1 批量点亮完成！成功点亮: {total_lit} 首")

    conn.close()
    elapsed = time.time() - start_time
    print("=" * 80)
    print(f"🏁 全量补齐任务收官！总耗时: {elapsed:.1f} 秒")
    print(f"📊 最终统计: 成功上传并点亮 {len(success_items)} 首 | 未匹配到歌词 {len(failed_items)} 首")
    print("=" * 80)

if __name__ == "__main__":
    run_backfill()
