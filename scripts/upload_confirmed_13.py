#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上传并点亮经肉眼与听音文本严格复核无误的 13 首高难度歌曲（100% 写入 Bucket 08）
"""

import os
import json
import boto3
import subprocess
import requests
from botocore.config import Config

with open("r2_config.json", "r") as f:
    cfg = json.load(f)["buckets"]["account_08"]

s3 = boto3.client(
    "s3",
    endpoint_url=cfg["endpoint_url"],
    aws_access_key_id=cfg["access_key_id"],
    aws_secret_access_key=cfg["secret_access_key"],
    config=Config(signature_version="s3v4")
)
B08_NAME = cfg["name"]
B08_DOMAIN = cfg["public_url"].rstrip("/")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

confirmed_ids = [
    # Package A
    (2238, '崔健', '新长征路上的摇滚', '假行僧', 'package_a'),
    (2229, '崔健', '红旗下的蛋', '北京故事', 'package_a'),
    # Package B
    (24534, '张学友', '走过1999', '坏x5 (坏坏坏坏坏)', 'package_b'),
    (24538, '张学友', '走过1999', '认错', 'package_b'),
    (11277, '梁静茹', '親親', '憨過頭', 'package_b'),
    # Package C
    (21632, '张惠妹', '阿密特意識專輯', '好膽你就來', 'package_c'),
    (24007, '王菲', '王靖雯', '害怕', 'package_c'),
    (24011, '王菲', 'Everything', '無理取鬧', 'package_c'),
    (24070, '王菲', '迷', '從下世紀欣賞我', 'package_c'),
    (24073, '王菲', '迷', '從明日開始', 'package_c'),
    (15902, '田馥甄', 'To Hebe', 'Going Nowhere', 'package_c'),
    (15881, '田馥甄', '渺小', 'The Most Important Thing in Life', 'package_c'),
    (15882, '田馥甄', '渺小', 'Learning From Drunk', 'package_c')
]

d1_updates = []
for sid, art, alb, title, pkg in confirmed_ids:
    mp3 = f'/tmp/moody_remediate_{pkg}/s_{sid}.mp3'
    lrc = f'/tmp/moody_remediate_{pkg}/s_{sid}.lrc'
    
    key_audio = f"music/{art}/{alb}/s_{sid}.mp3"
    key_lrc = f"lyrics/{art}/{alb}/s_{sid}.lrc"
    
    print(f"Uploading [{art}] 《{alb}》 - 《{title}》 (ID {sid}) to account_08...")
    s3.upload_file(mp3, B08_NAME, key_audio, ExtraArgs={"ContentType": "audio/mpeg"})
    s3.upload_file(lrc, B08_NAME, key_lrc, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
    
    # 获取时长
    dur_raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", mp3
    ]).decode().strip()
    dur = round(float(dur_raw))
    
    d1_updates.append({
        "id": sid,
        "file_path": f"{B08_DOMAIN}/{key_audio}",
        "lrc_path": f"{B08_DOMAIN}/{key_lrc}",
        "duration": dur,
        "is_lit": 1
    })

print(f"\nSubmitting {len(d1_updates)} songs to D1 batch-light...")
r = requests.post(D1_LIGHT_URL, json={"updates": d1_updates}, timeout=25)
print(f"D1 response: {r.status_code} | {r.text}")
