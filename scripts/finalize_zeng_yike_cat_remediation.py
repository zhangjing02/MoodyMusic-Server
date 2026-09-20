#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - 曾轶可《一只猫的旅行》全专 8 首最终母带合流与 D1 生产网关点亮
==============================================================================
"""

import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
TMP_DIR = "/tmp/remediate_zeng_yike_cat"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]["account_07"]

s3_client = boto3.client(
    's3',
    endpoint_url=r2_cfg['endpoint_url'],
    aws_access_key_id=r2_cfg['access_key_id'],
    aws_secret_access_key=r2_cfg['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4')
)
BUCKET_NAME = r2_cfg['name']
PUBLIC_DOMAIN = r2_cfg.get('public_url', r2_cfg.get('public_domain', '')).rstrip('/')
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

def main():
    print("=" * 80)
    print("🚀 [Step 1] 重制并替换第 8 首《羽绒服》(28810) 为 YouTube 官方曾轶可原版母带...")
    print("=" * 80)
    
    raw_m4a = "/tmp/yt_yu_rong_fu.m4a"
    norm_mp3 = os.path.join(TMP_DIR, "s_28810.mp3")
    
    # 压制 EBU R128 + 160k CBR Xing
    cmd = [
        "ffmpeg", "-y", "-i", raw_m4a,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k",
        "-write_xing", "1",
        norm_mp3
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 上传至 Bucket 07
    r2_key = "music/曾轶可/一只猫的旅行/s_28810.mp3"
    s3_client.upload_file(norm_mp3, BUCKET_NAME, r2_key, ExtraArgs={'ContentType': 'audio/mpeg'})
    print(f"✅ 《羽绒服》曾轶可真唱母带已物理覆盖 R2: {PUBLIC_DOMAIN}/{r2_key}")
    
    print("\n" + "=" * 80)
    print("🚀 [Step 2] 汇总整专全部 8 首重制曲目，调用 D1 batch-light 点亮...")
    print("=" * 80)
    
    target_ids = [28797, 28800, 28801, 28802, 28804, 28806, 28808, 28810]
    
    updates = []
    for sid in target_ids:
        audio_url = f"{PUBLIC_DOMAIN}/music/曾轶可/一只猫的旅行/s_{sid}.mp3"
        lrc_url = f"{PUBLIC_DOMAIN}/lyrics/曾轶可/一只猫的旅行/s_{sid}.lrc"
        updates.append({
            "id": sid,
            "file_path": audio_url,
            "lrc_path": lrc_url
        })
        
    payload = {"updates": updates}
    headers = {"Content-Type": "application/json"}
    resp = requests.post(D1_LIGHT_URL, json=payload, headers=headers, timeout=20)
    
    print(f"HTTP Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200 and resp.json().get('code') in [0, 200]:
        print("\n🎉🎉🎉 曾轶可《一只猫的旅行》全部 8 首异常曲目已全部重制并点亮成功！")
    else:
        print("\n⚠️ 点亮可能存在异常，请检查响应内容")

if __name__ == "__main__":
    main()
