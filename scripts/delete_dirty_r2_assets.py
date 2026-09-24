#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 物理删除 R2 脏音频文件释放空间脚本
"""

import os
import sys
import json
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)["buckets"]

def get_s3_client(b_key):
    b_cfg = cfg[b_key]
    return boto3.client(
        "s3",
        endpoint_url=b_cfg["endpoint_url"],
        aws_access_key_id=b_cfg["access_key_id"],
        aws_secret_access_key=b_cfg["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4")
    ), b_cfg["name"]

TARGETS_TO_DELETE = [
    {
        "bucket_key": "account_06",
        "key": "music/王菲/將愛/s_24168.mp3",
        "desc": "王菲《MV》- 视频片头广告口播污染音轨"
    },
    {
        "bucket_key": "account_08",
        "key": "music/动力火车/结伴/s_25795.mp3",
        "desc": "动力火车《我这个你不爱的人》- Zither Harp古筝伴奏李鬼音轨"
    },
    {
        "bucket_key": "account_08",
        "key": "lyrics/动力火车/结伴/s_25795.lrc",
        "desc": "动力火车《我这个你不爱的人》- 脏歌词"
    }
]

def main():
    print("=" * 80)
    print("🗑️ 开始在 Cloudflare R2 中物理删除一级严重错误脏音频资产...")
    print("=" * 80)
    
    total_freed_bytes = 0
    clients = {}
    
    for item in TARGETS_TO_DELETE:
        b_key = item["bucket_key"]
        key = item["key"]
        desc = item["desc"]
        
        if b_key not in clients:
            clients[b_key] = get_s3_client(b_key)
            
        s3, bname = clients[b_key]
        
        # 1. 检查是否存在并获取大小
        try:
            head = s3.head_object(Bucket=bname, Key=key)
            size = head.get("ContentLength", 0)
            print(f"📦 发现目标脏资产: [{bname}] {key} ({size:,} 字节) - {desc}")
            
            # 2. 执行删除
            s3.delete_object(Bucket=bname, Key=key)
            print(f"   ✅ [删除成功] 物理已清除: {key}")
            total_freed_bytes += size
        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
                print(f"ℹ️ 目标在 [{bname}] 已不存在: {key}")
            else:
                print(f"❌ 访问异常 [{bname}] {key}: {e}")
                
    print("\n" + "=" * 80)
    print(f"🎉 物理清理完成！累计直接释放 R2 物理存储空间: {total_freed_bytes:,} 字节 ({total_freed_bytes/1000/1000:.2f} MB)")
    print("=" * 80)

if __name__ == "__main__":
    main()
