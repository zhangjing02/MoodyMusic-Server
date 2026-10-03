# -*- coding: utf-8 -*-
"""
MoodyMusic Global Physical R2 Circuit Breaker & Auto-Locking Watchdog
=============================================================================
核心使命：
1. 底层物理拦截：在 Python Boto3 最底层（BaseClient._make_api_call）0毫秒阻断。
2. 动态自愈与零人工上锁：未来任意桶（如第 17、18 桶）一旦容量达标（>= 9.00 GB），
   底层看门狗在拦截的同时，会自动将该桶标记为 sealed_readonly，并自动将主力写入桶
   转移到下一个可用桶，更新 r2_config.json，完全无需人工干预！
3. 进程内写入累加器 (In-flight Accumulator)：
   实时跟踪单进程累计写入字节数，杜绝大批量采录脚本在单次运行中将空桶写爆。
=============================================================================
"""
import os
import sys
import json
import threading

# 9.00 GB 自动封箱阈值 (Cloudflare 十进制 1 GB = 10^9 字节)
WARN_LIMIT_BYTES = 9 * 1000 * 1000 * 1000
MAX_SAFE_BYTES = int(9.5 * 1000 * 1000 * 1000)

# 保底封箱桶（历史超限/保护桶列表，兜底防线）
STATIC_HARD_LOCKED_BUCKETS = {
    "moody-music-asset",       # Bucket 01: 8.29 GB
    "moody-music-asset-02",    # Bucket 02: 9.04 GB
    "moody-music-asset-03",    # Bucket 03: 8.96 GB
    "moody-music-asset-04",    # Bucket 04: 9.28 GB
    "moody-music-asset-05",    # Bucket 05: 9.12 GB
    "moody-music-asset-06",    # Bucket 06: 9.16 GB
    "moody-music-asset-07",    # Bucket 07: 9.17 GB
    "moody-music-asset-08",    # Bucket 08: 9.55 GB
    "moody-music-asset-09",    # Bucket 09: 9.04 GB
    "moody-music-asset-10",    # Bucket 10: 9.68 GB
    "moody-music-asset-11",    # Bucket 11: 8.90 GB
    "moody-music-asset-12",    # Bucket 12: 6.84 GB (排雷降温中)
    "moody-music-asset-15",    # Bucket 15: 8.46 GB (已承接大批核心资产)
    "moody-music-asset-16",    # Bucket 16: 8.31 GB (已承接大批核心资产)
}

S3_WRITE_OPERATIONS = {
    'PutObject',
    'UploadPart',
    'CreateMultipartUpload',
    'CopyObject',
    'PutBucketPolicy',
    'PutBucketAcl',
    'PutBucketCors'
}

# 进程内写入字节累加追踪 (线程安全)
_LOCK = threading.Lock()
_IN_FLIGHT_WRITTEN = {}

def _find_config_paths():
    """动态寻找项目配置文件与大盘缓存路径"""
    candidates = [
        r"e:\Workspace\AI-Project\MoodyMusic-Workspace\backend",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")),
    ]
    cfg_file = None
    stats_file = None
    for c in candidates:
        cf = os.path.join(c, "r2_config.json")
        sf = os.path.join(c, "frontend", "admin", "r2_stats.json")
        if os.path.exists(cf) and not cfg_file:
            cfg_file = cf
        if os.path.exists(sf) and not stats_file:
            stats_file = sf
    return cfg_file, stats_file

def _get_known_storage():
    """获取所有桶的最新已知用量与只读配置"""
    cfg_file, stats_file = _find_config_paths()
    known_bytes = {}
    locked_buckets = set(STATIC_HARD_LOCKED_BUCKETS)
    cfg_data = None

    if stats_file and os.path.exists(stats_file):
        try:
            with open(stats_file, 'r', encoding='utf-8') as f:
                stats = json.load(f)
            for k, v in stats.items():
                if isinstance(v, dict) and 'name' in v and 'used_bytes' in v:
                    b_name = v['name'].strip().lower()
                    b_bytes = int(v['used_bytes'])
                    known_bytes[b_name] = b_bytes
                    if b_bytes >= WARN_LIMIT_BYTES:
                        locked_buckets.add(b_name)
        except Exception:
            pass

    if cfg_file and os.path.exists(cfg_file):
        try:
            with open(cfg_file, 'r', encoding='utf-8') as f:
                cfg_data = json.load(f)
            buckets = cfg_data.get('buckets', {})
            for b_key, b_val in buckets.items():
                b_name = b_val.get('name', '').strip().lower()
                if not b_name:
                    continue
                if not b_val.get('allow_writes', False):
                    locked_buckets.add(b_name)
                if b_val.get('status') in ['sealed_readonly', 'frozen_readonly']:
                    locked_buckets.add(b_name)
        except Exception:
            pass

    return cfg_file, cfg_data, known_bytes, locked_buckets

def _auto_lock_and_failover(exceeded_bucket, current_bytes, cfg_file, cfg_data):
    """当任意桶超限时，自动修改配置文件：将该桶封箱并故障转移到下一个可用桶"""
    if not cfg_file or not cfg_data or not os.path.exists(cfg_file):
        return None

    try:
        buckets = cfg_data.get('buckets', {})
        target_key = None
        for k, v in buckets.items():
            if v.get('name', '').strip().lower() == exceeded_bucket.lower():
                target_key = k
                break

        if target_key:
            # 1. 自动上锁封箱
            buckets[target_key]['allow_writes'] = False
            buckets[target_key]['status'] = 'sealed_readonly'

            # 2. 检查是否需要故障转移活跃写入桶
            valve = cfg_data.get('global_safety_valve', {})
            active_bucket = valve.get('active_target_bucket')

            new_target = None
            if active_bucket == target_key or not active_bucket:
                # 寻找下一个允许写入且未超标的桶
                for cand_k, cand_v in buckets.items():
                    cand_name = cand_v.get('name', '').strip().lower()
                    if cand_k != target_key and cand_v.get('allow_writes', False) and cand_name not in STATIC_HARD_LOCKED_BUCKETS:
                        new_target = cand_k
                        break
                if new_target:
                    valve['active_target_bucket'] = new_target
                    buckets[new_target]['status'] = 'active_write'
                    valve['reason'] = f"存储桶 [{exceeded_bucket}] 已达警戒水位 ({current_bytes / 1e9:.2f} GB) 自动封箱，主力写入平滑转移至 [{buckets[new_target].get('name')}]"

            # 3. 原子写回配置文件
            with open(cfg_file, 'w', encoding='utf-8') as f:
                json.dump(cfg_data, f, ensure_ascii=False, indent=2)

            return new_target
    except Exception as e:
        sys.stderr.write(f"[物理看门狗自动更新配置失败]: {e}\n")
    return None

def install_guard():
    try:
        import botocore.client
    except ImportError:
        return

    orig_api_call = botocore.client.BaseClient._make_api_call

    if getattr(orig_api_call, "_moody_guarded", False):
        return  # 防止重复注入

    def guarded_make_api_call(self, operation_name, api_params):
        if operation_name in S3_WRITE_OPERATIONS and api_params:
            raw_bucket = api_params.get('Bucket')
            if raw_bucket:
                bucket = str(raw_bucket).strip().lower()
                cfg_file, cfg_data, known_bytes, locked_buckets = _get_known_storage()

                # 计算本次写入字节数
                op_bytes = 0
                body = api_params.get('Body')
                if body is not None:
                    if isinstance(body, (bytes, bytearray)):
                        op_bytes = len(body)
                    elif hasattr(body, '__len__'):
                        op_bytes = len(body)
                    elif hasattr(body, 'seek') and hasattr(body, 'tell'):
                        try:
                            cur_pos = body.tell()
                            body.seek(0, 2)
                            op_bytes = body.tell() - cur_pos
                            body.seek(cur_pos)
                        except Exception:
                            op_bytes = 0

                with _LOCK:
                    current_known = known_bytes.get(bucket, 0)
                    accumulated = _IN_FLIGHT_WRITTEN.get(bucket, 0)
                    projected_total = current_known + accumulated + op_bytes

                    # 判定条件：① 已在锁定名单中；② 当前总容量已达 9.00 GB 警戒线
                    is_locked = (bucket in locked_buckets)
                    is_over_watermark = (projected_total >= WARN_LIMIT_BYTES)

                    if is_locked or is_over_watermark:
                        # 触发自动封箱与故障转移
                        new_target = _auto_lock_and_failover(bucket, projected_total, cfg_file, cfg_data)
                        failover_info = f"已自动将该桶封箱，并将主力写入切换至: [{new_target}]" if new_target else "已自动将该桶标记为只读封箱！"

                        err_msg = (
                            f"\n{'!'*85}\n"
                            f"🚨 [物理看门狗·自动熔断拦截] 严重保护警报：\n"
                            f"   存储桶: [{bucket}]\n"
                            f"   当前已知容量 + 本次增量: {projected_total / 1e9:.3f} GB (警戒线 9.00 GB / 绝对红线 9.50 GB)\n"
                            f"   状态: 触发自动化物理封箱断写！\n"
                            f"   自愈动作: {failover_info}\n"
                            f"   底线声明: 依据 MoodyMusic P0 级铁律，拒绝向满载桶写入任何新资产，彻底消除超额账单隐患！\n"
                            f"{'!'*85}\n"
                        )
                        raise PermissionError(err_msg)

                    # 记录累加
                    _IN_FLIGHT_WRITTEN[bucket] = accumulated + op_bytes

        return orig_api_call(self, operation_name, api_params)

    guarded_make_api_call._moody_guarded = True
    botocore.client.BaseClient._make_api_call = guarded_make_api_call

# 自动在模块载入时安装
install_guard()
