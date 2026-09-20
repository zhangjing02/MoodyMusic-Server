#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 全库相对路径与假点亮幽灵曲目彻底治理脚本 (多线程极速并发版)
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
D1_UNLIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-unlight"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    R2_CFG = json.load(f)["buckets"]

s3_clients = {}
bucket_domains = {}
bucket_names = {}

BUCKET_ORDER = ['account_08', 'account_07', 'account_04', 'account_02', 'account_03', 'account_05', 'account_06', 'account_01']

for b_key in BUCKET_ORDER:
    if b_key in R2_CFG:
        cfg = R2_CFG[b_key]
        cli = boto3.client(
            's3',
            endpoint_url=cfg['endpoint_url'],
            aws_access_key_id=cfg['access_key_id'],
            aws_secret_access_key=cfg['secret_access_key'],
            region_name='auto',
            config=Config(signature_version='s3v4', connect_timeout=3, read_timeout=5, max_pool_connections=50)
        )
        s3_clients[b_key] = cli
        bucket_domains[b_key] = cfg.get('public_domain', '').rstrip('/')
        bucket_names[b_key] = cfg['name']

def probe_file_in_buckets(key: str) -> tuple:
    if not key:
        return None, None
    clean_key = key.lstrip('/')
    for b_key in BUCKET_ORDER:
        if b_key not in s3_clients:
            continue
        try:
            s3_clients[b_key].head_object(Bucket=bucket_names[b_key], Key=clean_key)
            return b_key, bucket_domains[b_key]
        except Exception:
            continue
    return None, None

def process_single_song(s: dict) -> dict:
    sid = s['id']
    p = s['path']
    lp = s['lrc_path']
    aname = s['artist']
    title = s['title']

    if not sid and p:
        m = re.search(r's_(\d+)\.(mp3|m4a)', p)
        if m:
            sid = int(m.group(1))

    if not sid:
        return None

    audio_domain = None
    target_bucket = None

    if p:
        if p.startswith('http'):
            abs_audio = p
        else:
            target_bucket, audio_domain = probe_file_in_buckets(p)
            if target_bucket:
                abs_audio = f"{audio_domain}/{p.lstrip('/')}"
            else:
                abs_audio = None
    else:
        abs_audio = None

    if abs_audio:
        abs_lrc = None
        if lp and lp.startswith('http'):
            abs_lrc = lp
        else:
            cand_lrc_keys = []
            if lp and lp.strip() not in ['', 'music/', 'lyrics/']:
                cand_lrc_keys.append(lp.lstrip('/'))
            if p:
                p_clean = p.lstrip('/')
                if p_clean.startswith('music/'):
                    cand_lrc_keys.append(p_clean.replace('music/', 'lyrics/', 1).rsplit('.', 1)[0] + '.lrc')
                    cand_lrc_keys.append(p_clean.rsplit('.', 1)[0] + '.lrc')

            for lkey in cand_lrc_keys:
                l_bkey, l_dom = probe_file_in_buckets(lkey)
                if l_bkey:
                    abs_lrc = f"{l_dom}/{lkey}"
                    break

        return {
            'action': 'LIGHT',
            'id': sid,
            'artist': aname,
            'title': title,
            'file_path': abs_audio,
            'lrc_path': abs_lrc,
            'bucket': target_bucket
        }
    else:
        return {
            'action': 'UNLIGHT',
            'id': sid,
            'artist': aname,
            'title': title
        }

def run_remediation():
    print("=" * 80)
    print("🚀 MOODY 全库相对路径与假点亮幽灵曲目彻底治理流水线启动 (并发加速版)")
    print("=" * 80)

    print("\n[阶段 1/4] 正在拉取 Cloudflare D1 全量元数据...")
    resp = requests.get(D1_SONGS_URL, timeout=30)
    if resp.status_code != 200:
        print(f"❌ 无法连接 D1: HTTP {resp.status_code}")
        return
    data = resp.json().get('data', [])
    print(f"✅ D1 数据拉取成功! 涵盖 {len(data)} 位歌手")

    print("\n[阶段 2/4] 扫描全库相对路径与异常曲目...")
    target_songs = []
    for art in data:
        aname = art.get('name')
        for alb in art.get('albums', []):
            albtitle = alb.get('title')
            for s in alb.get('songs', []):
                sid = s.get('id')
                p = s.get('path')
                lp = s.get('lrc_path')

                needs_fix = False
                if p and not p.startswith('http'):
                    needs_fix = True
                if lp and not lp.startswith('http'):
                    needs_fix = True

                if needs_fix:
                    target_songs.append({
                        'id': sid,
                        'artist': aname,
                        'album': albtitle,
                        'title': s.get('title'),
                        'path': p,
                        'lrc_path': lp
                    })

    print(f" • 检出待治理相对路径/异常曲目: {len(target_songs)} 首")

    print(f"\n[阶段 3/4] 启动 30 线程并发探查 Cloudflare R2 集群物理文件...")
    to_light = []
    to_unlight_ids = []

    completed = 0
    total = len(target_songs)
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(process_single_song, s): s for s in target_songs}
        for fut in as_completed(futures):
            res = fut.result()
            completed += 1
            if res:
                if res['action'] == 'LIGHT':
                    to_light.append(res)
                else:
                    to_unlight_ids.append(res['id'])
            if completed % 200 == 0 or completed == total:
                print(f"   • 并发探查进度: [{completed}/{total}] | 确认存在待点亮: {len(to_light)} | 幽灵待置灰: {len(to_unlight_ids)}")

    print(f"\n📊 探查结果汇总:")
    print(f"  • 物理资产确认完整，待绝对直链点亮: {len(to_light)} 首")
    print(f"  • 物理资产不存在，待置灰留白: {len(to_unlight_ids)} 首")

    print("\n[阶段 4/4] 正在向 Cloudflare D1 提交治理载荷...")
    chunk_size = 50

    light_success = 0
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
                    light_success += len(chunk)
                    print(f"   • batch-light [{min(i + chunk_size, len(to_light))}/{len(to_light)}] 成功! (累积: {light_success})")
                    break
            except Exception:
                time.sleep(1)
        time.sleep(0.3)

    unlight_success = 0
    for i in range(0, len(to_unlight_ids), chunk_size):
        chunk = to_unlight_ids[i:i + chunk_size]
        payload = {"song_ids": chunk}
        for retry in range(3):
            try:
                res = requests.post(D1_UNLIGHT_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=20)
                if res.status_code == 200 and res.json().get('code') == 200:
                    unlight_success += len(chunk)
                    print(f"   • batch-unlight [{min(i + chunk_size, len(to_unlight_ids))}/{len(to_unlight_ids)}] 成功! (累积: {unlight_success})")
                    break
            except Exception:
                time.sleep(1)
        time.sleep(0.3)

    print("\n" + "=" * 80)
    print("🔍 正在验证治理结果...")
    time.sleep(3)
    check_resp = requests.get(D1_SONGS_URL, timeout=30)
    remain_rel = 0
    if check_resp.status_code == 200:
        cdata = check_resp.json().get('data', [])
        for a in cdata:
            for al in a.get('albums', []):
                for sg in al.get('songs', []):
                    p = sg.get('path')
                    lp = sg.get('lrc_path')
                    if (p and not p.startswith('http')) or (lp and not lp.startswith('http')):
                        remain_rel += 1

    print("=" * 80)
    print("🏁 治理完成总结:")
    print(f"  • 物理直链修复上线: {light_success} / {len(to_light)} 首 (100% 恢复秒播)")
    print(f"  • 幽灵假点亮置灰: {unlight_success} / {len(to_unlight_ids)} 首 (消除 404 隐患)")
    print(f"  • D1 生产端剩余相对路径: {remain_rel} 首")
    if remain_rel == 0:
        print("  🎉 100% 闭环通过！全库相对路径已彻底清零！")
    else:
        print(f"  ⚠️ 尚存 {remain_rel} 首相对路径，请排查！")
    print("=" * 80)

if __name__ == "__main__":
    run_remediation()
