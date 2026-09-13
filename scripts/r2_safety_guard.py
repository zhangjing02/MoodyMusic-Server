#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - Cloudflare R2 全局存储写入安全阀门卫 (Global Storage Write Safety Guard)
=============================================================================
作用：
当三桶集群用量接近满额时，硬性拦截所有 Python 脚本、CLI 管道或后台任务向 R2 执行任何写入/上传操作。
如果安全阀被激活：
1. assert_write_allowed() 直接阻断并抛出 PermissionError
2. install_boto3_safety_guard() 深度劫持 boto3 S3 Client 的写操作 (put_object, upload_file 等)
=============================================================================
"""

import os
import sys
import json

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

class StorageSafetyValveActiveError(PermissionError):
    """当存储安全阀开启时尝试写入触发的致命异常"""
    pass

def is_safety_valve_active() -> tuple[bool, str]:
    if not os.path.exists(CONFIG_PATH):
        return True, "r2_config.json 不存在，默认开启安全阀保护"
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        valve = cfg.get("global_safety_valve", {})
        if valve.get("active", False):
            reason = valve.get("reason", "存储总用量已达警戒红线，安全阀已生效")
            return True, reason
        
        buckets = cfg.get("buckets", {})
        all_frozen = all(b.get("status") == "frozen_readonly" for b in buckets.values())
        if all_frozen and len(buckets) > 0:
            return True, "所有存储桶均处于 frozen_readonly 状态"
        
        return False, "安全阀未激活"
    except Exception as e:
        return True, f"读取安全阀配置异常: {e}，默认拦截保护"

def assert_write_allowed(bucket_name: str = None):
    """
    在任何写入、上传、同步逻辑开始前必须调用的硬性守卫。
    """
    active, reason = is_safety_valve_active()
    if active:
        msg = f"\n{'=' * 80}\n🚨【全局存储安全阀已激活 - 写入已被硬阻断】\n原因: {reason}\n当前所有存储桶已切换为只读保护模式 (READ-ONLY)。\n严禁向 R2 写入任何新音频或资产文件，防止超出 10GB 免费限额！\n{'=' * 80}\n"
        print(msg, file=sys.stderr, flush=True)
        raise StorageSafetyValveActiveError(msg)

def install_boto3_safety_guard():
    """
    深度劫持 boto3，对任何向 S3/R2 发起的写操作进行拦截
    """
    try:
        from botocore.client import BaseClient
        
        orig_call = BaseClient._make_api_call

        BLOCKED_ACTIONS = {
            'PutObject', 'UploadPart', 'CreateMultipartUpload',
            'CompleteMultipartUpload', 'CopyObject', 'UploadFile',
            'UploadFileObj', 'PutObjectTagging', 'PutBucketPolicy'
        }

        def guarded_api_call(self, operation_name, api_params):
            if operation_name in BLOCKED_ACTIONS:
                active, reason = is_safety_valve_active()
                if active:
                    bucket = api_params.get('Bucket', 'Unknown')
                    key = api_params.get('Key', 'Unknown')
                    raise StorageSafetyValveActiveError(
                        f"🚨 [R2 Safety Guard] 尝试向 R2 执行 {operation_name} (Bucket={bucket}, Key={key}) 被安全阀硬阻断！\n原因: {reason}"
                    )
            return orig_call(self, operation_name, api_params)

        BaseClient._make_api_call = guarded_api_call
    except Exception as e:
        pass

install_boto3_safety_guard()

if __name__ == "__main__":
    active, reason = is_safety_valve_active()
    print(f"安全阀状态: {'🔴 已激活 (禁止写入)' if active else '🟢 未激活'}")
    print(f"状态详情: {reason}")
    try:
        assert_write_allowed()
    except StorageSafetyValveActiveError:
        print("✅ 守卫安全拦截测试成功！")
