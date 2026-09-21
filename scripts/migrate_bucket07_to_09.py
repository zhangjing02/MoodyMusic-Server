#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
Bucket 07 -> Bucket 09 资产平移与排雷降温流水线 (Zero-Loss Pipeline)
==============================================================================
平移歌手：苏慧伦 (Tarcy Su)
目标：将 Bucket 07 从 9.84 GB 压降至 ~9.20 GB，彻底消除 98.4% 扣费熔断风险
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

# Cloudflare 边缘 IP 直连
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

b07_info = r2_cfg["buckets"]["account_07"]
b09_info = r2_cfg["buckets"]["account_09"]

B07_NAME = b07_info["name"]
B09_NAME = b09_info["name"]
B09_DOMAIN = b09_info["public_url"].rstrip("/")

s3_b07 = boto3.client(
    "s3",
    endpoint_url=b07_info["endpoint_url"],
    aws_access_key_id=b07_info["access_key_id"],
    aws_secret_access_key=b07_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, signature_version="s3v4")
)

s3_b09 = boto3.client(
    "s3",
    endpoint_url=b09_info["endpoint_url"],
    aws_access_key_id=b09_info["access_key_id"],
    aws_secret_access_key=b09_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, signature_version="s3v4")
)

TARGET_ARTIST = "苏慧伦"
ARTIST_ID = 79

def scan_b07_artist_objects():
    """扫描 Bucket 07 中苏慧伦全部对象"""
    prefix = f"music/{TARGET_ARTIST}/"
    paginator = s3_b07.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=B07_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            objects.append({
                "key": obj["Key"],
                "size": obj["Size"]
            })
    return objects

def transfer_single_object(item):
    """单文件流式迁移并执行 S3 HEAD 强校验"""
    key = item["key"]
    expected_size = item["size"]

    # 1. 从 Bucket 07 读取
    try:
        resp = s3_b07.get_object(Bucket=B07_NAME, Key=key)
        data = resp["Body"].read()
        if len(data) != expected_size:
            return {"key": key, "success": False, "error": f"Size mismatch on read: got {len(data)}, expected {expected_size}"}
    except Exception as e:
        return {"key": key, "success": False, "error": f"Get from Bucket 07 failed: {e}"}

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

    # 3. S3 HEAD 字节强校验
    try:
        head = s3_b09.head_object(Bucket=B09_NAME, Key=key)
        if head.get("ContentLength") != expected_size:
            return {"key": key, "success": False, "error": f"Head ContentLength mismatch: got {head.get('ContentLength')}, expected {expected_size}"}
    except Exception as e:
        return {"key": key, "success": False, "error": f"Head on Bucket 09 failed: {e}"}

    return {"key": key, "success": True, "size": expected_size}

def get_artist_d1_songs():
    """通过专辑接口获取苏慧伦全部歌曲"""
    r_alb = requests.get(f"{BASE_URL}/api/admin/albums/search?artist_id={ARTIST_ID}&limit=100", timeout=15)
    r_alb.raise_for_status()
    albums = r_alb.json().get("data", {}).get("albums", [])
    
    all_songs = []
    for alb in albums:
        alb_id = alb["id"]
        r_det = requests.get(f"{BASE_URL}/api/admin/albums/detail?album_id={alb_id}", timeout=15)
        if r_det.status_code == 200:
            songs = r_det.json().get("data", {}).get("songs", [])
            all_songs.extend(songs)
    return all_songs

def clean_rel_path(p):
    if not p:
        return ""
    # 去除各种已有前缀
    for b in r2_cfg.get("buckets", {}).values():
        pub = b.get("public_url", "").rstrip("/")
        if pub and p.startswith(pub):
            p = p[len(pub):]
    if p.startswith("https://r2.changgepd.ccwu.cc"):
        p = p[len("https://r2.changgepd.ccwu.cc"):]
    if p.startswith("/"):
        p = p[1:]
    if p.startswith("storage/"):
        p = p[8:]
    return p

def main():
    print("=" * 80)
    print("🚀 启动 Bucket 07 -> Bucket 09 资产平移与降温流水线 (Zero-Loss)")
    print(f"🎯 目标平移歌手: {TARGET_ARTIST} (artist_id={ARTIST_ID})")
    print(f"📦 源桶: {B07_NAME} -> 目标桶: {B09_NAME}")
    print("=" * 80)

    # 1. 扫描 Bucket 07
    print(f"\n📡 [Step 1] 扫描 Bucket 07 中 [{TARGET_ARTIST}] 的全部对象...")
    items = scan_b07_artist_objects()
    total_files = len(items)
    total_bytes = sum(i["size"] for i in items)
    mp3_cnt = sum(1 for i in items if i["key"].endswith(".mp3"))
    lrc_cnt = sum(1 for i in items if i["key"].endswith(".lrc"))
    print(f"   共发现物理对象: {total_files} 个 (音频 .mp3: {mp3_cnt}, 歌词 .lrc: {lrc_cnt})")
    print(f"   总数据体积: {total_bytes / 1000000:.2f} MB ({total_bytes / 1000000000:.4f} GB)")

    if total_files == 0:
        print("❌ 未发现任何待平移对象，终止！")
        sys.exit(1)

    # 2. 并发流式传输并执行 S3 HEAD 强校验
    print(f"\n⚡ [Step 2 & 3] 开始高速流式传输至 Bucket 09 并执行 S3 HEAD 字节强校验...")
    start_time = time.time()
    success_keys = set()
    failed_items = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(transfer_single_object, item): item for item in items}
        done_cnt = 0
        for f in as_completed(futures):
            res = f.result()
            done_cnt += 1
            if res["success"]:
                success_keys.add(res["key"])
            else:
                failed_items.append(res)
            if done_cnt % 20 == 0 or done_cnt == total_files:
                pct = (done_cnt / total_files) * 100
                print(f"   进度: {done_cnt}/{total_files} ({pct:.1f}%) | 成功: {len(success_keys)} | 失败: {len(failed_items)}", flush=True)

    elapsed = time.time() - start_time
    print(f"   ✅ 传输与字节强核验完成！耗时: {elapsed:.2f} 秒, 成功: {len(success_keys)}/{total_files}")

    if failed_items:
        print(f"❌ 发现 {len(failed_items)} 个文件传输失败，出于 Zero-Loss 规范，立即终止！")
        for f in failed_items[:5]:
            print("   失败项:", f)
        sys.exit(1)

    # 3. D1 数据库原子切链
    print(f"\n⚡ [Step 4] 检索 D1 歌曲主键并执行原子切链 (POST /api/admin/songs/batch-light)...")
    songs = get_artist_d1_songs()
    print(f"   D1 中 [{TARGET_ARTIST}] 关联歌曲总数: {len(songs)} 首")

    songs_to_update = []
    for s in songs:
        sid = s["id"]
        rel_audio = clean_rel_path(s.get("file_path"))
        rel_lrc = clean_rel_path(s.get("lrc_path"))

        if rel_audio in success_keys:
            new_audio = f"{B09_DOMAIN}/{rel_audio}"
            new_lrc = f"{B09_DOMAIN}/{rel_lrc}" if rel_lrc and rel_lrc in success_keys else None
            songs_to_update.append({
                "id": sid,
                "file_path": new_audio,
                "lrc_path": new_lrc
            })

    print(f"   待切链点亮歌曲数: {len(songs_to_update)} 首")
    batch_size = 100
    for i in range(0, len(songs_to_update), batch_size):
        chunk = songs_to_update[i:i+batch_size]
        payload = {"updates": chunk}
        r_light = requests.post(f"{BASE_URL}/api/admin/songs/batch-light", json=payload, timeout=20)
        if r_light.status_code != 200:
            print(f"❌ D1 切链失败: {r_light.text}")
            sys.exit(1)
        print(f"   D1 切链进度: {min(i+batch_size, len(songs_to_update))}/{len(songs_to_update)} 完成", flush=True)

    print("   ✅ D1 数据库链接已 100% 切换至 Bucket 09！")

    # 4. 生产 CDN 抽检
    print(f"\n⚡ [Step 5] 生产 CDN 直链播放连通性抽验...")
    sample_mp3s = [k for k in success_keys if k.endswith(".mp3")][:5]
    for k in sample_mp3s:
        test_url = f"{B09_DOMAIN}/{k}"
        r_head = requests.head(test_url, timeout=10)
        print(f"   抽验 {k.split('/')[-1]}: HTTP {r_head.status_code} ({r_head.headers.get('Content-Length')} 字节)", flush=True)
        if r_head.status_code != 200:
            print(f"❌ CDN 抽验失败！停止释放源桶文件！")
            sys.exit(1)
    print("   ✅ 生产 CDN 抽验全部通过！")

    # 5. 安全释放 Bucket 07 源文件
    print(f"\n⚡ [Step 6] 安全释放 Bucket 07 中的源文件...")
    keys_to_delete = [{"Key": k} for k in success_keys]
    del_batch = 500
    total_deleted = 0
    for i in range(0, len(keys_to_delete), del_batch):
        chunk = keys_to_delete[i:i+del_batch]
        resp = s3_b07.delete_objects(
            Bucket=B07_NAME,
            Delete={"Objects": chunk, "Quiet": True}
        )
        total_deleted += len(chunk)
        print(f"   源桶释放进度: {total_deleted}/{len(keys_to_delete)} 个对象已从 Bucket 07 清理", flush=True)

    print(f"\n🎉 苏慧伦资产平移与释放圆满完成！已释放: {total_deleted} 个文件, 腾出空间: {total_bytes / 1000000:.2f} MB！")

if __name__ == "__main__":
    main()
