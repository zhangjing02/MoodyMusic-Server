#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - Bucket 07 / Bucket 08 真实物理资产绝对直链精准点亮脚本
==============================================================================
原则：
1. 只探查 Bucket 07 与 Bucket 08 真实存在的物理文件；
2. 命中 07/08 物理文件的曲目，补全为对应的 CDN 绝对公网直链并调用 batch-light；
3. 对第 1 存储桶的早期历史相对路径（周杰伦、孙燕姿、陈奕迅等）100% 保持原样，绝不置灰！
4. 绝不调用 batch-unlight！
==============================================================================
"""

import os
import sys
import json
import time
import re
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    R2_CFG = json.load(f)["buckets"]

b07 = R2_CFG['account_07']
b08 = R2_CFG['account_08']

s3_07 = boto3.client(
    's3', endpoint_url=b07['endpoint_url'],
    aws_access_key_id=b07['access_key_id'],
    aws_secret_access_key=b07['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4', connect_timeout=3, read_timeout=5, max_pool_connections=50)
)
name_07 = b07['name']
domain_07 = b07.get('public_url', b07.get('public_domain', '')).rstrip('/')

s3_08 = boto3.client(
    's3', endpoint_url=b08['endpoint_url'],
    aws_access_key_id=b08['access_key_id'],
    aws_secret_access_key=b08['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4', connect_timeout=3, read_timeout=5, max_pool_connections=50)
)
name_08 = b08['name']
domain_08 = b08.get('public_url', b08.get('public_domain', '')).rstrip('/')

def check_file(key: str) -> tuple:
    clean_key = key.lstrip('/')
    # 先查 07
    try:
        s3_07.head_object(Bucket=name_07, Key=clean_key)
        return 'account_07', domain_07
    except Exception:
        pass
    # 再查 08
    try:
        s3_08.head_object(Bucket=name_08, Key=clean_key)
        return 'account_08', domain_08
    except Exception:
        pass
    return None, None

def check_and_prepare(song: dict) -> dict:
    sid = song['id']
    p = song['path']
    lp = song['lrc_path']
    aname = song['artist']
    title = song['title']

    if not sid and p:
        m = re.search(r's_(\d+)\.(mp3|m4a)', p)
        if m:
            sid = int(m.group(1))

    if not sid or not p:
        return None

    # 如果音频已经是绝对链接，检查歌词是否需要补齐
    if p.startswith('http'):
        # 音频已是绝对直链
        abs_audio = p
        # 检查歌词
        abs_lrc = lp
        if lp and not lp.startswith('http') and lp.strip() not in ['', 'music/', 'lyrics/']:
            bkey, dom = check_file(lp)
            if bkey:
                abs_lrc = f"{dom}/{lp.lstrip('/')}"
        return None # 音频已正常，暂不作为重点
    else:
        # 音频是相对路径，探测其是否在 07 或 08 桶！
        bkey, dom = check_file(p)
        if bkey:
            abs_audio = f"{dom}/{p.lstrip('/')}"
            # 探测歌词
            abs_lrc = None
            if lp and lp.startswith('http'):
                abs_lrc = lp
            else:
                cand_lrc_keys = []
                if lp and lp.strip() not in ['', 'music/', 'lyrics/']:
                    cand_lrc_keys.append(lp.lstrip('/'))
                p_clean = p.lstrip('/')
                if p_clean.startswith('music/'):
                    cand_lrc_keys.append(p_clean.replace('music/', 'lyrics/', 1).rsplit('.', 1)[0] + '.lrc')
                    cand_lrc_keys.append(p_clean.rsplit('.', 1)[0] + '.lrc')

                for lk in cand_lrc_keys:
                    l_bkey, l_dom = check_file(lk)
                    if l_bkey:
                        abs_lrc = f"{l_dom}/{lk}"
                        break

            return {
                'id': sid,
                'artist': aname,
                'title': title,
                'file_path': abs_audio,
                'lrc_path': abs_lrc,
                'bucket': bkey
            }

    return None

def main():
    print("=" * 80)
    print("🎯 MOODY - Bucket 07 / 08 相对路径定向绝对直链点亮流水线")
    print("=" * 80)

    print("\n[1/3] 从生产网关拉取全库数据...")
    resp = requests.get(D1_SONGS_URL, timeout=30)
    data = resp.json().get('data', [])

    candidates = []
    for art in data:
        aname = art.get('name')
        for alb in art.get('albums', []):
            albtitle = alb.get('title')
            for s in alb.get('songs', []):
                p = s.get('path')
                if p and not p.startswith('http'):
                    candidates.append({
                        'id': s.get('id'),
                        'artist': aname,
                        'album': albtitle,
                        'title': s.get('title'),
                        'path': p,
                        'lrc_path': s.get('lrc_path')
                    })

    print(f" • 相对路径候选曲目: {len(candidates)} 首")

    print("\n[2/3] 并发探查在 Bucket 07 与 Bucket 08 的真实物理归属...")
    to_light = []
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(check_and_prepare, c): c for c in candidates}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                to_light.append(res)

    print(f"\n📊 探查完成! 在 Bucket 07/08 中确认有物理文件的曲目: {len(to_light)} 首")
    by_art = {}
    for item in to_light:
        a = item['artist']
        by_art[a] = by_art.get(a, 0) + 1
    for a, c in sorted(by_art.items(), key=lambda x: x[1], reverse=True):
        print(f"   • {a}: {c} 首")

    # 3. 提交 batch-light
    print(f"\n[3/3] 正在向 Cloudflare D1 批量提交绝对直链点亮 ({len(to_light)} 首)...")
    chunk_size = 50
    success = 0
    for i in range(0, len(to_light), chunk_size):
        chunk = to_light[i:i + chunk_size]
        payload = {
            "updates": [{
                "id": item['id'],
                "file_path": item['file_path'],
                "lrc_path": item['lrc_path']
            } for item in chunk]
        }
        for retry in range(3):
            try:
                res = requests.post(D1_LIGHT_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=20)
                if res.status_code == 200 and res.json().get('code') == 200:
                    success += len(chunk)
                    print(f"   • batch-light [{min(i + chunk_size, len(to_light))}/{len(to_light)}] 成功! (累积: {success})")
                    break
            except Exception:
                time.sleep(1)
        time.sleep(0.3)

    print("\n" + "=" * 80)
    print(f"🏁 Bucket 07 / 08 绝对直链点亮完成: 成功 {success} / {len(to_light)} 首")
    print("   注意：第 1 桶的早期历史相对路径（周杰伦、孙燕姿等）100% 完整保留，未做任何置灰！")
    print("=" * 80)

if __name__ == "__main__":
    main()
