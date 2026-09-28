#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第一批 10 首曲目高保真正版歌词补全与上传点亮
"""
import os
import json
import boto3
import requests
from botocore.config import Config
from fetch_official_lyrics import fetch_clean_lrc

API_BASE = "https://m-api.changgepd.ccwu.cc"
ARTIST = "动力火车"
WORK_DIR = "/tmp/dongli_batch1_work"

with open("MoodyMusic-Server/r2_config.json", "r", encoding="utf-8") as f:
    all_cfg = json.load(f)
    r2_cfg = all_cfg["buckets"]["account_11"]

s3_client = boto3.client(
    service_name="s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, connect_timeout=15, read_timeout=30)
)
bucket_name = r2_cfg["name"]
public_base = r2_cfg["public_url"]

TARGET_SONGS = [
    {"id": 25758, "album": "无情的情书", "title": "不甘心不放手"},
    {"id": 25759, "album": "无情的情书", "title": "还隐隐作痛"},
    {"id": 25765, "album": "无情的情书", "title": "不只是"},
    {"id": 25764, "album": "无情的情书", "title": "Happy By Your Side"},
    {"id": 25707, "album": "再见我的爱人", "title": "再见我的爱人"},
    {"id": 25710, "album": "再见我的爱人", "title": "不会哭的人"},
    {"id": 25711, "album": "再见我的爱人", "title": "可不可能"},
    {"id": 25716, "album": "再见我的爱人", "title": "Bye Bye Subway"},
    {"id": 25737, "album": "MAN", "title": "潇洒的走"},
    {"id": 25740, "album": "继续转动", "title": "逆向行驶"},
    {"id": 25718, "album": "忠孝东路走九遍", "title": "酒醉的探戈2001"},
    {"id": 25745, "album": "继续转动", "title": "你是我的眼"}
]

updates = []
for item in TARGET_SONGS:
    sid = item["id"]
    alb = item["album"]
    tit = item["title"]

    lrc_text = fetch_clean_lrc(ARTIST, tit)
    if lrc_text:
        local_path = os.path.join(WORK_DIR, f"s_{sid}.lrc")
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(lrc_text)
        
        r2_key = f"lyrics/{ARTIST}/{alb}/s_{sid}.lrc"
        s3_client.upload_file(local_path, bucket_name, r2_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        lrc_url = f"{public_base}/{r2_key}"
        print(f"✅ [{sid}] {alb} - 《{tit}》 歌词已上传: {lrc_url}")
        updates.append({"id": sid, "lrc_path": lrc_url})
    else:
        print(f"⚠️ [{sid}] 未能获取歌词: 《{tit}》")

if updates:
    res = requests.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": updates}, timeout=15)
    print(f"batch-light 歌词点亮响应: HTTP {res.status_code} | {res.text}")
