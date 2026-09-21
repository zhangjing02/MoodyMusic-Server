#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 音乐曲库 - 三桶集群并发采录实时监控仪表盘 (Cluster Dashboard)
=============================================================================
功能:
实时统计 3 个存储桶当前容量、各分流 Worker 进度、各歌手点亮完成率及全库总态势
=============================================================================
"""

import os
import sys
import json
import sqlite3
import boto3
from botocore.config import Config
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

import requests

def get_bucket_stats(cfg, acc_key):
    acc = cfg["buckets"][acc_key]
    bucket_name = acc["name"]
    cf_token = acc.get("cf_token") or os.environ.get("CF_TOKEN")
    acc_id = acc.get("account_id", "")

    # 优先尝试 Cloudflare 官方 REST API (特别针对 account_01)
    if acc_key == "account_01" and cf_token and acc_id:
        try:
            r = requests.get(
                f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/r2/buckets/{bucket_name}/usage",
                headers={"Authorization": f"Bearer {cf_token}", "Content-Type": "application/json"},
                timeout=8
            )
            data = r.json()
            if data.get('success'):
                res = data['result']
                payload_bytes = int(res['payloadSize'])
                obj_count = int(res['objectCount'])
                gb = payload_bytes / (1000 ** 3)
                return {"name": bucket_name, "count": obj_count, "gb": gb, "avail_gb": max(0.0, 9.5 - gb)}
        except Exception:
            pass

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=acc["endpoint_url"],
            aws_access_key_id=acc["access_key_id"],
            aws_secret_access_key=acc["secret_access_key"],
            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10)
        )
        paginator = s3.get_paginator('list_objects_v2')
        total_size = 0
        total_count = 0
        for page in paginator.paginate(Bucket=bucket_name):
            if 'Contents' in page:
                for obj in page['Contents']:
                    total_size += obj['Size']
                    total_count += 1
        gb = total_size / (1000 ** 3)
        return {"name": bucket_name, "count": total_count, "gb": gb, "avail_gb": max(0.0, 9.5 - gb)}
    except Exception as e:
        return {"name": bucket_name, "count": -1, "gb": 0.0, "avail_gb": 0.0, "error": str(e)}

def print_dashboard():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "=" * 95)
    print(f"📡 MOODY 音乐曲库 - 三桶并发集群实时监控仪表盘 [{now_str}]")
    print("=" * 95)
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
        
    print("\n📦【Cloudflare R2 九桶集群容量与负载】")
    print("-" * 95)
    print(f"{'存储桶':<24} | {'账号标识':<12} | {'对象总数':<8} | {'当前用量':<10} | {'安全额度':<10} | {'剩余安全空间':<12}")
    print("-" * 95)
    
    cluster_buckets = [
        ("moody-music-asset", "account_01"),
        ("moody-music-asset-02", "account_02"),
        ("moody-music-asset-03", "account_03"),
        ("moody-music-asset-04", "account_04"),
        ("moody-music-asset-05", "account_05"),
        ("moody-music-asset-06", "account_06"),
        ("moody-music-asset-07", "account_07"),
        ("moody-music-asset-08", "account_08"),
        ("moody-music-asset-09", "account_09")
    ]
    for bname, akey in cluster_buckets:
        stats = get_bucket_stats(cfg, akey)
        print(f"{bname:<24} | {akey:<12} | {stats['count']:<8} | {stats['gb']:>6.3f} GB   | 9.500 GB   | {stats['avail_gb']:>6.3f} GB")
    print("-" * 95)
    
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM tracks_sync_state WHERE status = 'D1_LIT'")
        total_lit = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tracks_sync_state")
        total_tracks = cur.fetchone()[0]
        lit_pct = (total_lit / total_tracks * 100) if total_tracks else 0
        
        print(f"\n🌟 全库总体点亮率: {total_lit} / {total_tracks} 首 ({lit_pct:.2f}% 已完成上线)")
    else:
        print(f"\n🌟 本地 catalog_sync.db 未挂载，跳过点亮率统计")
    
    # 统计三大 Worker 分组及归档
    GROUPS = [
        ("Worker 05 正在运行 (国民神曲与音乐魔术师 -> Bucket 05)", ['张雨生', '凤凰传奇']),
        ("Worker 06 正在运行 (金曲唱将与当红顶流 -> Bucket 06)", ['薛之谦', '张靓颖', '郁可唯', '方大同', '汪峰', 'JOLIN蔡依林', '曹格', '黄小琥']),
        ("已圆满归档天王天后群星 (王菲/张学友/张国荣/刘德华/黎明/Beyond/陈奕迅等)", [
            '王菲', '张学友', '张国荣', '刘德华', '黎明', '陈奕迅', 'Beyond', '任贤齐', '李玟', 
            '王力宏', '姜育恒', '萧敬腾', '范晓萱', '费玉清', '卢广仲', '伍佰', '苏打绿', '齐豫', 
            '齐秦', '莫文蔚', '庾澄庆', '游鸿明', '张惠妹', '罗大佑', '飞儿乐团', '苏慧伦', '黄品源', '万芳'
        ])
    ]
    
    if os.path.exists(DB_PATH):
        print("=" * 95)
        print("🚀【三大 Worker 分组采录点亮实时明细】")
        print("=" * 95)
        
        for gname, artists in GROUPS:
            print(f"\n📌 {gname}")
            print(f"{'歌手':<12} | {'总曲目':<8} | {'已点亮 (D1)':<12} | {'留白跳过':<10} | {'待采录队列':<10} | {'点亮完成率':<10}")
            print("-" * 80)
            g_tot = g_lit = g_skip = g_pend = 0
            for a in artists:
                cur.execute("SELECT COUNT(*) FROM tracks_sync_state WHERE artist_name = ?", (a,))
                tot = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM tracks_sync_state WHERE artist_name = ? AND status = 'D1_LIT'", (a,))
                lit = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM tracks_sync_state WHERE artist_name = ? AND status = 'UNLIT_SKIPPED'", (a,))
                skip = cur.fetchone()[0]
                pend = tot - lit - skip
                pct = (lit / tot * 100) if tot else 0
                print(f"{a:<12} | {tot:<8} | {lit:<12} | {skip:<10} | {pend:<10} | {pct:>6.1f}%")
                g_tot += tot
                g_lit += lit
                g_skip += skip
                g_pend += pend
            g_pct = (g_lit / g_tot * 100) if g_tot else 0
            print("-" * 80)
            print(f"{'【小计】':<12} | {g_tot:<8} | {g_lit:<12} | {g_skip:<10} | {g_pend:<10} | {g_pct:>6.1f}%\n")
            
        conn.close()
    print("=" * 95 + "\n")

if __name__ == "__main__":
    print_dashboard()
