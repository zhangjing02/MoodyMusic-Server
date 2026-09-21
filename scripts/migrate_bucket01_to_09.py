#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
Bucket 01 -> Bucket 09 资产平移与降载流水线 (Zero-Loss Pipeline)
==============================================================================
目标歌手：陈奕迅 (Eason Chan) + 孙燕姿 (Stefanie Sun)
预期释放空间：~2.05 GB (将 Bucket 01 从 10.29 GB 压降至 ~8.24 GB 绿色健康区)
Zero-Loss 六步严格 SOP:
  [1] 全量扫描两歌手在 Bucket 01 中的音频 (.mp3) 与歌词 (.lrc) 对象
  [2] 并发安全读取源桶并写入 Bucket 09
  [3] Bucket 09 对象 S3 HEAD 字节级强校验
  [4] D1 数据库原子批量切链 (POST /api/admin/songs/batch-light)
  [5] 生产 CDN 播放抽验 (HTTP 200)
  [6] 100% 成功后调用 Worker 接口安全释放 Bucket 01 源文件
==============================================================================
"""

import os
import sys
import json
import time
import socket
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed

# Cloudflare 边缘 IP 直连 (防 TUN 代理劫持与丢包)
CF_EDGE_IPS = ["104.21.21.164", "172.67.199.94"]
_orig_getaddrinfo = socket.getaddrinfo
def _custom_getaddrinfo(host, port, *args, **kwargs):
    if host == "m-api.changgepd.ccwu.cc":
        return _orig_getaddrinfo(CF_EDGE_IPS[0], port, *args, **kwargs)
    if host and host.endswith(".r2.cloudflarestorage.com"):
        return _orig_getaddrinfo("172.64.190.1", port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _custom_getaddrinfo

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
BASE_URL = "https://m-api.changgepd.ccwu.cc"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)

b09_info = r2_cfg["buckets"]["account_09"]
B09_NAME = b09_info["name"]
B09_DOMAIN = b09_info["public_url"].rstrip("/")

s3_b09 = boto3.client(
    "s3",
    endpoint_url=b09_info["endpoint_url"],
    aws_access_key_id=b09_info["access_key_id"],
    aws_secret_access_key=b09_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, signature_version="s3v4", connect_timeout=5, read_timeout=15)
)

TARGET_ARTISTS = ["陈奕迅", "孙燕姿"]

def fetch_artist_d1_mapping(artist_name):
    """从 D1 提取歌手全部歌曲的 ID、title 与相对路径映射"""
    url = f"{BASE_URL}/api/songs?artist={requests.utils.quote(artist_name)}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        return {}
    
    mapping = {} # relative_path -> song_info
    for album in data[0].get("albums", []):
        for s in album.get("songs", []):
            p = s.get("path") or ""
            # 去除已有 http 前缀提取相对路径
            clean_p = p.replace("https://r2.changgepd.ccwu.cc/", "")
            if clean_p.startswith("/"):
                clean_p = clean_p[1:]
            if clean_p.startswith("storage/"):
                clean_p = clean_p[8:]
            if clean_p:
                mapping[clean_p] = s
    return mapping

def scan_bucket01_artist_keys(artist_name):
    """扫描 Bucket 01 下该歌手的全部对象 (mp3 + lrc)"""
    prefix = f"music/{artist_name}/"
    url = f"{BASE_URL}/api/debug/r2?prefix={requests.utils.quote(prefix)}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    items = r.json().get("keys", [])
    return items

def migrate_single_object(item):
    """迁移单个对象至 Bucket 09 并强校验"""
    key = item["key"]
    expected_size = item["size"]
    
    # 1. 从 Worker storage 读取源文件
    fetch_url = f"{BASE_URL}/storage/{requests.utils.quote(key)}"
    for attempt in range(3):
        try:
            r = requests.get(fetch_url, timeout=20)
            if r.status_code == 200 and len(r.content) == expected_size:
                data = r.content
                break
        except Exception:
            time.sleep(1)
    else:
        return {"key": key, "success": False, "error": "Fetch from Bucket 01 failed or size mismatch"}

    # 2. 写入 Bucket 09
    content_type = "audio/mpeg" if key.endswith(".mp3") else ("text/plain; charset=utf-8" if key.endswith(".lrc") else "application/octet-stream")
    try:
        s3_b09.put_object(
            Bucket=B09_NAME,
            Key=key,
            Body=data,
            ContentType=content_type
        )
    except Exception as e:
        return {"key": key, "success": False, "error": f"Put to Bucket 09 failed: {e}"}

    # 3. S3 HEAD 字节级强核验
    try:
        head = s3_b09.head_object(Bucket=B09_NAME, Key=key)
        if head.get("ContentLength") != expected_size:
            return {"key": key, "success": False, "error": "Bucket 09 ContentLength mismatch"}
    except Exception as e:
        return {"key": key, "success": False, "error": f"Head on Bucket 09 failed: {e}"}

    return {"key": key, "success": True, "size": expected_size}

def main():
    print("=" * 80)
    print("🚀 启动 Bucket 01 -> Bucket 09 资产平移与降温流水线 (Zero-Loss)")
    print(f"🎯 目标平移歌手: {', '.join(TARGET_ARTISTS)}")
    print("=" * 80)

    all_keys_to_migrate = []
    d1_song_maps = {}

    for artist in TARGET_ARTISTS:
        print(f"\n📡 正在检索歌手 [{artist}] 的物理对象与 D1 拓扑...")
        keys = scan_bucket01_artist_keys(artist)
        d1_map = fetch_artist_d1_mapping(artist)
        d1_song_maps[artist] = d1_map
        
        mp3_cnt = sum(1 for k in keys if k["key"].endswith(".mp3"))
        lrc_cnt = sum(1 for k in keys if k["key"].endswith(".lrc"))
        total_sz = sum(k["size"] for k in keys)
        print(f" - Bucket 01 物理对象: 共 {len(keys)} 个 (.mp3: {mp3_cnt}, .lrc: {lrc_cnt}), 体积: {total_sz / 1000000:.2f} MB")
        print(f" - D1 数据库记录: 共关联 {len(d1_map)} 首歌曲")
        all_keys_to_migrate.extend(keys)

    total_files = len(all_keys_to_migrate)
    total_bytes = sum(k["size"] for k in all_keys_to_migrate)
    print("\n" + "-" * 80)
    print(f"📦 平移总量统计: 共 {total_files} 个文件, 总大小: {total_bytes / 1000000000:.3f} GB ({total_bytes / 1000000:.1f} MB)")
    print("-" * 80)

    # 2. 并发流式复制至 Bucket 09 并强校验
    print("\n⚡ [Step 1 & 2] 开始并发传输至 Bucket 09 并执行 S3 HEAD 字节强校验...")
    success_keys = set()
    failed_items = []
    
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(migrate_single_object, item): item for item in all_keys_to_migrate}
        done_cnt = 0
        for f in as_completed(futures):
            res = f.result()
            done_cnt += 1
            if res["success"]:
                success_keys.add(res["key"])
            else:
                failed_items.append(res)
            if done_cnt % 50 == 0 or done_cnt == total_files:
                pct = (done_cnt / total_files) * 100
                print(f"   进度: {done_cnt}/{total_files} ({pct:.1f}%) | 成功: {len(success_keys)} | 失败: {len(failed_items)}")

    duration = time.time() - start_time
    print(f"\n✅ 传输完成！耗时: {duration:.1f} 秒, 成功: {len(success_keys)}/{total_files}")
    if failed_items:
        print(f"❌ 发现 {len(failed_items)} 个文件传输失败，出于 Zero-Loss 铁律，终止切链与删除！")
        for f in failed_items[:5]:
            print("   失败项:", f)
        sys.exit(1)

    # 3. 原子更新 D1 数据库链接 (batch-light)
    print("\n⚡ [Step 3] 开始原子更新 D1 数据库链接至 Bucket 09...")
    songs_to_update = []
    for artist, d1_map in d1_song_maps.items():
        for rel_path, song in d1_map.items():
            sid = song["id"]
            new_audio_url = f"{B09_DOMAIN}/{rel_path}"
            
            # 检查是否有配对的 lrc
            lrc_rel = rel_path.rsplit(".", 1)[0] + ".lrc"
            new_lrc_url = f"{B09_DOMAIN}/{lrc_rel}" if lrc_rel in success_keys else None
            
            songs_to_update.append({
                "id": sid,
                "file_path": new_audio_url,
                "lrc_path": new_lrc_url
            })

    print(f"   待更新 D1 记录数: {len(songs_to_update)} 首")
    batch_size = 100
    for i in range(0, len(songs_to_update), batch_size):
        chunk = songs_to_update[i:i+batch_size]
        payload = {"songs": chunk}
        r_light = requests.post(f"{BASE_URL}/api/admin/songs/batch-light", json=payload, timeout=15)
        if r_light.status_code != 200:
            print(f"❌ D1 批量切链失败 (批次 {i//batch_size + 1}): {r_light.text}")
            sys.exit(1)
        print(f"   D1 切链进度: {min(i+batch_size, len(songs_to_update))}/{len(songs_to_update)} 完成")

    # 4. 生产 CDN 播放连通性抽检
    print("\n⚡ [Step 4] 生产 CDN 播放连通性抽验...")
    sample_mp3s = [k for k in success_keys if k.endswith(".mp3")][:5]
    for k in sample_mp3s:
        test_url = f"{B09_DOMAIN}/{k}"
        r_head = requests.head(test_url, timeout=10)
        print(f" - 抽验 {k.split('/')[-1]}: {r_head.status_code} ({r_head.headers.get('Content-Length')} 字节)")
        if r_head.status_code != 200:
            print(f"❌ 抽验失败！停止删除源桶文件！")
            sys.exit(1)
    print("✅ 抽验 100% 连通，可安全执行源文件释放！")

    # 5. 安全释放 Bucket 01 源文件
    print("\n⚡ [Step 5] 安全释放 Bucket 01 中已迁移的源文件...")
    keys_list = list(success_keys)
    del_batch = 400
    total_deleted = 0
    for i in range(0, len(keys_list), del_batch):
        chunk = keys_list[i:i+del_batch]
        r_del = requests.post(f"{BASE_URL}/api/admin/debug/delete-bucket01-keys", json={"keys": chunk}, timeout=30)
        if r_del.status_code == 200:
            total_deleted += len(chunk)
            print(f"   释放进度: {total_deleted}/{len(keys_list)} 个对象已从 Bucket 01 清理")
        else:
            print(f"⚠️ 释放批次异常: {r_del.text}")

    print(f"\n🎉 迁移与释放全部完成！累计平移并释放: {total_deleted} 个物理文件，释放体积: {total_bytes / 1000000000:.3f} GB！")

if __name__ == "__main__":
    main()
