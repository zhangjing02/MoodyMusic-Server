#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 存量音频批量轻量化转码与 R2 同名覆写脚本 (Batch Compress Stock)
依据 AUDIO_COMPRESSION_AND_STORAGE_SPEC.md 规范实现
核心任务：
1. 提取本地 catalog_sync.db 中已在云端（R2_UPLOADED、D1_LIT）但未压缩（is_compressed=0）的存量曲目
2. 基于本地 backend/downloads/ 的 320k 原始母盘（永久冷备），无损听感转码为 160kbps MP3 至 backend/downloads_optimized/
3. 向 Cloudflare R2 发起同名覆盖上传（Key: music/{artist}/{album}/s_{id}.mp3），实现云端透明瘦身 57%
4. 同步更新本地数据库字段（is_compressed=1, bitrate_kbps=160, file_size=new_size, compressed_at=NOW）
"""

import os
import sys
import time
import sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
OPTIMIZED_DIR = os.path.join(BASE_DIR, "downloads_optimized")
RECOVERED_DIR = os.path.join(BASE_DIR, "r2_recovered_320k")

os.makedirs(OPTIMIZED_DIR, exist_ok=True)
os.makedirs(RECOVERED_DIR, exist_ok=True)

sys.path.insert(0, os.path.dirname(__file__))
from compress_engine import transcode_to_160k
import r2_safety_guard
r2_safety_guard.assert_write_allowed()

API_UPLOAD_URL = "https://m-api.changgepd.ccwu.cc/api/admin/assets/upload"
PROXIES = {
    'http': 'http://127.0.0.1:7897',
    'https': 'http://127.0.0.1:7897'
}

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def do_post(files, data, timeout=90):
    try:
        return requests.post(API_UPLOAD_URL, files=files, data=data, proxies=PROXIES, timeout=timeout)
    except Exception:
        return requests.post(API_UPLOAD_URL, files=files, data=data, timeout=timeout)

def process_track(track):
    """
    单个曲目的转码与覆写流程：
    1. 确认本地母盘（若缺失则从 R2 找回至冷备份目录）
    2. 转码至 160k 输出到 downloads_optimized/
    3. 推送至 R2 同名覆写
    4. 更新 SQLite 数据库
    """
    sid, art, alb, title, local_mp3, r2_mp3_key, old_size, status = track
    
    # 1. 确认源文件
    source_file = local_mp3
    if not source_file or not os.path.exists(source_file):
        potential = os.path.join(DOWNLOADS_DIR, f"{title}-{art}-{alb}.mp3")
        if os.path.exists(potential):
            source_file = potential
        else:
            print(f"  📥 [找回母带] 《{title}》本地缺失，正从 R2 下载留存永久冷备份...")
            r2_url = f"https://m-api.changgepd.ccwu.cc/storage/{r2_mp3_key}"
            recovered_path = os.path.join(RECOVERED_DIR, f"s_{sid}_{title}.mp3")
            try:
                resp = requests.get(r2_url, proxies=PROXIES, timeout=60)
                if resp.status_code == 200:
                    with open(recovered_path, 'wb') as f_rec:
                        f_rec.write(resp.content)
                    source_file = recovered_path
                else:
                    return sid, False, f"R2 拉取失败: HTTP {resp.status_code}"
            except Exception as e:
                return sid, False, f"R2 拉取异常: {e}"

    # 2. 确定 160k 输出路径
    base_name = os.path.basename(source_file)
    target_160k = os.path.join(OPTIMIZED_DIR, base_name)

    # 若尚未压缩或临时文件不完整，执行 160k 转码
    if not os.path.exists(target_160k) or os.path.getsize(target_160k) < 500000:
        success = transcode_to_160k(source_file, target_160k)
        if not success:
            return sid, False, "FFmpeg 转码失败"

    new_size = os.path.getsize(target_160k)
    saved_mb = (old_size - new_size) / (1024 * 1024) if old_size else 0

    # 3. 若已在 R2 存储桶（R2_UPLOADED / D1_LIT），执行 R2 同名覆写
    if status in ('R2_UPLOADED', 'D1_LIT'):
        try:
            with open(target_160k, 'rb') as f_mp3:
                files = {'file': (f"s_{sid}.mp3", f_mp3, 'audio/mpeg')}
                data = {'category': f"music/{art}/{alb}", 'filename': f"s_{sid}.mp3"}
                resp = do_post(files, data, timeout=90)
                
            if resp.status_code != 200:
                return sid, False, f"R2 覆写 HTTP 异常: {resp.status_code}"
            resp_json = resp.json()
            if resp_json.get('code') not in [0, 200]:
                return sid, False, f"R2 覆写接口错误: {resp_json.get('message')}"
        except Exception as e:
            return sid, False, f"R2 覆写网络超时: {e}"

    # 4. 更新数据库状态
    conn = get_db()
    conn.execute("""
        UPDATE tracks_sync_state
        SET is_compressed = 1,
            bitrate_kbps = 160,
            file_size = ?,
            compressed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE song_id = ?
    """, (new_size, sid))
    conn.commit()
    conn.close()

    return sid, True, f"瘦身 {saved_mb:.2f} MB (新大小: {new_size / (1024*1024):.2f} MB)"

def get_current_r2_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT')
    """)
    total_count, total_bytes = c.fetchone()
    conn.close()
    
    gb = total_bytes / (1024 * 1024 * 1024)
    pct = (total_bytes / (10 * 1024 * 1024 * 1024)) * 100
    rem_gb = max(0.0, (10 * 1024 * 1024 * 1024 - total_bytes) / (1024 * 1024 * 1024))
    return total_count, gb, pct, rem_gb

def run_batch_compress(batch_size=20, max_workers=3, max_total_limit=None):
    print("=" * 80)
    print("🗜️ MOODY - 存量音频批量轻量化转码与 R2 覆写瘦身流水线")
    print(f"📁 母盘冷备目录: {DOWNLOADS_DIR} (永久保留)")
    print(f"📁 轻量化转码目录: {OPTIMIZED_DIR} (160kbps CBR)")
    print(f"🧵 并发线程: {max_workers} | 批次大小: {batch_size}" + (f" | 运行上限: {max_total_limit} 首" if max_total_limit else ""))
    print("=" * 80)

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT') AND is_compressed = 0
    """)
    total_uncompressed, total_bytes = c.fetchone()
    conn.close()

    _, init_gb, init_pct, init_rem = get_current_r2_stats()
    print(f"📊 当前未压缩存量曲目: {total_uncompressed} 首 (占用: {total_bytes / (1024*1024*1024):.2f} GB)")
    print(f"📡 当前 R2 总用量基准: {init_gb:.3f} GB / 10.000 GB ({init_pct:.2f}%) | 剩余容量: {init_rem:.3f} GB\n")

    if total_uncompressed == 0:
        print("🎉 所有存量曲目均已完成 160k 轻量化！无需重复执行。")
        return

    processed = 0

    while True:
        if max_total_limit and processed >= max_total_limit:
            print(f"\n🛑 已达到指定的单次处理上限 ({max_total_limit} 首)，平稳退出。")
            break

        current_fetch = batch_size
        if max_total_limit:
            current_fetch = min(batch_size, max_total_limit - processed)

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT song_id, artist_name, album_title, song_title, local_mp3, r2_mp3_key, file_size, status
            FROM tracks_sync_state
            WHERE status IN ('R2_UPLOADED', 'D1_LIT') AND is_compressed = 0
            ORDER BY song_id ASC
            LIMIT ?
        """, (current_fetch,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            break

        target_total = max_total_limit if max_total_limit else total_uncompressed
        print(f"\n🚀 开始处理批次 [{processed + 1} ~ {processed + len(rows)} / {target_total}]...")
        t0 = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_track = {executor.submit(process_track, r): r for r in rows}
            for future in as_completed(future_to_track):
                r = future_to_track[future]
                sid, art, alb, title, _, _, old_size, _ = r
                try:
                    _, success, msg = future.result()
                    if success:
                        processed += 1
                        print(f"  ✅ [{processed}/{target_total}] 《{title}》 - {art} | {msg}")
                    else:
                        print(f"  ❌ 《{title}》 - {art} 失败: {msg}")
                except Exception as e:
                    print(f"  ❌ 《{title}》 执行异常: {e}")

        elapsed = time.time() - t0
        _, cur_gb, cur_pct, cur_rem = get_current_r2_stats()
        freed_mb = (init_gb - cur_gb) * 1024
        print(f"⏱️ 批次完成 (耗时: {elapsed:.1f}s) | 当前 R2 降至: {cur_gb:.3f} GB ({cur_pct:.2f}%) | 累计净释放: {freed_mb:.1f} MB | 剩余: {cur_rem:.3f} GB")
        time.sleep(0.5)

    _, final_gb, final_pct, final_rem = get_current_r2_stats()
    print("\n" + "=" * 80)
    print(f"🏆 本轮 160k 轻量化与 R2 覆写执行完毕！共处理: {processed} 首曲目。")
    print(f"📉 R2 空间变化: {init_gb:.3f} GB ➔ {final_gb:.3f} GB (占比: {init_pct:.2f}% ➔ {final_pct:.2f}%)")
    print(f"🎉 净释放云端存储: {(init_gb - final_gb) * 1024:.1f} MB ({(init_gb - final_gb):.3f} GB)")
    print(f"🛡️ 距离 10GB 免费限额剩余安全容量: {final_rem:.3f} GB")
    print("=" * 80)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MOODY 存量音频 160k 轻量化与 R2 覆写脚本")
    parser.add_argument("--limit", type=int, default=None, help="本轮最大处理曲目数 (例如 5, 20, 50)")
    parser.add_argument("--batch-size", type=int, default=20, help="批处理并发窗口大小 (默认 20)")
    parser.add_argument("--workers", type=int, default=3, help="并发线程数 (默认 3)")
    args = parser.parse_args()

    run_batch_compress(batch_size=args.batch_size, max_workers=args.workers, max_total_limit=args.limit)
