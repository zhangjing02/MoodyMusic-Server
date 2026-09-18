import os
import sys
import json
import time
import sqlite3
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
import download_music as dm
from smart_dual_bucket_uploader import load_r2_clients, compress_to_160k_cbr
from leehom_pipeline import LEEHOM_PIPELINE
from david_tao_pipeline import DAVID_TAO_PIPELINE

DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
OPTIMIZED_DIR = os.path.join(BASE_DIR, "downloads_optimized")
os.makedirs(OPTIMIZED_DIR, exist_ok=True)

API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
TARGET_ACCOUNT = "account_04"

def process_artist(artist_name, pipelines):
    print(f"\\n{'='*80}\\n🚀 开始修复专项: {artist_name}\\n{'='*80}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    clients = load_r2_clients()
    s3_info = clients[TARGET_ACCOUNT]["info"]
    s3 = clients[TARGET_ACCOUNT]["s3"]
    bucket_name = s3_info["name"]
    public_domain = s3_info.get("public_domain", "")
    
    updates_payload = []
    repaired_count = 0
    total_tracks = 0
    
    for album_item in pipelines:
        album = album_item["album"]
        tracks = album_item["tracks"]
        total_tracks += len(tracks)
        
        for song in tracks:
            print(f"\\n⏳ 检查: {artist_name} - 《{album}》 - {song}")
            cur.execute("""
                SELECT song_id, local_mp3, local_lrc, r2_mp3_key 
                FROM tracks_sync_state 
                WHERE artist_name = ? AND album_title = ? AND song_title = ?
            """, (artist_name, album, song))
            row = cur.fetchone()
            
            if not row:
                print(f"⚠️ 数据库未找到: {song}")
                continue
                
            song_id, local_mp3, local_lrc, r2_mp3_key = row
            
            # 1. 如果本地文件不存在或不完整，下载它
            if not local_mp3 or not os.path.exists(local_mp3) or os.path.getsize(local_mp3) < 1000:
                print(f"📥 下载缺失音源: {song}")
                target_path, qa, lrc_info = dm.download_track(song, artist_name, album, dm.DEFAULT_DOWNLOAD_DIR)
                if not target_path:
                    print(f"❌ 无法下载: {song}")
                    continue
                local_mp3 = target_path
                local_lrc = lrc_info.get("lrc_path", "")
                
                # 更新本地库
                cur.execute("""
                    UPDATE tracks_sync_state 
                    SET local_mp3 = ?, local_lrc = ? 
                    WHERE song_id = ?
                """, (local_mp3, local_lrc, song_id))
                conn.commit()
            
            # 2. 压制 160k CBR
            opt_mp3 = os.path.join(OPTIMIZED_DIR, f"s_{song_id}.mp3")
            if not os.path.exists(opt_mp3) or os.path.getsize(opt_mp3) < 1000:
                print(f"🛠️ 重新压制 160k CBR: {song}")
                if not compress_to_160k_cbr(local_mp3, opt_mp3):
                    print(f"❌ 转码失败: {song}")
                    continue
                    
            opt_size = os.path.getsize(opt_mp3)
            r2_key = f"music/{artist_name}/{album}/s_{song_id}.mp3"
            r2_lrc_key = f"music/{artist_name}/{album}/s_{song_id}.lrc"
            
            final_file_path = f"{public_domain}/{r2_key}"
            final_lrc_path = f"{public_domain}/{r2_lrc_key}"
            
            # 3. 上传到 account_04
            try:
                print(f"☁️ 上传到 Bucket 04: {r2_key}")
                with open(opt_mp3, "rb") as f_mp3:
                    s3.put_object(Bucket=bucket_name, Key=r2_key, Body=f_mp3, ContentType="audio/mpeg")
                
                if local_lrc and os.path.exists(local_lrc):
                    with open(local_lrc, "rb") as f_lrc:
                        s3.put_object(Bucket=bucket_name, Key=r2_lrc_key, Body=f_lrc, ContentType="text/plain; charset=utf-8")
                
                cur.execute("""
                    UPDATE tracks_sync_state
                    SET status = 'R2_UPLOADED_ACCOUNT_04',
                        is_compressed = 1,
                        bitrate_kbps = 160,
                        r2_mp3_key = ?,
                        r2_lrc_key = ?
                    WHERE song_id = ?
                """, (final_file_path, final_lrc_path, song_id))
                conn.commit()
                
                updates_payload.append({
                    "id": song_id,
                    "file_path": final_file_path,
                    "lrc_path": final_lrc_path
                })
                repaired_count += 1
                
            except Exception as e:
                print(f"❌ 上传失败: {e}")
                
    # 4. 批量点亮 D1
    if updates_payload:
        print(f"\\n🚀 发送 Batch-Light API, 点亮 {len(updates_payload)} 首歌...")
        try:
            resp = requests.post(API_BATCH_LIGHT_URL, json={"updates": updates_payload}, timeout=60)
            if resp.status_code == 200:
                print(f"✅ 点亮成功！")
                sids = [u["id"] for u in updates_payload]
                cur.executemany("UPDATE tracks_sync_state SET status = 'D1_LIT', lit_at = CURRENT_TIMESTAMP WHERE song_id = ?", [(s,) for s in sids])
                conn.commit()
            else:
                print(f"❌ 点亮失败: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"❌ API 请求失败: {e}")
            
    conn.close()
    return total_tracks, repaired_count, len(updates_payload)

if __name__ == "__main__":
    t1, r1, u1 = process_artist("王力宏", LEEHOM_PIPELINE)
    t2, r2, u2 = process_artist("陶喆", DAVID_TAO_PIPELINE)
    
    print("\\n" + "="*80)
    print("📊 修复与点亮任务总结")
    print("="*80)
    print(f"王力宏: 计划 {t1} 首, 成功压制/上传 {r1} 首, D1 批量点亮请求 {u1} 首")
    print(f"陶喆:   计划 {t2} 首, 成功压制/上传 {r2} 首, D1 批量点亮请求 {u2} 首")
    print("="*80)
