#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - Cloudflare R2 对象存储容量实时监控仪表盘 (R2 Storage Monitor)
=============================================================================
功能：
1. 严密对齐 Cloudflare 官方商业十进制计费标准 (1 GB = 1,000,000,000 字节)
2. 融合 Cloudflare REST API (官方计量) 与 S3 API 物理实测，消除主桶统计盲区
3. 设置 9.00 GB 预警、9.50 GB 强制熔断封箱红线，死守 10.00 GB 免费额度底线
4. 同步九桶集群最新状态并输出 r2_stats.json 供前端大盘秒级刷新
=============================================================================
"""

import os
import sys
import json
import sqlite3
import glob
import time
import requests
import boto3
from botocore.config import Config
import socket

# Cloudflare 边缘 IP Pinning 防代理劫持与网络丢包
_orig_getaddrinfo = socket.getaddrinfo
def _custom_getaddrinfo(host, port, *args, **kwargs):
    if host == "m-api.changgepd.ccwu.cc":
        return _orig_getaddrinfo("172.67.199.94", port, *args, **kwargs)
    if host and host.endswith(".r2.cloudflarestorage.com"):
        return _orig_getaddrinfo("172.64.190.1", port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _custom_getaddrinfo

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

# Cloudflare 官方商业计费标准：1 GB = 10^9 字节
R2_FREE_CAPACITY_BYTES = 10 * 1000 * 1000 * 1000  # 10.00 GB
WARN_THRESHOLD_PERCENT = 90.0                      # 9.00 GB 预警线
CRITICAL_THRESHOLD_PERCENT = 95.0                  # 9.50 GB 熔断封箱线
TOTAL_BUCKETS_COUNT = 11

def format_bytes(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1000.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1000.0
    return f"{bytes_val:.2f} PB"

_PHYSICAL_CACHE = {
    'time': 0,
    'buckets': {}
}

def fetch_bucket_physical_data(b_key, b_cfg, verbose=False):
    """
    智能获取单桶物理用量：
    1. 优先尝试 Cloudflare 官方 REST API (提取官方计费 payloadSize 和 objectCount)
    2. 备用通过 S3 API (list_objects_v2) 进行全量对象物理统计
    """
    bname = b_cfg['name']
    cf_token = b_cfg.get('cf_token') or os.environ.get('CF_TOKEN')

    # 对于主桶 account_01，优先通过 Worker /api/debug/r2 获取 100% 实时的物理对象与字节数 (消除官方 24h 账单统计时延)
    if b_key == 'account_01':
        try:
            r = requests.get("https://m-api.changgepd.ccwu.cc/api/debug/r2", timeout=15)
            if r.status_code == 200:
                d = r.json()
                tot_bytes = d.get('total_bytes', 0)
                tot_count = d.get('total_objects', 0)
                mp3_info = d.get('extensions', {}).get('.mp3', {})
                mp3_cnt = mp3_info.get('count', 0)
                if verbose:
                    print(f"[{b_key}] 通过 Worker 原生 R2 实时获取成功: {tot_bytes} 字节, {tot_count} 对象")
                return {
                    'bytes': tot_bytes,
                    'count': tot_count,
                    'mp3_count': mp3_cnt,
                    'method': 'worker_realtime'
                }
        except Exception as e:
            if verbose:
                print(f"[{b_key}] Worker debug/r2 查询失败: {e}")

    # 其次尝试 Cloudflare 官方 REST API (提取官方计费 payloadSize 和 objectCount)
    if cf_token and acc_id:
        try:
            r = requests.get(
                f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/r2/buckets/{bname}/usage",
                headers={"Authorization": f"Bearer {cf_token}", "Content-Type": "application/json"},
                timeout=8
            )
            data = r.json()
            if data.get('success'):
                res = data['result']
                payload_bytes = int(res['payloadSize'])
                obj_count = int(res['objectCount'])
                if verbose:
                    print(f"[{b_key}] 通过 Cloudflare REST API 获取成功: {payload_bytes} 字节, {obj_count} 对象")
                return {
                    'bytes': payload_bytes,
                    'count': obj_count,
                    'mp3_count': obj_count, # 官方接口未区分后缀，取对象数
                    'method': 'cf_api'
                }
        except Exception as e:
            if verbose:
                print(f"[{b_key}] CF REST API 查询失败: {e}")

    # 尝试通过 S3 API 扫描
    try:
        s3_cli = boto3.client(
            's3',
            endpoint_url=b_cfg['endpoint_url'],
            aws_access_key_id=b_cfg['access_key_id'],
            aws_secret_access_key=b_cfg['secret_access_key'],
            region_name='auto',
            config=Config(s3={'addressing_style': 'path'}, signature_version="s3v4", connect_timeout=5, read_timeout=15)
        )
        paginator = s3_cli.get_paginator('list_objects_v2')
        tot_sz = 0
        tot_cnt = 0
        songs_cnt = 0
        for page in paginator.paginate(Bucket=bname):
            for o in page.get('Contents', []):
                tot_sz += o['Size']
                tot_cnt += 1
                if o['Key'].endswith('.mp3'):
                    songs_cnt += 1
        return {
            'bytes': tot_sz,
            'count': tot_cnt,
            'mp3_count': songs_cnt,
            'method': 's3'
        }
    except Exception as e:
        if verbose:
            print(f"[{b_key}] S3 遍历失败: {e}")
        return None

def check_storage(verbose=False):
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    r2_all = cfg.get("buckets", {})

    # 1. 物理连接与缓存检查 (20秒低频刷新，保障极致响应速度)
    now = time.time()
    if now - _PHYSICAL_CACHE['time'] > 20:
        for b_idx in range(1, TOTAL_BUCKETS_COUNT + 1):
            b_key = f"account_{b_idx:02d}"
            b_cfg = r2_all.get(b_key)
            if not b_cfg:
                continue
            p_data = fetch_bucket_physical_data(b_key, b_cfg, verbose=verbose)
            if p_data:
                _PHYSICAL_CACHE['buckets'][b_key] = p_data
        _PHYSICAL_CACHE['time'] = now

    # 2. 汇总各桶数据
    bucket_stats = {}
    total_r2_bytes = 0
    total_r2_count = 0

    bucket_metas = [
        (1,  "account_01", "moody-music-asset",    "主存储桶 (Bucket 01)",  "r2.changgepd.ccwu.cc"),
        (2,  "account_02", "moody-music-asset-02", "扩展存储桶 (Bucket 02)", "pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev"),
        (3,  "account_03", "moody-music-asset-03", "第三存储桶 (Bucket 03)", "pub-383b876c0bb840f6b852946604275232.r2.dev"),
        (4,  "account_04", "moody-music-asset-04", "第四存储桶 (Bucket 04)", "pub-3507a1a1bc4b4ac3a3340833031078c2.r2.dev"),
        (5,  "account_05", "moody-music-asset-05", "第五存储桶 (Bucket 05)", "pub-e7d069eb11954440aeb32012e8e3c670.r2.dev"),
        (6,  "account_06", "moody-music-asset-06", "第六存储桶 (Bucket 06)", "pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev"),
        (7,  "account_07", "moody-music-asset-07", "第七存储桶 (Bucket 07)", "pub-a0a90fda9b0d45d59a52685eb2ee93d6.r2.dev"),
        (8,  "account_08", "moody-music-asset-08", "第八存储桶 (Bucket 08)", "pub-dd32e05660c74c3dba04d231391eb82b.r2.dev"),
        (9,  "account_09", "moody-music-asset-09", "第九存储桶 (Bucket 09)", "pub-147987db1e7b419cb6ea49acd48d0d25.r2.dev"),
        (10, "account_10", "moody-music-asset-10", "第十存储桶 (Bucket 10)", "pub-9e5d39f15e4a40dfb886ecb275551c90.r2.dev"),
        (11, "account_11", "moody-music-asset-11", "第十一存储桶 (Bucket 11)", "pub-086ee39e1f294c8ba0a12c7073a3c271.r2.dev"),
    ]

    for b_id, b_key, b_name, b_label, b_url in bucket_metas:
        b_cfg = r2_all.get(b_key, {})
        cached = _PHYSICAL_CACHE['buckets'].get(b_key, {})
        
        # 提取真实物理体积与对象数 (0 兜底)
        used_bytes = cached.get('bytes', 0)
        obj_count = cached.get('count', 0)
        mp3_count = cached.get('mp3_count', obj_count)

        # 十进制 GB 计算
        used_gb = round(used_bytes / (1000 ** 3), 2)
        used_mb = round(used_bytes / (1000 ** 2), 1)
        used_ratio = round((used_bytes / R2_FREE_CAPACITY_BYTES) * 100.0, 1)
        remaining_bytes = max(0, R2_FREE_CAPACITY_BYTES - used_bytes)
        remaining_gb = round(remaining_bytes / (1000 ** 3), 2)
        remaining_mb = round(remaining_bytes / (1000 ** 2), 1)

        # 状态判定：死守 10GB 计费红线，9.5GB 强制封箱
        status_cfg = b_cfg.get('status', 'standby')
        allow_writes = b_cfg.get('allow_writes', False)

        if used_ratio >= 100.0:
            status_level = 'critical'
            status_text = f'🚨 已超额扣费 ({used_gb} GB)'
        elif used_ratio >= CRITICAL_THRESHOLD_PERCENT:
            status_level = 'critical'
            status_text = f'🛑 熔断封箱 ({used_ratio}%)'
        elif used_ratio >= WARN_THRESHOLD_PERCENT:
            status_level = 'warning'
            status_text = f'⚠️ 容量预警 ({used_ratio}%)'
        elif not allow_writes or status_cfg == 'frozen_readonly':
            status_level = 'warning' if used_ratio >= 80.0 else 'healthy'
            status_text = f'🔒 只读归档 ({used_ratio}%)'
        elif status_cfg == 'active_write':
            status_level = 'healthy'
            status_text = '🚀 主力写入中'
        else:
            status_level = 'healthy'
            status_text = '就绪待命'

        bucket_stats[f"bucket{b_id}"] = {
            'id': b_id,
            'name': b_name,
            'label': b_label,
            'account_id': b_cfg.get('account_id', '')[:12] + '...',
            'free_capacity_gb': 10.0,
            'used_bytes': used_bytes,
            'used_gb': used_gb,
            'used_mb': used_mb,
            'used_ratio': used_ratio,
            'remaining_gb': remaining_gb,
            'remaining_mb': remaining_mb,
            'songs_count': mp3_count,
            'total_objects': obj_count,
            'status_level': status_level,
            'status_text': status_text,
            'public_url': b_url,
            'allow_writes': allow_writes
        }

        total_r2_bytes += used_bytes
        total_r2_count += mp3_count

    # 3. 十桶集群全景汇总 (100.00 GB 总配额)
    total_capacity_bytes = R2_FREE_CAPACITY_BYTES * TOTAL_BUCKETS_COUNT
    cluster_ratio = round((total_r2_bytes / total_capacity_bytes) * 100.0, 1)
    cluster_remaining_bytes = max(0, total_capacity_bytes - total_r2_bytes)
    cluster_est_songs = int(cluster_remaining_bytes / (3.2 * 1000 * 1000)) if cluster_remaining_bytes > 0 else 0
    cluster_status = 'critical' if cluster_ratio >= CRITICAL_THRESHOLD_PERCENT else ('warning' if cluster_ratio >= WARN_THRESHOLD_PERCENT else 'healthy')

    # 安全阀状态
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from r2_safety_guard import is_safety_valve_active
        safety_active, safety_reason = is_safety_valve_active()
    except Exception:
        safety_active, safety_reason = False, ""

    stats_data = {
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'cluster_mode': 'hendeca_bucket',
        'total_free_capacity_gb': float(TOTAL_BUCKETS_COUNT * 10.0),
        'total_used_gb': round(total_r2_bytes / (1000 ** 3), 2),
        'total_used_ratio': cluster_ratio,
        'total_remaining_gb': round(cluster_remaining_bytes / (1000 ** 3), 2),
        'total_songs_count': total_r2_count,
        'estimated_songs_remaining': cluster_est_songs,
        'cluster_status': cluster_status,
        'safety_valve_active': safety_active,
        'safety_valve_reason': safety_reason if safety_active else '',
        'active_write_bucket': 'moody-music-asset-11 (第十一桶主力写入)',
        'standby_bucket': '第10桶备用，前九桶已安全封箱/降温归档 (防止扣费)',
        'compression_policy': '160 kbps CBR (十一桶集群十进制计量已启用)',

        # 各存储桶
        **bucket_stats,

        # 向后兼容顶层字段
        'r2_free_capacity_gb': 10.0,
        'r2_used_bytes': bucket_stats['bucket1']['used_bytes'],
        'r2_used_gb': bucket_stats['bucket1']['used_gb'],
        'r2_used_ratio': bucket_stats['bucket1']['used_ratio'],
        'r2_remaining_gb': bucket_stats['bucket1']['remaining_gb'],
        'r2_remaining_mb': bucket_stats['bucket1']['remaining_mb'],
        'r2_songs_count': total_r2_count,
        'compressed_songs_count': 5738,
        'status_level': cluster_status,
        'status_text': f'十一桶集群十进制计量已校准 (总用量 {cluster_ratio:.1f}%)',
        'local_pending_songs': 0,
        'local_pending_mb': 0.0,
        'local_disk_mp3_count': 0,
        'local_disk_gb': 0.0
    }

    # 4. 同步分发至所有前端与管理端 JSON 文件
    parent_dir = os.path.dirname(BASE_DIR)
    target_dirs = [
        os.path.join(BASE_DIR, "frontend", "admin"),
        os.path.join(BASE_DIR, "frontend"),
        os.path.join(parent_dir, "MoodyMusic-Web", "admin"),
        os.path.join(parent_dir, "MoodyMusic-Web")
    ]
    for out_dir in target_dirs:
        try:
            if os.path.exists(out_dir):
                target_json = os.path.join(out_dir, "r2_stats.json")
                with open(target_json, 'w', encoding='utf-8') as f_json:
                    json.dump(stats_data, f_json, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # 4.1 自动上报至 Cloudflare Worker 动态接口（写入 D1 app_settings，秒级广播全网管理端）
    try:
        r_sync = requests.post(
            "https://m-api.changgepd.ccwu.cc/api/admin/r2/stats",
            json={"stats": stats_data},
            timeout=8
        )
        if verbose and r_sync.status_code == 200:
            print("🚀 [D1 云端同步] 十一桶最新物理指标已成功持久化至 D1 app_settings")
    except Exception as e_sync:
        if verbose:
            print(f"⚠️ [D1 云端同步异常] {e_sync}")

    # 5. 打印专业控制台体检报告
    if verbose or __name__ == "__main__":
        print("\n" + "=" * 90)
        print("📊 MOODY - Cloudflare R2 十一存储桶集群商业计费实时监控报告 (Hendeca-Bucket Hub)")
        print(f"⏰ 采样校准时间: {time.strftime('%Y-%m-%d %H:%M:%S')} (标准十进制 GB: 1 GB = 1,000,000,000 字节)")
        print("=" * 90)
        print(f"{'存储桶':<22} | {'对象总数':<8} | {'真实用量 (GB)':<14} | {'额度占比':<10} | {'当前状态'}")
        print("-" * 90)
        for b_id in range(1, TOTAL_BUCKETS_COUNT + 1):
            bs = stats_data[f"bucket{b_id}"]
            print(f"{bs['name']:<22} | {bs['total_objects']:<8} | {bs['used_gb']:>6.2f} / 10.00 GB | {bs['used_ratio']:>6.1f}%    | {bs['status_text']}")
        print("-" * 90)
        print(f"🌐 集群全网总用量: {stats_data['total_used_gb']} GB / {stats_data['total_free_capacity_gb']:.2f} GB ({stats_data['total_used_ratio']}%) | 剩余安全空间: {stats_data['total_remaining_gb']} GB")
        print("=" * 90 + "\n")

    return stats_data

if __name__ == "__main__":
    check_storage(verbose=True)
