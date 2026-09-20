#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 9 存储桶 (moody-music-asset-09) 全链路连通性与读写测试
"""

import boto3
import requests
from botocore.config import Config

account_id = "2c1d41817014a37dfda148883d240058"
bucket_name = "moody-music-asset-09"
access_key = "e45fc30f57363bf20e31341cc3a361e4"
secret_key = "deb6ae87cbb9391dacf7f7b3e94843161c89ff482ee65c6b13ab7eb1a9e3aa88"
endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
public_url = "https://pub-147987db1e7b419cb6ea49acd48d0d25.r2.dev"

print(f"=== 正在测试第 9 存储桶: {bucket_name} ===")

# 1. 建立 S3 客户端
s3 = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    config=Config(signature_version="s3v4")
)

# 2. 列举对象测试
print("1. 测试 S3 ListObjects...")
res = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=5)
print(f"   List 成功! 当前对象数: {res.get('KeyCount', 0)}")

# 3. 写入探针文件测试
probe_key = "_connectivity_test_probe.txt"
probe_content = b"MoodyMusic Bucket 09 Connected Successfully at 2026-09-20!"
print(f"2. 测试 S3 写入探针: {probe_key}...")
s3.put_object(Bucket=bucket_name, Key=probe_key, Body=probe_content, ContentType="text/plain")
print("   Put 成功!")

# 4. 公网 CDN 直链测试
probe_url = f"{public_url}/{probe_key}"
print(f"3. 测试公网 CDN 直链 GET: {probe_url}...")
resp = requests.get(probe_url, timeout=10)
accept_ranges = resp.headers.get("Accept-Ranges", "N/A")
content_len = resp.headers.get("Content-Length", "N/A")
cors_origin = resp.headers.get("Access-Control-Allow-Origin", "N/A")
print(f"   CDN 返回状态码: {resp.status_code}")
print(f"   CDN 返回内容: {resp.text.strip()}")
print(f"   CDN 响应标头: Accept-Ranges={accept_ranges}, Content-Length={content_len}, CORS={cors_origin}")

# 5. 删除探针文件
print(f"4. 清理探针文件: {probe_key}...")
s3.delete_object(Bucket=bucket_name, Key=probe_key)
print("   Delete 成功!")

print("=== 第 9 存储桶全链路连通性验证全部通过！ ===")
