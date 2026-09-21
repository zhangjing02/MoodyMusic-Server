#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计 Bucket 03, 04, 05, 06 的实际物理资产与 D1 数据库映射情况
"""
import os
import sys
import json
import boto3
import requests
from botocore.config import Config
from collections import defaultdict

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg_all = json.load(f)["buckets"]

print("📡 [1/2] 从 D1 网关获取全库曲目元数据...", flush=True)
d1_res = requests.get("https://m-api.changgepd.ccwu.cc/api/songs", timeout=30).json().get("data", [])

# 构建 D1 字典：key 是相对路径，value 是歌曲元数据
d1_map = {}
for art in d1_res:
    art_name = art.get("name")
    for alb in art.get("albums", []):
        alb_title = alb.get("title")
        for s in alb.get("songs", []):
            sid = s.get("id")
            path = s.get("path") or ""
            lrc = s.get("lrc") or ""
            if path:
                if ".r2.dev/" in path:
                    k = path.split(".r2.dev/")[1]
                elif "r2.changgepd.ccwu.cc/" in path:
                    k = path.split("r2.changgepd.ccwu.cc/")[1]
                else:
                    k = path.lstrip("/")
                d1_map[k] = {
                    "id": sid,
                    "title": s.get("title"),
                    "path": path,
                    "lrc": lrc,
                    "artist": art_name,
                    "album": alb_title
                }

print(f"   D1 索引构建完成，有效歌曲路径: {len(d1_map)} 条\n", flush=True)

buckets_to_audit = ["account_03", "account_04", "account_05", "account_06"]

for b_id in buckets_to_audit:
    cfg = cfg_all[b_id]
    b_name = cfg["name"]
    pub_url = cfg["public_url"]
    print("=" * 70, flush=True)
    print(f"🔍 审计存储桶: {b_id} ({b_name}) | 公网: {pub_url}", flush=True)
    print("=" * 70, flush=True)

    s3 = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4")
    )

    paginator = s3.get_paginator("list_objects_v2")
    artist_stats = defaultdict(lambda: {
        "mp3_count": 0,
        "lrc_count": 0,
        "bytes": 0,
        "d1_matched": 0,
        "d1_missing": 0,
        "d1_wrong_domain": 0
    })
    total_bytes = 0
    total_objects = 0

    for page in paginator.paginate(Bucket=b_name):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            sz = obj["Size"]
            total_bytes += sz
            total_objects += 1

            parts = k.split("/")
            if len(parts) >= 3 and parts[0] in ["music", "lyrics"]:
                artist = parts[1]
                if parts[0] == "music":
                    artist_stats[artist]["mp3_count"] += 1
                    if k in d1_map:
                        # 检查 D1 中的 path 是否包含当前桶的域名
                        if cfg["public_url"].replace("https://", "") in d1_map[k]["path"]:
                            artist_stats[artist]["d1_matched"] += 1
                        else:
                            artist_stats[artist]["d1_wrong_domain"] += 1
                    else:
                        artist_stats[artist]["d1_missing"] += 1
                else:
                    artist_stats[artist]["lrc_count"] += 1
                artist_stats[artist]["bytes"] += sz
            else:
                artist_stats["_OTHER_"]["bytes"] += sz
                artist_stats["_OTHER_"]["mp3_count"] += 1

    print(f"📊 物理总量: {total_bytes / 10**9:.3f} GB (10进制), {total_objects} 个对象")
    sorted_artists = sorted(artist_stats.items(), key=lambda x: x[1]["bytes"], reverse=True)
    print(f"   {'歌手':<10} | {'体积(MB)':>8} | {'MP3':>5} | {'D1精准匹配':>10} | {'D1指向它桶':>10} | {'D1无记录':>8} | {'LRC':>5}")
    print("   " + "-" * 68)
    for art, stat in sorted_artists[:15]:
        mb = stat["bytes"] / (10**6)
        print(f"   {art:<10} | {mb:8.1f} | {stat['mp3_count']:5d} | {stat['d1_matched']:10d} | {stat['d1_wrong_domain']:10d} | {stat['d1_missing']:8d} | {stat['lrc_count']:5d}")
    print("\n", flush=True)
