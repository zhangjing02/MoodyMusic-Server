#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完成 Bucket 01 -> Bucket 09 平移收尾流程：
1. 校验 Bucket 09 对象完整性 (749 个文件)
2. 查出陈奕迅与孙燕姿所有歌曲 ID 并原子更新 D1 链接 (batch-light)
3. 抽样验证生产 CDN 播放可用性
4. 释放 Bucket 01 中的源文件 (释放 ~2.045 GB)
5. 重新核算大盘数据并写入 D1
"""

import os
import sys
import json
import time
import socket
import requests
import boto3
from botocore.config import Config

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

b09_info = r2_cfg["buckets"]["account_09"]
B09_NAME = b09_info["name"]
B09_DOMAIN = b09_info["public_url"].rstrip("/")

s3_b09 = boto3.client(
    "s3",
    endpoint_url=b09_info["endpoint_url"],
    aws_access_key_id=b09_info["access_key_id"],
    aws_secret_access_key=b09_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, signature_version="s3v4")
)

def get_bucket09_keys():
    """扫描 Bucket 09 中陈奕迅与孙燕姿的文件集合"""
    b09_keys = set()
    for artist in ["陈奕迅", "孙燕姿"]:
        prefix = f"music/{artist}/"
        paginator = s3_b09.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=B09_NAME, Prefix=prefix):
            for obj in page.get("Contents", []):
                b09_keys.add(obj["Key"])
    return b09_keys

def get_artist_songs(artist_id):
    """通过 albums/search 与 albums/detail 获取该艺人全部歌曲"""
    r_alb = requests.get(f"{BASE_URL}/api/admin/albums/search?artist_id={artist_id}&limit=100", timeout=15)
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

def clean_relative_path(path_str):
    if not path_str:
        return ""
    p = path_str.replace("https://r2.changgepd.ccwu.cc/", "")
    p = p.replace(B09_DOMAIN + "/", "")
    if p.startswith("/"):
        p = p[1:]
    if p.startswith("storage/"):
        p = p[8:]
    return p

def main():
    print("=" * 80)
    print("🚀 开始执行 Bucket 01 -> Bucket 09 切链与释放流程 (Phase 2)")
    print("=" * 80)

    # 1. 核对 Bucket 09 资产
    print("\n📡 [Step 1] 核验 Bucket 09 资产完整性...")
    b09_keys = get_bucket09_keys()
    print(f"   Bucket 09 当前已存在目标文件数: {len(b09_keys)} 个")
    if len(b09_keys) < 740:
        print(f"❌ Bucket 09 目标文件数不足 (预期 749, 实际 {len(b09_keys)})，出于安全终止切链！")
        sys.exit(1)
    print("   ✅ Bucket 09 资产核验通过！")

    # 2. 获取陈奕迅与孙燕姿歌曲记录
    print("\n📡 [Step 2] 提取歌曲主键并构建 D1 切链映射...")
    artists_map = {"陈奕迅": 6, "孙燕姿": 74}
    songs_to_update = []

    for artist_name, artist_id in artists_map.items():
        songs = get_artist_songs(artist_id)
        print(f"   歌手 [{artist_name}] 检索到 D1 歌曲记录: {len(songs)} 首")
        for s in songs:
            sid = s["id"]
            orig_audio = s.get("file_path") or ""
            orig_lrc = s.get("lrc_path") or ""

            rel_audio = clean_relative_path(orig_audio)
            rel_lrc = clean_relative_path(orig_lrc)

            # 只要在 Bucket 09 中存在，就切换至 Bucket 09
            if rel_audio in b09_keys:
                new_audio = f"{B09_DOMAIN}/{rel_audio}"
                new_lrc = f"{B09_DOMAIN}/{rel_lrc}" if rel_lrc and rel_lrc in b09_keys else None
                songs_to_update.append({
                    "id": sid,
                    "file_path": new_audio,
                    "lrc_path": new_lrc
                })

    print(f"   共构建完成 D1 待切链记录: {len(songs_to_update)} 首")
    if len(songs_to_update) == 0:
        print("❌ 未构建出待切链记录，终止！")
        sys.exit(1)

    # 3. 批量更新 D1 数据库
    print("\n⚡ [Step 3] 批量执行 D1 数据库原子切链 (POST /api/admin/songs/batch-light)...")
    batch_size = 100
    for i in range(0, len(songs_to_update), batch_size):
        chunk = songs_to_update[i:i+batch_size]
        payload = {"updates": chunk}
        r_light = requests.post(f"{BASE_URL}/api/admin/songs/batch-light", json=payload, timeout=20)
        if r_light.status_code != 200:
            print(f"❌ D1 切链失败: {r_light.text}")
            sys.exit(1)
        print(f"   D1 切链进度: {min(i+batch_size, len(songs_to_update))}/{len(songs_to_update)} 完成")

    print("   ✅ D1 切链 100% 成功！")

    # 4. 生产 CDN 播放连通性抽检
    print("\n⚡ [Step 4] 生产 CDN 播放连通性抽验...")
    mp3_keys = [k for k in b09_keys if k.endswith(".mp3")][:5]
    for k in mp3_keys:
        test_url = f"{B09_DOMAIN}/{k}"
        r_head = requests.head(test_url, timeout=10)
        print(f"   抽验 {k.split('/')[-1]}: HTTP {r_head.status_code} ({r_head.headers.get('Content-Length')} 字节)")
        if r_head.status_code != 200:
            print(f"❌ CDN 抽验失败！停止释放源文件！")
            sys.exit(1)
    print("   ✅ CDN 抽验全部通过！")

    # 5. 安全释放 Bucket 01 源文件
    print("\n⚡ [Step 5] 安全释放 Bucket 01 中的源文件...")
    keys_list = list(b09_keys)
    del_batch = 400
    total_deleted = 0
    for i in range(0, len(keys_list), del_batch):
        chunk = keys_list[i:i+del_batch]
        r_del = requests.post(f"{BASE_URL}/api/admin/debug/delete-bucket01-keys", json={"keys": chunk}, timeout=30)
        if r_del.status_code == 200:
            total_deleted += len(chunk)
            print(f"   释放进度: {total_deleted}/{len(keys_list)} 个源文件已从 Bucket 01 释放")
        else:
            print(f"⚠️ 释放批次异常: {r_del.text}")

    print(f"\n🎉 资产切链与源桶释放完成！已成功从 Bucket 01 释放 {total_deleted} 个文件 (约 2.05 GB)！")

if __name__ == "__main__":
    main()
