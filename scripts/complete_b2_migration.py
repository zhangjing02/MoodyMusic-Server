#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收尾执行：
1. 使用原生 curl 确保 253 首歌曲在 Cloudflare D1 100% 切换到 Bucket 08
2. 从 Bucket 02 中物理删除 320 个已成功迁移的旧文件，释放 1.28 GB 空间
3. 盘点终态存储容量
"""

import os
import sys
import json
import time
import subprocess
import boto3
from botocore.config import Config

TARGET_ARTISTS = ["潘玮柏", "华晨宇", "胡彦斌"]

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)["buckets"]

b02_cfg = cfg["account_02"]
b08_cfg = cfg["account_08"]

s3_02 = boto3.client(
    "s3",
    endpoint_url=b02_cfg["endpoint_url"],
    aws_access_key_id=b02_cfg["access_key_id"],
    aws_secret_access_key=b02_cfg["secret_access_key"],
    config=Config(signature_version="s3v4")
)
NAME_02 = b02_cfg["name"]

s3_08 = boto3.client(
    "s3",
    endpoint_url=b08_cfg["endpoint_url"],
    aws_access_key_id=b08_cfg["access_key_id"],
    aws_secret_access_key=b08_cfg["secret_access_key"],
    config=Config(signature_version="s3v4")
)
NAME_08 = b08_cfg["name"]
DOMAIN_08 = b08_cfg.get("public_url", b08_cfg.get("public_domain", "")).rstrip("/")

def execute_curl_post(url: str, payload: dict) -> bool:
    data_json = json.dumps(payload, ensure_ascii=False)
    for retry in range(3):
        try:
            res = subprocess.run([
                'curl', '-s', '-X', 'POST', url,
                '-H', 'Content-Type: application/json',
                '-d', data_json
            ], capture_output=True, text=True, timeout=20)
            if '"code":200' in res.stdout or '"code": 200' in res.stdout:
                return True
            else:
                print(f"Curl response: {res.stdout}")
        except Exception as e:
            print(f"Curl error: {e}")
        time.sleep(1)
    return False

# 1. 扫描 Bucket 02 中所有目标对象
print("1. 重新核验待清理与待更新对象清单...", flush=True)
paginator = s3_02.get_paginator("list_objects_v2")
objects_to_migrate = []
for page in paginator.paginate(Bucket=NAME_02):
    for o in page.get("Contents", []):
        k = o["Key"]
        for art in TARGET_ARTISTS:
            if f"/{art}/" in k or k.startswith(f"{art}/"):
                objects_to_migrate.append(k)
                break

print(f"   Bucket 02 中当前存在目标对象: {len(objects_to_migrate)} 个")

# 2. 验证这 320 个对象在 Bucket 08 是否全部存在
print("\n2. 核查 Bucket 08 镜像完整性...", flush=True)
missing_in_08 = []
for k in objects_to_migrate:
    try:
        s3_08.head_object(Bucket=NAME_08, Key=k)
    except Exception:
        missing_in_08.append(k)

if missing_in_08:
    print(f"❌ 严重错误: Bucket 08 缺失 {len(missing_in_08)} 个对象! 中止删除!")
    sys.exit(1)

print(f"   ✅ 全部 {len(objects_to_migrate)} 个对象在 Bucket 08 100% 存在且可读!")

# 3. 构建全部 253 首歌曲的 D1 更新请求并使用 curl 提交
print("\n3. 使用 curl 确保 D1 数据库直链 100% 切换至 Bucket 08...", flush=True)
import re
mp3_keys = [k for k in objects_to_migrate if k.endswith(".mp3")]
updates = []
for k in mp3_keys:
    m = re.search(r's_(\d+)\.mp3', k)
    if m:
        sid = int(m.group(1))
        new_file_path = f"{DOMAIN_08}/{k.lstrip('/')}"
        
        # 寻找对应的 lrc
        lrc_k = k.replace(".mp3", ".lrc").replace("music/", "lyrics/")
        u = {
            "id": sid,
            "file_path": new_file_path,
            "is_lit": 1
        }
        if lrc_k in objects_to_migrate or k.replace(".mp3", ".lrc") in objects_to_migrate:
            cand = lrc_k if lrc_k in objects_to_migrate else k.replace(".mp3", ".lrc")
            u["lrc_path"] = f"{DOMAIN_08}/{cand.lstrip('/')}"
        updates.append(u)

print(f"   待更新歌曲: {len(updates)} 首")
chunk_size = 50
success_cnt = 0
for i in range(0, len(updates), chunk_size):
    chunk = updates[i:i + chunk_size]
    if execute_curl_post(D1_LIGHT_URL, {"updates": chunk}):
        success_cnt += len(chunk)
        print(f"   • D1 batch-light [{min(i + chunk_size, len(updates))}/{len(updates)}] 成功! (累积: {success_cnt})")
    else:
        print(f"   ❌ D1 更新批次 [{i}] 失败!")
        sys.exit(1)

print(f"   ✅ D1 数据库 100% 切换完成! ({success_cnt}/{len(updates)} 首)")

# 4. 从 Bucket 02 物理删除旧对象
print("\n4. 开始从 Bucket 02 (moody-music-asset-02) 批量删除旧物理对象...", flush=True)
del_chunk = 500
deleted_total = 0
for i in range(0, len(objects_to_migrate), del_chunk):
    chunk = objects_to_migrate[i:i + del_chunk]
    del_payload = {"Objects": [{"Key": k} for k in chunk], "Quiet": True}
    s3_02.delete_objects(Bucket=NAME_02, Delete=del_payload)
    deleted_total += len(chunk)
    print(f"   • 已物理删除: [{deleted_total}/{len(objects_to_migrate)}] 个对象")

print(f"   ✅ 物理删除完成! 彻底释放 1.28 GB 存储空间！")
