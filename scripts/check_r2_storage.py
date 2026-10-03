#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - Cloudflare R2 对象存储集群自适应容量监控与自愈看门狗调度器
=============================================================================
核心功能：
1. 严密对齐 Cloudflare 官方商业十进制计费标准 (1 GB = 1,000,000,000 字节)
2. 动态自适应集群：完全解耦硬编码，无论 16 桶、17 桶还是后续拓展任意 N 桶均自适应发现与扫描
3. 9.00 GB 自动封箱与故障转移 (Auto-Locking & Failover)：
   一旦检测到任意桶物理容量 >= 9.00 GB (90%)，自动切为 sealed_readonly 并落盘 r2_config.json；
   若该桶为主力写入桶，自动在健康桶中遴选剩余空间最大的备用桶晋升为 active_write！
4. 全网秒级广播：自动同步前端 admin/r2_stats.json 并实时持久化至 Cloudflare D1 app_settings
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
from concurrent.futures import ThreadPoolExecutor

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
WARN_THRESHOLD_PERCENT = 90.0                      # 9.00 GB 自动封箱与预警线
CRITICAL_THRESHOLD_PERCENT = 95.0                  # 9.50 GB 红色熔断线

# 历史已知只读保护/降温桶 (不可晋升为主力写入桶)
STATIC_PROTECTED_BUCKETS = {
    "moody-music-asset",       # 01
    "moody-music-asset-02",    # 02
    "moody-music-asset-03",    # 03
    "moody-music-asset-04",    # 04
    "moody-music-asset-05",    # 05
    "moody-music-asset-06",    # 06
    "moody-music-asset-07",    # 07
    "moody-music-asset-08",    # 08
    "moody-music-asset-09",    # 09
    "moody-music-asset-10",    # 10
    "moody-music-asset-11",    # 11
    "moody-music-asset-12",    # 12
    "moody-music-asset-15",    # 15
    "moody-music-asset-16",    # 16
}

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
    bname = b_cfg.get('name')
    if not bname:
        return None
    cf_token = b_cfg.get('cf_token') or os.environ.get('CF_TOKEN')
    acc_id = b_cfg.get('account_id')

    # 对于主桶 account_01，优先通过 Worker /api/debug/r2 获取 100% 实时的物理对象与字节数
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

    # 其次尝试 Cloudflare 官方 REST API
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
                    'mp3_count': obj_count,
                    'method': 'cf_api'
                }
        except Exception as e:
            if verbose:
                print(f"[{b_key}] CF REST API 查询失败: {e}")

    # 尝试通过 S3 API 扫描
    try:
        s3_cli = boto3.client(
            's3',
            endpoint_url=b_cfg.get('endpoint_url'),
            aws_access_key_id=b_cfg.get('access_key_id'),
            aws_secret_access_key=b_cfg.get('secret_access_key'),
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
    total_buckets_count = len(r2_all)

    # 1. 物理连接与缓存检查 (20秒低频刷新，保障极致响应速度，多线程并发提速)
    now = time.time()
    if now - _PHYSICAL_CACHE['time'] > 20:
        def _fetch_one(b_key):
            b_cfg = r2_all.get(b_key)
            if not b_cfg:
                return b_key, None
            p_data = fetch_bucket_physical_data(b_key, b_cfg, verbose=verbose)
            return b_key, p_data

        with ThreadPoolExecutor(max_workers=min(12, max(1, total_buckets_count))) as executor:
            futures = [executor.submit(_fetch_one, b_key) for b_key in r2_all.keys()]
            for fut in futures:
                b_key, p_data = fut.result()
                if p_data:
                    _PHYSICAL_CACHE['buckets'][b_key] = p_data
        _PHYSICAL_CACHE['time'] = now

    # 2. 动态生成各存储桶元信息 (不再写死 16 桶)
    bucket_metas = []
    for b_key, b_cfg in r2_all.items():
        digits = "".join([c for c in b_key if c.isdigit()])
        b_id = int(digits) if digits else 99
        b_name = b_cfg.get('name', f'bucket-{b_id}')
        b_label = b_cfg.get('label') or f"第{b_id}存储桶 (Bucket {b_id:02d})"
        b_url = b_cfg.get('public_domain') or b_cfg.get('public_url', '')
        bucket_metas.append((b_id, b_key, b_name, b_label, b_url))
    bucket_metas.sort(key=lambda x: x[0])

    bucket_stats = {}
    total_r2_bytes = 0
    total_r2_count = 0
    config_modified = False

    active_target_key = cfg.get("global_safety_valve", {}).get("active_target_bucket")

    # 3. 汇总与自动自愈加锁判定
    for b_id, b_key, b_name, b_label, b_url in bucket_metas:
        b_cfg = r2_all.get(b_key, {})
        cached = _PHYSICAL_CACHE['buckets'].get(b_key, {})

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

        # 核心自愈防线：若物理用量达到或逼近 9.00 GB (90%)，自动上锁封箱
        if used_ratio >= WARN_THRESHOLD_PERCENT and b_cfg.get('allow_writes', False):
            if verbose:
                print(f"🚨 [自动封箱看门狗触发] 存储桶 [{b_name}] ({b_key}) 容量已达 {used_gb} GB ({used_ratio}%)，自动切换为只读封箱！")
            b_cfg['allow_writes'] = False
            b_cfg['status'] = 'sealed_readonly'
            config_modified = True
            if active_target_key == b_key:
                active_target_key = None  # 原主力桶已超标，需晋升新桶

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
            status_text = f'🔒 警戒封箱 ({used_ratio}%)'
        elif status_cfg in ['frozen_readonly', 'sealed_readonly']:
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
            'account_id': b_cfg.get('account_id', '')[:12] + '...' if b_cfg.get('account_id') else '',
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

    # 4. 自动故障转移与晋升 (Auto-Promotion)
    # 若当前没有可用的 active_target_bucket 或其已被封箱，自动挑选剩余空间最大的备用桶
    if not active_target_key or not r2_all.get(active_target_key, {}).get('allow_writes', False):
        eligible = []
        for k, v in r2_all.items():
            b_name = v.get('name', '').strip().lower()
            if v.get('allow_writes', False) and b_name not in STATIC_PROTECTED_BUCKETS:
                u_bytes = _PHYSICAL_CACHE['buckets'].get(k, {}).get('bytes', 0)
                if u_bytes < (WARN_THRESHOLD_PERCENT / 100.0) * R2_FREE_CAPACITY_BYTES:
                    eligible.append((k, u_bytes))
        if eligible:
            eligible.sort(key=lambda x: x[1])  # 挑选已用空间最少，剩余空间最多的桶
            new_active_key = eligible[0][0]
            cfg.setdefault("global_safety_valve", {})["active_target_bucket"] = new_active_key
            for k, v in r2_all.items():
                if k == new_active_key:
                    v['status'] = 'active_write'
                elif v.get('status') == 'active_write':
                    v['status'] = 'standby'
            config_modified = True
            if verbose:
                print(f"🚀 [自动故障转移完成] 主力写入桶自动晋升为: [{r2_all[new_active_key].get('name')}]")

    # 若配置有变动，写回 r2_config.json
    if config_modified:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            if verbose:
                print("💾 [配置已安全同步] r2_config.json 已自动持久化最新安全锁定状态")
        except Exception as e:
            if verbose:
                print(f"⚠️ [配置持久化失败] {e}")

    # 5. 集群全景汇总
    total_capacity_bytes = R2_FREE_CAPACITY_BYTES * total_buckets_count
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

    active_b_key = cfg.get("global_safety_valve", {}).get("active_target_bucket", "account_13")
    active_b_name = r2_all.get(active_b_key, {}).get("name", active_b_key)

    # 统计可用桶与封箱桶
    writable_names = [v.get('name') for k, v in r2_all.items() if v.get('allow_writes', False)]
    sealed_names = [v.get('name') for k, v in r2_all.items() if not v.get('allow_writes', False)]

    stats_data = {
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'cluster_mode': f'{total_buckets_count}_buckets_adaptive',
        'total_buckets_count': total_buckets_count,
        'total_free_capacity_gb': float(total_buckets_count * 10.0),
        'total_used_gb': round(total_r2_bytes / (1000 ** 3), 2),
        'total_used_ratio': cluster_ratio,
        'total_remaining_gb': round(cluster_remaining_bytes / (1000 ** 3), 2),
        'total_songs_count': total_r2_count,
        'estimated_songs_remaining': cluster_est_songs,
        'cluster_status': cluster_status,
        'safety_valve_active': safety_active,
        'safety_valve_reason': safety_reason if safety_active else '',
        'active_write_bucket': f"{active_b_name} (主力写入中)",
        'writable_buckets': writable_names,
        'sealed_buckets': sealed_names,
        'compression_policy': f'160 kbps CBR ({total_buckets_count}桶集群自适应十进制计量)',

        # 各存储桶详情
        **bucket_stats,

        # 向后兼容顶层字段
        'r2_free_capacity_gb': 10.0,
        'r2_used_bytes': bucket_stats.get('bucket1', {}).get('used_bytes', 0),
        'r2_used_gb': bucket_stats.get('bucket1', {}).get('used_gb', 0),
        'r2_used_ratio': bucket_stats.get('bucket1', {}).get('used_ratio', 0),
        'r2_remaining_gb': bucket_stats.get('bucket1', {}).get('remaining_gb', 0),
        'r2_remaining_mb': bucket_stats.get('bucket1', {}).get('remaining_mb', 0),
        'r2_songs_count': total_r2_count,
        'status_level': cluster_status,
        'status_text': f'{total_buckets_count}桶集群动态自愈监控已生效 (总用量 {cluster_ratio:.1f}%)',
        'local_pending_songs': 0,
        'local_pending_mb': 0.0,
        'local_disk_mp3_count': 0,
        'local_disk_gb': 0.0
    }

    # 6. 同步分发至所有前端与管理端 JSON 文件
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

    # 7. 自动上报至 Cloudflare Worker 动态接口（写入 D1 app_settings，秒级广播全网管理端）
    try:
        r_sync = requests.post(
            "https://m-api.changgepd.ccwu.cc/api/admin/r2/stats",
            json={"stats": stats_data},
            timeout=8
        )
        if verbose and r_sync.status_code == 200:
            print(f"🚀 [D1 云端同步] {total_buckets_count}桶最新物理指标已成功持久化至 D1 app_settings")
    except Exception as e_sync:
        if verbose:
            print(f"⚠️ [D1 云端同步异常] {e_sync}")

    # 8. 打印专业控制台体检报告
    if verbose or __name__ == "__main__":
        print("\n" + "=" * 90)
        print(f"📊 MOODY - Cloudflare R2 {total_buckets_count}存储桶集群自适应监控报告")
        print(f"⏰ 采样校准时间: {time.strftime('%Y-%m-%d %H:%M:%S')} (标准十进制 GB: 1 GB = 1,000,000,000 字节)")
        print("=" * 90)
        print(f"{'存储桶':<22} | {'对象总数':<8} | {'真实用量 (GB)':<14} | {'额度占比':<10} | {'当前状态'}")
        print("-" * 90)
        for b_id, b_key, b_name, b_label, b_url in bucket_metas:
            bs = bucket_stats[f"bucket{b_id}"]
            print(f"{bs['name']:<22} | {bs['total_objects']:<8} | {bs['used_gb']:>6.2f} / 10.00 GB | {bs['used_ratio']:>6.1f}%    | {bs['status_text']}")
        print("-" * 90)
        print(f"🌐 集群全网总用量: {stats_data['total_used_gb']} GB / {stats_data['total_free_capacity_gb']:.2f} GB ({stats_data['total_used_ratio']}%) | 剩余安全空间: {stats_data['total_remaining_gb']} GB")
        print(f"🎯 主力写入桶: {stats_data['active_write_bucket']} | 可写桶数量: {len(writable_names)} | 封箱桶数量: {len(sealed_names)}")
        print("=" * 90 + "\n")

    return stats_data

if __name__ == "__main__":
    check_storage(verbose=True)
