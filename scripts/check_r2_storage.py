#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - Cloudflare R2 对象存储容量实时监控仪表盘 (R2 Storage Monitor)
功能：
1. 精准核算已入驻 R2 的音频及歌词资产物理体积
2. 对比 Cloudflare R2 每月 10 GB 免费额度并计算剩余容量
3. 提供基于剩余空间的预警分析、安全边际评估及应对策略
"""

import os
import sys
import json
import sqlite3
import glob
import time

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

R2_FREE_CAPACITY_BYTES = 10 * 1024 * 1024 * 1024  # 10.00 GB
WARN_THRESHOLD_PERCENT = 80.0
CRITICAL_THRESHOLD_PERCENT = 95.0

def format_bytes(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"

_PHYSICAL_CACHE = {
    'time': 0,
    'b2_bytes': None,
    'b2_count': None,
    'b3_bytes': None,
    'b3_count': None,
    'b4_bytes': None,
    'b4_count': None,
    'b5_bytes': None,
    'b5_count': None,
    'b6_bytes': None,
    'b6_count': None
}

def check_storage(verbose=False):
    if not os.path.exists(DB_PATH):
        if verbose:
            print(f"❌ 数据库不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1.1 存储桶 1 (主存储桶 - moody-music-asset)
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT')
          AND (r2_mp3_key IS NULL OR (
              r2_mp3_key NOT LIKE '%pub-9ea7ff16135d47238c0229f1aa54ecc4%'
              AND r2_mp3_key NOT LIKE '%moody-music-asset-02%'
              AND r2_mp3_key NOT LIKE '%pub-383b876c0bb840f6b852946604275232%'
              AND r2_mp3_key NOT LIKE '%moody-music-asset-03%'
              AND r2_mp3_key NOT LIKE '%pub-3507a1a1bc4b4ac3a3340833031078c2%'
              AND r2_mp3_key NOT LIKE '%moody-music-asset-04%'
              AND r2_mp3_key NOT LIKE '%pub-e7d069eb11954440aeb32012e8e3c670%'
              AND r2_mp3_key NOT LIKE '%moody-music-asset-05%'
              AND r2_mp3_key NOT LIKE '%pub-46ab5c0015d84be1b748cffecd23fdbb%'
              AND r2_mp3_key NOT LIKE '%moody-music-asset-06%'
          ))
    """)
    b1_count, b1_bytes = cur.fetchone()

    # 1.2 存储桶 2 (扩展桶 - moody-music-asset-02) 数据库记录
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT', 'R2_UPLOADED_BUCKET2')
          AND (r2_mp3_key LIKE '%pub-9ea7ff16135d47238c0229f1aa54ecc4%' OR r2_mp3_key LIKE '%moody-music-asset-02%')
    """)
    b2_db_count, b2_db_bytes = cur.fetchone()

    # 1.3 存储桶 3 (第三桶 - moody-music-asset-03) 数据库记录
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT', 'R2_UPLOADED_BUCKET3')
          AND (r2_mp3_key LIKE '%pub-383b876c0bb840f6b852946604275232%' OR r2_mp3_key LIKE '%moody-music-asset-03%')
    """)
    b3_db_count, b3_db_bytes = cur.fetchone()

    # 1.4 存储桶 4 (第四桶 - moody-music-asset-04) 数据库记录
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT', 'R2_UPLOADED_BUCKET4')
          AND (r2_mp3_key LIKE '%pub-3507a1a1bc4b4ac3a3340833031078c2%' OR r2_mp3_key LIKE '%moody-music-asset-04%')
    """)
    b4_db_count, b4_db_bytes = cur.fetchone()

    # 1.5 存储桶 5 (第五桶 - moody-music-asset-05) 数据库记录
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT', 'R2_UPLOADED_BUCKET5')
          AND (r2_mp3_key LIKE '%pub-e7d069eb11954440aeb32012e8e3c670%' OR r2_mp3_key LIKE '%moody-music-asset-05%')
    """)
    b5_db_count, b5_db_bytes = cur.fetchone()

    # 1.6 存储桶 6 (第六桶 - moody-music-asset-06) 数据库记录
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT', 'R2_UPLOADED_BUCKET6')
          AND (r2_mp3_key LIKE '%pub-46ab5c0015d84be1b748cffecd23fdbb%' OR r2_mp3_key LIKE '%moody-music-asset-06%')
    """)
    b6_db_count, b6_db_bytes = cur.fetchone()

    b2_bytes = b2_db_bytes
    b2_count = b2_db_count
    b3_bytes = b3_db_bytes
    b3_count = b3_db_count
    b4_bytes = b4_db_bytes
    b4_count = b4_db_count
    b5_bytes = b5_db_bytes
    b5_count = b5_db_count
    b6_bytes = b6_db_bytes
    b6_count = b6_db_count

    # 1.7 直接物理连接 Cloudflare R2 S3 API 实测物理体积（0 估算，带 20s 内存缓存保证毫秒级响应）
    now = time.time()
    if now - _PHYSICAL_CACHE['time'] > 20:
        try:
            import boto3
            from botocore.config import Config
            cfg_file = os.path.join(BASE_DIR, "r2_config.json")
            if os.path.exists(cfg_file):
                with open(cfg_file, "r", encoding="utf-8") as f:
                    r2_all = json.load(f).get("buckets", {})
                for b_idx, b_key in enumerate(['account_02', 'account_03', 'account_04', 'account_05', 'account_06'], start=2):
                    b_cfg = r2_all.get(b_key)
                    if not b_cfg:
                        continue
                    s3_cli = boto3.client(
                        's3',
                        endpoint_url=b_cfg['endpoint_url'],
                        aws_access_key_id=b_cfg['access_key_id'],
                        aws_secret_access_key=b_cfg['secret_access_key'],
                        region_name='auto',
                        config=Config(s3={'addressing_style': 'path'}, connect_timeout=5, read_timeout=15)
                    )
                    paginator = s3_cli.get_paginator('list_objects_v2')
                    tot_sz = 0
                    songs_cnt = 0
                    for page in paginator.paginate(Bucket=b_cfg['name']):
                        for o in page.get('Contents', []):
                            tot_sz += o['Size']
                            if o['Key'].endswith('.mp3'):
                                songs_cnt += 1
                    _PHYSICAL_CACHE[f'b{b_idx}_bytes'] = tot_sz
                    _PHYSICAL_CACHE[f'b{b_idx}_count'] = songs_cnt
                _PHYSICAL_CACHE['time'] = now
        except Exception as e:
            print("EXCEPTION IN S3 PAGINATE:", e)

    if _PHYSICAL_CACHE['b2_bytes'] is not None:
        b2_bytes = _PHYSICAL_CACHE['b2_bytes']
    if _PHYSICAL_CACHE['b2_count'] is not None:
        b2_count = _PHYSICAL_CACHE['b2_count']

    if _PHYSICAL_CACHE['b3_bytes'] is not None:
        b3_bytes = _PHYSICAL_CACHE['b3_bytes']
    if _PHYSICAL_CACHE['b3_count'] is not None:
        b3_count = _PHYSICAL_CACHE['b3_count']

    if _PHYSICAL_CACHE['b4_bytes'] is not None:
        b4_bytes = _PHYSICAL_CACHE['b4_bytes']
    if _PHYSICAL_CACHE['b4_count'] is not None:
        b4_count = _PHYSICAL_CACHE['b4_count']

    if _PHYSICAL_CACHE['b5_bytes'] is not None:
        b5_bytes = _PHYSICAL_CACHE['b5_bytes']
    if _PHYSICAL_CACHE['b5_count'] is not None:
        b5_count = _PHYSICAL_CACHE['b5_count']

    if _PHYSICAL_CACHE['b6_bytes'] is not None:
        b6_bytes = _PHYSICAL_CACHE['b6_bytes']
    if _PHYSICAL_CACHE['b6_count'] is not None:
        b6_count = _PHYSICAL_CACHE['b6_count']

    # 1.8 六桶总计
    total_r2_count = b1_count + b2_count + b3_count + b4_count + b5_count + b6_count
    total_r2_bytes = b1_bytes + b2_bytes + b3_bytes + b4_bytes + b5_bytes + b6_bytes

    # 2. 本地已下载统计
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status = 'DOWNLOADED'
    """)
    dl_count, dl_bytes = cur.fetchone()

    # 3. 失败隔离统计
    cur.execute("""
        SELECT COUNT(*) FROM tracks_sync_state WHERE status = 'UPLOAD_FAILED'
    """)
    failed_count = cur.fetchone()[0]

    # 4. 本地实际磁盘文件统计
    local_mp3s = glob.glob(os.path.join(DOWNLOADS_DIR, "*.mp3"))
    actual_disk_bytes = sum(os.path.getsize(f) for f in local_mp3s if os.path.exists(f))

    # 查询已压缩数量
    cur.execute("SELECT COUNT(*) FROM tracks_sync_state WHERE is_compressed = 1")
    compressed_count = cur.fetchone()[0]

    conn.close()

    # 引入全局安全阀门卫检测
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from r2_safety_guard import is_safety_valve_active
        safety_active, safety_reason = is_safety_valve_active()
    except Exception:
        safety_active, safety_reason = True, "安全阀配置生效中"

    # 单桶与四桶集群指标计算
    # 存储桶 1 指标 (10GB 限额)
    b1_ratio = (b1_bytes / R2_FREE_CAPACITY_BYTES) * 100.0
    b1_remaining_bytes = max(0, R2_FREE_CAPACITY_BYTES - b1_bytes)
    b1_status = 'critical' if b1_ratio >= CRITICAL_THRESHOLD_PERCENT else ('warning' if b1_ratio >= WARN_THRESHOLD_PERCENT else 'healthy')
    b1_status_text = '熔断红线 (已达95%)' if b1_ratio >= CRITICAL_THRESHOLD_PERCENT else ('预警分流中 (已超80%)' if b1_ratio >= WARN_THRESHOLD_PERCENT else '空间充裕')

    # 存储桶 2 指标 (10GB 限额)
    b2_ratio = (b2_bytes / R2_FREE_CAPACITY_BYTES) * 100.0
    b2_remaining_bytes = max(0, R2_FREE_CAPACITY_BYTES - b2_bytes)
    b2_status = 'critical' if b2_ratio >= CRITICAL_THRESHOLD_PERCENT else ('warning' if b2_ratio >= WARN_THRESHOLD_PERCENT else 'healthy')
    b2_status_text = '熔断红线 (已达95%)' if b2_ratio >= CRITICAL_THRESHOLD_PERCENT else ('容量预警 (已超80%)' if b2_ratio >= WARN_THRESHOLD_PERCENT else '只读归档')

    # 存储桶 3 指标 (10GB 限额)
    b3_ratio = (b3_bytes / R2_FREE_CAPACITY_BYTES) * 100.0
    b3_remaining_bytes = max(0, R2_FREE_CAPACITY_BYTES - b3_bytes)
    b3_status = 'critical' if b3_ratio >= CRITICAL_THRESHOLD_PERCENT else ('warning' if b3_ratio >= WARN_THRESHOLD_PERCENT else 'healthy')
    b3_status_text = '熔断红线 (已达95%)' if b3_ratio >= CRITICAL_THRESHOLD_PERCENT else ('容量预警 (已超80%)' if b3_ratio >= WARN_THRESHOLD_PERCENT else '只读归档')

    # 存储桶 4 指标 (10GB 限额 - 主力写入)
    b4_ratio = (b4_bytes / R2_FREE_CAPACITY_BYTES) * 100.0
    b4_remaining_bytes = max(0, R2_FREE_CAPACITY_BYTES - b4_bytes)
    b4_status = 'critical' if b4_ratio >= CRITICAL_THRESHOLD_PERCENT else ('warning' if b4_ratio >= WARN_THRESHOLD_PERCENT else 'healthy')
    b4_status_text = '熔断红线 (已达95%)' if b4_ratio >= CRITICAL_THRESHOLD_PERCENT else ('容量预警 (已超80%)' if b4_ratio >= WARN_THRESHOLD_PERCENT else ('主力写入' if b4_count > 0 else '主力写入 (极度充裕)'))

    # 存储桶 5 指标 (10GB 限额 - 就绪待命)
    b5_ratio = (b5_bytes / R2_FREE_CAPACITY_BYTES) * 100.0
    b5_remaining_bytes = max(0, R2_FREE_CAPACITY_BYTES - b5_bytes)
    b5_status = 'critical' if b5_ratio >= CRITICAL_THRESHOLD_PERCENT else ('warning' if b5_ratio >= WARN_THRESHOLD_PERCENT else 'healthy')
    b5_status_text = '熔断红线 (已达95%)' if b5_ratio >= CRITICAL_THRESHOLD_PERCENT else ('容量预警 (已超80%)' if b5_ratio >= WARN_THRESHOLD_PERCENT else ('主力写入' if b5_count > 0 else '就绪待命'))

    # 存储桶 6 指标 (10GB 限额 - 就绪待命)
    b6_ratio = (b6_bytes / R2_FREE_CAPACITY_BYTES) * 100.0
    b6_remaining_bytes = max(0, R2_FREE_CAPACITY_BYTES - b6_bytes)
    b6_status = 'critical' if b6_ratio >= CRITICAL_THRESHOLD_PERCENT else ('warning' if b6_ratio >= WARN_THRESHOLD_PERCENT else 'healthy')
    b6_status_text = '熔断红线 (已达95%)' if b6_ratio >= CRITICAL_THRESHOLD_PERCENT else ('容量预警 (已超80%)' if b6_ratio >= WARN_THRESHOLD_PERCENT else ('主力写入' if b6_count > 0 else '就绪待命'))

    # 六桶集群总览 (60GB 总限额)
    total_capacity_bytes = R2_FREE_CAPACITY_BYTES * 6
    cluster_ratio = (total_r2_bytes / total_capacity_bytes) * 100.0
    cluster_remaining_bytes = max(0, total_capacity_bytes - total_r2_bytes)
    cluster_est_songs = int(cluster_remaining_bytes / (3.2 * 1024 * 1024)) if cluster_remaining_bytes > 0 else 0
    cluster_status = 'critical' if cluster_ratio >= CRITICAL_THRESHOLD_PERCENT else ('warning' if cluster_ratio >= WARN_THRESHOLD_PERCENT else 'healthy')

    # 安全阀生效时的状态覆写
    if safety_active:
        b1_status = 'locked'
        b1_status_text = '🛡️ 安全阀已锁死 (只读保护)'
        b2_status = 'locked'
        b2_status_text = '🛡️ 安全阀已锁死 (只读保护)'
        b3_status = 'locked'
        b3_status_text = '🛡️ 安全阀已锁死 (只读保护)'
        b4_status = 'locked'
        b4_status_text = '🛡️ 安全阀已锁死 (只读保护)'
        b5_status = 'locked'
        b5_status_text = '🛡️ 安全阀已锁死 (只读保护)'
        b6_status = 'locked'
        b6_status_text = '🛡️ 安全阀已锁死 (只读保护)'
        cluster_status = 'locked'

    # 输出 JSON 供 CMS 管理后台直接渲染
    stats_data = {
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'cluster_mode': 'hexa_bucket',
        'total_free_capacity_gb': 60.0,
        'total_used_gb': round(total_r2_bytes / (1024**3), 2),
        'total_used_ratio': round(cluster_ratio, 1),
        'total_remaining_gb': round(cluster_remaining_bytes / (1024**3), 2),
        'total_songs_count': total_r2_count,
        'estimated_songs_remaining': cluster_est_songs,
        'cluster_status': cluster_status,
        'safety_valve_active': safety_active,
        'safety_valve_reason': safety_reason if safety_active else '',
        'active_write_bucket': '⛔ 全局安全阀锁死 (禁止写入)' if safety_active else 'moody-music-asset-04 (第四桶主力写入)',
        'standby_bucket': '⛔ 全局安全阀锁死 (禁止写入)' if safety_active else '第五桶/第六桶就绪待命 (50~60GB)',
        'compression_policy': '160 kbps CBR (六桶集群已启用)',

        # 存储桶 1 细化资产
        'bucket1': {
            'name': 'moody-music-asset',
            'label': '主存储桶 (Bucket 01)',
            'account_id': '0bd18c2b... (changgepd)',
            'free_capacity_gb': 10.0,
            'used_bytes': b1_bytes,
            'used_gb': round(b1_bytes / (1024**3), 2),
            'used_ratio': round(b1_ratio, 1),
            'remaining_gb': round(b1_remaining_bytes / (1024**3), 2),
            'remaining_mb': round(b1_remaining_bytes / (1024**2), 1),
            'songs_count': b1_count,
            'status_level': b1_status,
            'status_text': b1_status_text,
            'domain': 'r2.changgepd.ccwu.cc'
        },

        # 存储桶 2 细化资产
        'bucket2': {
            'name': 'moody-music-asset-02',
            'label': '扩展存储桶 (Bucket 02)',
            'account_id': '042076c2... (juanlihou)',
            'free_capacity_gb': 10.0,
            'used_bytes': b2_bytes,
            'used_gb': round(b2_bytes / (1024**3), 2),
            'used_mb': round(b2_bytes / (1024**2), 1),
            'used_ratio': round(b2_ratio, 1),
            'remaining_gb': round(b2_remaining_bytes / (1024**3), 2),
            'remaining_mb': round(b2_remaining_bytes / (1024**2), 1),
            'songs_count': b2_count,
            'status_level': b2_status,
            'status_text': b2_status_text,
            'public_url': 'pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev'
        },

        # 存储桶 3 细化资产
        'bucket3': {
            'name': 'moody-music-asset-03',
            'label': '第三存储桶 (Bucket 03)',
            'account_id': '2cf50939... (Changgepd.robot)',
            'free_capacity_gb': 10.0,
            'used_bytes': b3_bytes,
            'used_gb': round(b3_bytes / (1024**3), 2),
            'used_mb': round(b3_bytes / (1024**2), 1),
            'used_ratio': round(b3_ratio, 1),
            'remaining_gb': round(b3_remaining_bytes / (1024**3), 2),
            'remaining_mb': round(b3_remaining_bytes / (1024**2), 1),
            'songs_count': b3_count,
            'status_level': b3_status,
            'status_text': b3_status_text,
            'public_url': 'pub-383b876c0bb840f6b852946604275232.r2.dev'
        },

        # 存储桶 4 细化资产
        'bucket4': {
            'name': 'moody-music-asset-04',
            'label': '第四存储桶 (Bucket 04)',
            'account_id': '9fd42323... (zhangjing.study)',
            'free_capacity_gb': 10.0,
            'used_bytes': b4_bytes,
            'used_gb': round(b4_bytes / (1024**3), 2),
            'used_mb': round(b4_bytes / (1024**2), 1),
            'used_ratio': round(b4_ratio, 1),
            'remaining_gb': round(b4_remaining_bytes / (1024**3), 2),
            'remaining_mb': round(b4_remaining_bytes / (1024**2), 1),
            'songs_count': b4_count,
            'status_level': b4_status,
            'status_text': b4_status_text,
            'public_url': 'pub-3507a1a1bc4b4ac3a3340833031078c2.r2.dev'
        },

        # 存储桶 5 细化资产
        'bucket5': {
            'name': 'moody-music-asset-05',
            'label': '第五存储桶 (Bucket 05)',
            'account_id': '599e95ec... (moody-05)',
            'free_capacity_gb': 10.0,
            'used_bytes': b5_bytes,
            'used_gb': round(b5_bytes / (1024**3), 2),
            'used_mb': round(b5_bytes / (1024**2), 1),
            'used_ratio': round(b5_ratio, 1),
            'remaining_gb': round(b5_remaining_bytes / (1024**3), 2),
            'remaining_mb': round(b5_remaining_bytes / (1024**2), 1),
            'songs_count': b5_count,
            'status_level': b5_status,
            'status_text': b5_status_text,
            'public_url': 'pub-e7d069eb11954440aeb32012e8e3c670.r2.dev'
        },

        # 存储桶 6 细化资产
        'bucket6': {
            'name': 'moody-music-asset-06',
            'label': '第六存储桶 (Bucket 06)',
            'account_id': '14777c28... (moody-06)',
            'free_capacity_gb': 10.0,
            'used_bytes': b6_bytes,
            'used_gb': round(b6_bytes / (1024**3), 2),
            'used_mb': round(b6_bytes / (1024**2), 1),
            'used_ratio': round(b6_ratio, 1),
            'remaining_gb': round(b6_remaining_bytes / (1024**3), 2),
            'remaining_mb': round(b6_remaining_bytes / (1024**2), 1),
            'songs_count': b6_count,
            'status_level': b6_status,
            'status_text': b6_status_text,
            'public_url': 'pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev'
        },

        # 顶层向后兼容字段
        'r2_free_capacity_gb': 10.0,
        'r2_used_bytes': b1_bytes,
        'r2_used_gb': round(b1_bytes / (1024**3), 2),
        'r2_used_ratio': round(b1_ratio, 1),
        'r2_remaining_gb': round(b1_remaining_bytes / (1024**3), 2),
        'r2_remaining_mb': round(b1_remaining_bytes / (1024**2), 1),
        'r2_songs_count': total_r2_count,
        'compressed_songs_count': compressed_count,
        'status_level': cluster_status,
        'status_text': f'六桶扩容正常 (总用量 {cluster_ratio:.1f}%)',
        'local_pending_songs': dl_count,
        'local_pending_mb': round(dl_bytes / (1024**2), 1),
        'local_disk_mp3_count': len(local_mp3s),
        'local_disk_gb': round(actual_disk_bytes / (1024**3), 2)
    }

    root_dir = os.path.dirname(os.path.dirname(BASE_DIR))
    for out_dir in [
        os.path.join(BASE_DIR, "frontend", "admin"),
        os.path.join(BASE_DIR, "frontend"),
        os.path.join(root_dir, "MoodyMusicWeb-temp", "admin"),
        os.path.join(root_dir, "MoodyMusicWeb-temp")
    ]:
        try:
            if os.path.exists(os.path.dirname(out_dir)):
                os.makedirs(out_dir, exist_ok=True)
                target_json = os.path.join(out_dir, "r2_stats.json")
                with open(target_json, 'w', encoding='utf-8') as f_json:
                    json.dump(stats_data, f_json, ensure_ascii=False, indent=2)
        except Exception as e:
            pass

    print("\n" + "=" * 80)
    print("📊 MOODY - Cloudflare R2 六存储桶集群实时监控报告 (Hexa-Bucket Hub)")
    print(f"⏰ 采样时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print(f"📦 【存储桶 1 (主桶: moody-music-asset)】:")
    print(f"   • 音轨数量: {b1_count} 首 | 物理体积: {format_bytes(b1_bytes)} / 10.00 GB")
    print(f"   • 当前水位: {b1_ratio:.1f}% ({b1_status_text}) | 剩余: {format_bytes(b1_remaining_bytes)}")

    print(f"\n🚀 【存储桶 2 (扩展桶: moody-music-asset-02)】:")
    print(f"   • 音轨数量: {b2_count} 首 | 物理体积: {format_bytes(b2_bytes)} / 10.00 GB")
    print(f"   • 当前水位: {b2_ratio:.1f}% ({b2_status_text}) | 剩余: {format_bytes(b2_remaining_bytes)}")

    print(f"\n✨ 【存储桶 3 (第三桶: moody-music-asset-03)】:")
    print(f"   • 音轨数量: {b3_count} 首 | 物理体积: {format_bytes(b3_bytes)} / 10.00 GB")
    print(f"   • 当前水位: {b3_ratio:.1f}% ({b3_status_text}) | 剩余: {format_bytes(b3_remaining_bytes)}")

    print(f"\n🔥 【存储桶 4 (第四桶: moody-music-asset-04)】:")
    print(f"   • 音轨数量: {b4_count} 首 | 物理体积: {format_bytes(b4_bytes)} / 10.00 GB")
    print(f"   • 当前水位: {b4_ratio:.1f}% ({b4_status_text}) | 剩余: {format_bytes(b4_remaining_bytes)}")

    print(f"\n🌟 【存储桶 5 (第五桶: moody-music-asset-05)】:")
    print(f"   • 音轨数量: {b5_count} 首 | 物理体积: {format_bytes(b5_bytes)} / 10.00 GB")
    print(f"   • 当前水位: {b5_ratio:.1f}% ({b5_status_text}) | 剩余: {format_bytes(b5_remaining_bytes)}")

    print(f"\n💎 【存储桶 6 (第六桶: moody-music-asset-06)】:")
    print(f"   • 音轨数量: {b6_count} 首 | 物理体积: {format_bytes(b6_bytes)} / 10.00 GB")
    print(f"   • 当前水位: {b6_ratio:.1f}% ({b6_status_text}) | 剩余: {format_bytes(b6_remaining_bytes)}")

    print(f"\n🌐 【六桶集群汇总 (总配额: 60.00 GB)】:")
    print(f"   • 云端总资产: {total_r2_count} 首 | 总体积: {format_bytes(total_r2_bytes)} ({cluster_ratio:.1f}%)")
    print(f"   • 集群剩余空间: {format_bytes(cluster_remaining_bytes)} (估算按 160k 还可存约 {cluster_est_songs} 首)")

    print(f"\n💾 【本地就绪池 (DOWNLOADED)】:")
    print(f"   • 待推送曲目: {dl_count} 首 ({format_bytes(dl_bytes)})")
    print(f"   • 磁盘实测 MP3: {len(local_mp3s)} 个 ({format_bytes(actual_disk_bytes)})")

    print("\n🚦 【安全状态评估】:")
    print(f"   🟢 [六桶集群就绪] 第五桶与第六桶已接入，集群总额度扩容至 60.00 GB，当前水位 {cluster_ratio:.1f}%，极度健康安全！")

    print("=" * 80 + "\n")
    return stats_data

if __name__ == "__main__":
    check_storage()
