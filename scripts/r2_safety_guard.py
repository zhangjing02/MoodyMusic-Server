#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MoodyMusic - Cloudflare R2 工业级智能容量熔断与安全上传看门狗 (R2 Safety Guard)
=============================================================================
核心铁律：
1. 商业十进制：严格按 1 GB = 1,000,000,000 字节计算容量。
2. 9.50 GB 绝对红色熔断线：单桶达到或即将突破 9.50 GB 必须立刻触发强制熔断拦截，严禁任何可能产生超额账单的写入！
3. 写前强校验 (Pre-write Capacity Guard)：所有入库/采录脚本写入 R2 前必须经过本守卫核验。
=============================================================================
"""

import os
import sys
import json
import time
import socket
import boto3
from botocore.config import Config
from typing import Tuple, Dict, Any, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

# CF 边缘 IP Pinning
_orig_getaddrinfo = socket.getaddrinfo
def _patched_getaddrinfo(host, port, *args, **kwargs):
    if host and host.endswith(".r2.cloudflarestorage.com"):
        return _orig_getaddrinfo("172.64.190.1", port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _patched_getaddrinfo

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

# 官方商业计费标准
SAFE_CAPACITY_LIMIT_BYTES = int(9.50 * 1000 * 1000 * 1000)  # 9.50 GB 红色熔断封箱线
FREE_MAX_CAPACITY_BYTES = int(10.00 * 1000 * 1000 * 1000)   # 10.00 GB 免费额度底线
WARN_CAPACITY_LIMIT_BYTES = int(9.00 * 1000 * 1000 * 1000)  # 9.00 GB 黄色预警线

class R2CapacityFuseBrokenException(Exception):
    """当存储桶容量超过或写入后将突破 9.50 GB 熔断红线时抛出"""
    pass

class R2BucketWriteLockedException(Exception):
    """当存储桶已被标记为只读/封箱或禁止写入时抛出"""
    pass

_USAGE_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 180  # 3 分钟本地缓存，兼顾实时性与 S3 API 开销

def get_r2_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"R2 配置文件不存在: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_bucket_realtime_bytes(account_key: str, cfg: dict, force_refresh: bool = False) -> int:
    """获取指定桶当前的真实物理占用字节数 (优先读取 r2_stats.json，零时延)"""
    now = time.time()
    cached = _USAGE_CACHE.get(account_key)
    if not force_refresh and cached and (now - cached["time"] < CACHE_TTL_SECONDS):
        return cached["bytes"]

    # 1. 优先读取 backend/frontend/admin/r2_stats.json 快照
    stats_path = os.path.join(BASE_DIR, "frontend", "admin", "r2_stats.json")
    if not force_refresh and os.path.exists(stats_path):
        try:
            with open(stats_path, "r", encoding="utf-8") as f:
                stats_data = json.load(f)
                # 遍历 bucket1..bucket16 找到匹配 name 的桶
                b_target_name = cfg["buckets"][account_key]["name"]
                for k, v in stats_data.items():
                    if isinstance(v, dict) and v.get("name") == b_target_name:
                        b_bytes = v.get("used_bytes") or int(v.get("used_gb", 0) * 1e9)
                        _USAGE_CACHE[account_key] = {
                            "time": now,
                            "bytes": b_bytes,
                            "count": v.get("total_objects", 0)
                        }
                        return b_bytes
        except Exception:
            pass

    # 2. 备用通过 S3 实时查询
    b_cfg = cfg["buckets"].get(account_key)
    if not b_cfg:
        raise ValueError(f"未找到存储桶配置: {account_key}")

    s3 = boto3.client(
        "s3",
        endpoint_url=b_cfg["endpoint_url"],
        aws_access_key_id=b_cfg["access_key_id"],
        aws_secret_access_key=b_cfg["secret_access_key"],
        region_name="auto",
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4", connect_timeout=5, read_timeout=10, retries={"max_attempts": 2})
    )

    total_bytes = 0
    total_objects = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=b_cfg["name"]):
        for obj in page.get("Contents", []):
            total_bytes += obj["Size"]
            total_objects += 1

    _USAGE_CACHE[account_key] = {
        "time": now,
        "bytes": total_bytes,
        "count": total_objects
    }
    return total_bytes

def pre_write_capacity_guard(account_key: str, incoming_bytes: int = 0) -> Tuple[bool, str, dict]:
    """
    写前容量强校验熔断函数 (Pre-write Capacity Guard)
    所有上传/写入操作必须在执行底层 put 之前通过本函数的检验！
    """
    cfg = get_r2_config()
    b_cfg = cfg["buckets"].get(account_key)
    if not b_cfg:
        raise ValueError(f"❌ 存储桶 {account_key} 不存在于配置中！")

    # 1. 检查只读状态锁
    if not b_cfg.get("allow_writes", True) or b_cfg.get("status") in ["frozen_readonly", "sealed_readonly"]:
        reason = f"🛑 [安全熔断] 存储桶 {b_cfg['name']} ({account_key}) 处于只读封箱状态 ({b_cfg.get('status')})，物理严禁写入！"
        raise R2BucketWriteLockedException(reason)

    # 2. 检查全局安全阀
    safety_valve = cfg.get("global_safety_valve", {})
    if safety_valve.get("active") and not safety_valve.get("allow_writes", True):
        reason = f"🛑 [全局安全阀触发] 系统已处于全局写锁定状态: {safety_valve.get('reason')}"
        raise R2BucketWriteLockedException(reason)

    # 3. 检查物理容量与即将写入增量
    current_bytes = get_bucket_realtime_bytes(account_key, cfg)
    predicted_bytes = current_bytes + incoming_bytes

    if predicted_bytes >= SAFE_CAPACITY_LIMIT_BYTES:
        curr_gb = current_bytes / 1e9
        pred_gb = predicted_bytes / 1e9
        err_msg = (
            f"\n🚨 [CRITICAL FUSE BROKEN] 存储桶 {b_cfg['name']} ({account_key}) 触发 9.50 GB 红色熔断线！\n"
            f"   当前用量: {curr_gb:.3f} GB / 10.00 GB ({(current_bytes / FREE_MAX_CAPACITY_BYTES)*100:.1f}%)\n"
            f"   写入增量: {incoming_bytes / 1e6:.2f} MB -> 预测将达 {pred_gb:.3f} GB\n"
            f"   ⚠️ 严禁继续向该桶写入！请将写入路由切换至低水位待命桶 (如 Bucket 13/14)！"
        )
        # 自动将配置文件中该桶写入状态冻结，杜绝并发越界
        try:
            cfg["buckets"][account_key]["status"] = "sealed_readonly"
            cfg["buckets"][account_key]["allow_writes"] = False
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        raise R2CapacityFuseBrokenException(err_msg)

    # 4. 黄色预警检查
    if predicted_bytes >= WARN_CAPACITY_LIMIT_BYTES:
        print(f"⚠️ [容量预警] 存储桶 {b_cfg['name']} 即将达到 {(predicted_bytes / FREE_MAX_CAPACITY_BYTES)*100:.1f}%，请留意备用桶准备！")

    return True, "SAFE", {
        "current_gb": current_bytes / 1e9,
        "remaining_safe_gb": (SAFE_CAPACITY_LIMIT_BYTES - current_bytes) / 1e9
    }

def get_recommended_write_bucket() -> Tuple[str, dict]:
    """
    智能路由推荐：在集群所有桶中自动找出当前容量最低、最安全的就绪待命桶
    """
    cfg = get_r2_config()
    candidates = []

    for acc_key, b_cfg in cfg["buckets"].items():
        if b_cfg.get("allow_writes", False) and b_cfg.get("status") in ["active", "standby"]:
            try:
                used_bytes = get_bucket_realtime_bytes(acc_key, cfg)
                if used_bytes < WARN_CAPACITY_LIMIT_BYTES:
                    candidates.append((acc_key, used_bytes, b_cfg))
            except Exception:
                pass

    if not candidates:
        raise RuntimeError("🚨 [全网集群熔断告警] 全网已无可用的低于 9.00 GB 的写入桶！请立即开辟新桶！")

    # 按用量最少排序
    candidates.sort(key=lambda x: x[1])
    best_acc, best_bytes, best_cfg = candidates[0]
    return best_acc, {
        "name": best_cfg["name"],
        "used_gb": best_bytes / 1e9,
        "remaining_gb": (SAFE_CAPACITY_LIMIT_BYTES - best_bytes) / 1e9
    }

def safe_r2_put_object(s3_client, bucket_name: str, account_key: str, key: str, body: bytes, content_type: str = "application/octet-stream", **kwargs) -> dict:
    """
    带熔断看门狗的 S3 PutObject 安全入口
    凡是通过本函数上传的对象，均强制经过 9.50 GB 红色熔断守卫！
    """
    body_bytes_len = len(body) if isinstance(body, (bytes, bytearray)) else 0
    # 强制执行写前容量熔断校验
    pre_write_capacity_guard(account_key, incoming_bytes=body_bytes_len)

    # 校验通过，执行底层上传
    resp = s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=body,
        ContentType=content_type,
        **kwargs
    )

    # 增量维护内存缓存
    if account_key in _USAGE_CACHE:
        _USAGE_CACHE[account_key]["bytes"] += body_bytes_len
        _USAGE_CACHE[account_key]["count"] += 1

    return resp

if __name__ == "__main__":
    print("=" * 70)
    print("🛡️ 测试 R2 Safety Guard 写前容量熔断看门狗...")
    print("=" * 70)
    try:
        best_bucket, info = get_recommended_write_bucket()
        print(f"✅ 当前全网最推荐安全写入桶: {best_bucket} ({info['name']})")
        print(f"   当前用量: {info['used_gb']:.2f} GB | 剩余安全空间: {info['remaining_gb']:.2f} GB")
        
        # 测试 12 桶熔断拦截
        print("\n🧪 测试向已封箱的第 12 桶尝试写入拦截:")
        try:
            pre_write_capacity_guard("account_12", 1024)
            print("❌ 拦截失效！未抛出异常！")
        except R2BucketWriteLockedException as e:
            print("✅ 成功拦截封箱桶写入:", e)

    except Exception as e:
        print("❌ 看门狗运行异常:", e)
