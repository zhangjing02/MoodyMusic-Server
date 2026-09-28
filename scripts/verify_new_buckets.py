#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 Cloudflare R2 新增存储桶 (Bucket 13 & 14) 全链路读写及公网 CDN 连通性
"""

import boto3
from botocore.config import Config
import requests

import json
import os

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "r2_config.json"))
if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(f"未找到配置文件: {CONFIG_PATH}")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

buckets = []
for acc_key in ["account_13", "account_14"]:
    if acc_key in cfg.get("buckets", {}):
        item = cfg["buckets"][acc_key]
        buckets.append({
            "id": int(acc_key.replace("account_", "")),
            "name": item["name"],
            "email": item.get("email", ""),
            "acc_id": item["account_id"],
            "endpoint": item["endpoint_url"],
            "ak": item["access_key_id"],
            "sk": item["secret_access_key"],
            "pub": item["public_url"],
            "token": item.get("token", "")
        })

print("=" * 80)
print("🚀 启动新增存储桶 (Bucket 13 & 14) 全链路可用性与读写探针验证")
print("=" * 80)

for b in buckets:
    bid = b["id"]
    bname = b["name"]
    print(f"\n📦 [测试开始] Bucket {bid}: {bname} ({b['email']})")
    print(f" • Endpoint: {b['endpoint']}")
    print(f" • Public CDN: {b['pub']}")

    s3 = boto3.client(
        "s3",
        endpoint_url=b["endpoint"],
        aws_access_key_id=b["ak"],
        aws_secret_access_key=b["sk"],
        region_name="auto",
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4", connect_timeout=5, read_timeout=10)
    )

    # 1. List
    try:
        res = s3.list_objects_v2(Bucket=bname)
        cnt = res.get("KeyCount", 0)
        print(f" ✅ 1. S3 ListObjects 成功: 当前包含 {cnt} 个对象")
    except Exception as e:
        print(f" ❌ 1. S3 ListObjects 失败: {e}")

    # 2. Put
    probe_key = f"health_probe_{bid}.txt"
    probe_content = f"MOODY R2 Probe Test for Bucket {bid} - OK".encode("utf-8")
    try:
        s3.put_object(Bucket=bname, Key=probe_key, Body=probe_content, ContentType="text/plain")
        print(f" ✅ 2. S3 PutObject 写入成功: Key = {probe_key}")
    except Exception as e:
        print(f" ❌ 2. S3 PutObject 写入失败: {e}")

    # 3. Public CDN HTTP GET
    pub_url = f"{b['pub']}/{probe_key}"
    try:
        r = requests.get(pub_url, timeout=10)
        if r.status_code == 200 and r.content == probe_content:
            print(f" ✅ 3. 公网 r2.dev CDN 访问成功: HTTP 200, 内容 100% 校验吻合 ({pub_url})")
        else:
            print(f" ❌ 3. 公网 CDN 异常: HTTP {r.status_code}, 内容: {r.text[:60]}")
    except Exception as e:
        print(f" ❌ 3. 公网 CDN 请求异常: {e}")

    # 4. Clean up probe object
    try:
        s3.delete_object(Bucket=bname, Key=probe_key)
        print(f" ✅ 4. S3 DeleteObject 探测文件释放成功")
    except Exception as e:
        print(f" ❌ 4. S3 DeleteObject 失败: {e}")

    # 5. Cloudflare REST API usage endpoint
    try:
        r_cf = requests.get(
            f"https://api.cloudflare.com/client/v4/accounts/{b['acc_id']}/r2/buckets/{bname}/usage",
            headers={"Authorization": f"Bearer {b['token']}", "Content-Type": "application/json"},
            timeout=8
        )
        data = r_cf.json()
        if data.get("success"):
            print(f" ✅ 5. Cloudflare REST API Token 验证成功: usage 接口鉴权通过")
        else:
            print(f" ⚠️ 5. Cloudflare REST API 返回失败: {data.get('errors')}")
    except Exception as e:
        print(f" ⚠️ 5. Cloudflare REST API 异常: {e}")

print("\n" + "=" * 80)
print("🎉 存储桶 13 & 14 探针测试流程结束")
print("=" * 80)
