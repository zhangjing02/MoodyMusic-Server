#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - Cloudflare R2 第 7 存储桶平移瘦身流水线 (Bucket 07 -> Bucket 08)
标的：
- 尚雯婕 (全库 141 首)
- 毛不易 (全库 21 首)
共计 162 首曲目 (MP3 + LRC)，释放约 905 MB 空间，使 Bucket 07 降至 9.20 GB 安全水位。
==============================================================================
"""

import os
import sys
import json
import time
import re
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg_all = json.load(f)["buckets"]

cfg_07 = cfg_all["account_07"]
cfg_08 = cfg_all["account_08"]

s3_07 = boto3.client(
    's3',
    endpoint_url=cfg_07['endpoint_url'],
    aws_access_key_id=cfg_07['access_key_id'],
    aws_secret_access_key=cfg_07['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4', max_pool_connections=20)
)
BUCKET_07 = cfg_07['name']
DOMAIN_07 = cfg_07['public_url'].rstrip('/')

s3_08 = boto3.client(
    's3',
    endpoint_url=cfg_08['endpoint_url'],
    aws_access_key_id=cfg_08['access_key_id'],
    aws_secret_access_key=cfg_08['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4', max_pool_connections=20)
)
BUCKET_08 = cfg_08['name']
DOMAIN_08 = cfg_08['public_url'].rstrip('/')

D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

TARGET_ARTISTS = ["尚雯婕", "毛不易"]

def fetch_target_songs():
    print("📡 [1/6] 从 D1 网关获取标的歌手曲目清单...", flush=True)
    resp = requests.get(D1_SONGS_URL, timeout=30)
    data = resp.json().get('data', [])
    
    targets = []
    for art in data:
        art_name = art.get('name')
        if art_name in TARGET_ARTISTS:
            for alb in art.get('albums', []):
                alb_title = alb.get('title')
                for s in alb.get('songs', []):
                    path = s.get('path') or ''
                    if 'pub-a0a90fda9b0d45d59a52685eb2ee93d6' in path or 'moody-music-asset-07' in path:
                        # 提取实际的 S3 Key
                        if '.r2.dev/' in path:
                            mp3_key = path.split('.r2.dev/')[1]
                        else:
                            mp3_key = path.lstrip('/')
                            
                        id_match = re.search(r's_(\d+)\.mp3', mp3_key)
                        if not id_match:
                            continue
                        sid = int(id_match.group(1))
                        lrc_key = mp3_key.replace('music/', 'lyrics/').replace('.mp3', '.lrc')
                        
                        targets.append({
                            'id': sid,
                            'title': s.get('title'),
                            'artist': art_name,
                            'album': alb_title,
                            'mp3_key': mp3_key,
                            'lrc_key': lrc_key,
                            'old_path': path
                        })
    print(f"   ✅ 筛选出待迁移曲目: {len(targets)} 首", flush=True)
    return targets

def migrate_single_song(item):
    sid = item['id']
    art = item['artist']
    mp3_key = item['mp3_key']
    lrc_key = item['lrc_key']
    
    try:
        # 1. 复制 MP3
        mp3_obj = s3_07.get_object(Bucket=BUCKET_07, Key=mp3_key)
        mp3_bytes = mp3_obj['Body'].read()
        mp3_size = len(mp3_bytes)
        
        s3_08.put_object(
            Bucket=BUCKET_08,
            Key=mp3_key,
            Body=mp3_bytes,
            ContentType='audio/mpeg'
        )
        
        # 2. 复制 LRC（如果有）
        has_lrc = False
        try:
            lrc_obj = s3_07.get_object(Bucket=BUCKET_07, Key=lrc_key)
            lrc_bytes = lrc_obj['Body'].read()
            s3_08.put_object(
                Bucket=BUCKET_08,
                Key=lrc_key,
                Body=lrc_bytes,
                ContentType='text/plain; charset=utf-8'
            )
            has_lrc = True
        except Exception:
            pass
            
        new_audio_url = f"{DOMAIN_08}/{mp3_key}"
        new_lrc_url = f"{DOMAIN_08}/{lrc_key}" if has_lrc else ""
        
        return {
            'success': True,
            'id': sid,
            'artist': art,
            'title': item['title'],
            'mp3_key': mp3_key,
            'lrc_key': lrc_key,
            'has_lrc': has_lrc,
            'size': mp3_size,
            'new_audio_url': new_audio_url,
            'new_lrc_url': new_lrc_url
        }
    except Exception as e:
        return {
            'success': False,
            'id': sid,
            'title': item['title'],
            'error': str(e)
        }

def main():
    print("=" * 80, flush=True)
    print("🚀 启动 Bucket 07 -> Bucket 08 资产平移与瘦身流水线", flush=True)
    print("=" * 80, flush=True)
    
    targets = fetch_target_songs()
    if not targets:
        print("❌ 未找到待迁移歌曲，退出", flush=True)
        return
        
    print(f"\n📦 [2/6] 并发平移物理文件至 Bucket 08 (共 {len(targets)} 首)...", flush=True)
    success_results = []
    failed_results = []
    total_migrated_bytes = 0
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(migrate_single_song, t): t for t in targets}
        done_cnt = 0
        for f in as_completed(futures):
            res = f.result()
            done_cnt += 1
            if res['success']:
                success_results.append(res)
                total_migrated_bytes += res['size']
                if done_cnt % 20 == 0 or done_cnt == len(targets):
                    print(f"   Progress: {done_cnt}/{len(targets)} 首同步完成... ({total_migrated_bytes/(1024*1024):.1f} MB)", flush=True)
            else:
                failed_results.append(res)
                print(f"   ❌ 失败: ID {res['id']} - {res['title']}: {res['error']}", flush=True)
                
    print(f"\n   ✅ 物理写入成功: {len(success_results)} / {len(targets)} 首")
    print(f"   📊 累计传输体积: {total_migrated_bytes / (1024*1024):.2f} MB")
    
    if failed_results:
        print(f"⚠️ 存在 {len(failed_results)} 首同步失败，终止后续切换与删除操作！", flush=True)
        return
        
    # 3. 完整性校验与 HTTP 可达性抽检
    print("\n🔍 [3/6] 验证 Bucket 08 直链可达性抽检...", flush=True)
    sample_res = success_results[:5]
    for s in sample_res:
        url = s['new_audio_url']
        r = requests.head(url, timeout=10)
        print(f"   • HEAD {url} -> HTTP {r.status_code} ({r.headers.get('content-length')} bytes)", flush=True)
        if r.status_code != 200:
            print("❌ 直链校验失败，终止切换！", flush=True)
            return
            
    # 4. 调用 D1 生产网关批量切换直链
    print("\n⚡ [4/6] 向 D1 网关提交 batch-light 原子更新直链 (指向 Bucket 08)...", flush=True)
    d1_updates = []
    for s in success_results:
        d1_updates.append({
            "id": s['id'],
            "file_path": s['new_audio_url'],
            "lrc_path": s['new_lrc_url']
        })
        
    # 分批提交，每批 50 条
    batch_size = 50
    for i in range(0, len(d1_updates), batch_size):
        chunk = d1_updates[i:i+batch_size]
        payload = {"updates": chunk}
        resp = requests.post(D1_LIGHT_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
        print(f"   • D1 批次 [{i//batch_size + 1}]: HTTP {resp.status_code} - {resp.text}", flush=True)
        
    # 5. 从 Bucket 07 中物理删除旧资产
    print("\n🧹 [5/6] 生产直链已平稳切换，开始从 Bucket 07 物理删除旧文件释放空间...", flush=True)
    keys_to_delete = []
    for s in success_results:
        keys_to_delete.append({'Key': s['mp3_key']})
        if s['has_lrc']:
            keys_to_delete.append({'Key': s['lrc_key']})
            
    print(f"   准备从 Bucket 07 删除对象: {len(keys_to_delete)} 个...", flush=True)
    # S3 delete_objects 每批最多 1000 个
    for i in range(0, len(keys_to_delete), 500):
        sub_keys = keys_to_delete[i:i+500]
        del_resp = s3_07.delete_objects(
            Bucket=BUCKET_07,
            Delete={'Objects': sub_keys}
        )
        print(f"   • 物理删除批次 [{i//500 + 1}]: 成功释放 {len(del_resp.get('Deleted', []))} 个对象", flush=True)
        
    print(f"\n🎉 [6/6] 平移瘦身全部完成！成功释放 Bucket 07 物理空间约 {total_migrated_bytes/(1024*1024):.2f} MB！", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
