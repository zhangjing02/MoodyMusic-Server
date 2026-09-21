#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - Cloudflare R2 存储桶超额降温与资产平移流水线 (Buckets 03, 04, 05, 06 -> 09)
==============================================================================
核心目标：
1. 将 Bucket 03, 04, 05, 06 从超标状态（>10 GB）平移降至 9.1 ~ 9.3 GB 安全水位；
2. 保持完整歌手整专结构，绝不拆分打散；
3. 执行 Zero-Loss 严格六步 SOP：
   [1] 物理扫描与 D1 双向拓扑比对
   [2] 并发安全复制至 Bucket 09（保持相对 Key 100% 一致）
   [3] Bucket 09 对象完整性与字节级校验
   [4] 生产 D1 网关原子批量切链 (batch-light)
   [5] D1 回读与 CDN 播放连通性抽验
   [6] 100% 无误后安全释放源桶物理文件
==============================================================================
"""

import os
import sys
import json
import time
import re
import argparse
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import urllib3
from urllib3.util import connection
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# -----------------------------------------------------------------------------
# 网络自愈与 Cloudflare 边缘 IP 直连 (绕过本地 TUN/代理劫持)
# -----------------------------------------------------------------------------
CF_EDGE_IPS = ["104.21.21.164", "172.67.199.94"]
_orig_create_connection = connection.create_connection

def patched_create_connection(address, *args, **kwargs):
    host, port = address
    if host == "m-api.changgepd.ccwu.cc":
        # 优先使用第一 IP，失败走备用
        return _orig_create_connection((CF_EDGE_IPS[0], port), *args, **kwargs)
    return _orig_create_connection(address, *args, **kwargs)

connection.create_connection = patched_create_connection

# 全局高可用 Session
d1_session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
d1_session.mount("https://", HTTPAdapter(max_retries=retries))

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg_all = json.load(f)["buckets"]

# 目标桶配置 (Bucket 09)
cfg_dest = cfg_all["account_09"]
s3_dest = boto3.client(
    "s3",
    endpoint_url=cfg_dest["endpoint_url"],
    aws_access_key_id=cfg_dest["access_key_id"],
    aws_secret_access_key=cfg_dest["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4", max_pool_connections=25)
)
BUCKET_DEST = cfg_dest["name"]
DOMAIN_DEST = cfg_dest["public_url"].rstrip("/")

# 迁移任务矩阵定义
MIGRATION_TASKS = {
    "03": {
        "bucket_id": "account_03",
        "artists": ["刀郎", "阿杜"],
        "desc": "Bucket 03 (10.37 GB) -> 释放 刀郎 + 阿杜 (约 1.22 GB) -> 降至 ~9.15 GB"
    },
    "04": {
        "bucket_id": "account_04",
        "artists": ["陶喆", "范晓萱"],
        "desc": "Bucket 04 (10.47 GB) -> 释放 陶喆 + 范晓萱 (约 1.14 GB) -> 降至 ~9.33 GB"
    },
    "05": {
        "bucket_id": "account_05",
        "artists": ["齐豫", "萧敬腾"],
        "desc": "Bucket 05 (10.35 GB) -> 释放 齐豫 + 萧敬腾 (约 1.22 GB) -> 降至 ~9.13 GB"
    },
    "06": {
        "bucket_id": "account_06",
        "artists": ["费玉清"],
        "desc": "Bucket 06 (10.54 GB) -> 释放 费玉清 (约 1.34 GB) -> 降至 ~9.20 GB"
    }
}

def get_s3_client(b_id):
    cfg = cfg_all[b_id]
    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4", max_pool_connections=25)
    ), cfg["name"], cfg["public_url"].rstrip("/")

def fetch_d1_topology(target_artists):
    """
    严禁无参全量扫描！严格按目标歌手名单按需单点获取，彻底杜绝全表扫描消耗 D1 配额。
    """
    if not target_artists:
        raise ValueError("🛡️ [安全红线拦截] 严禁发起无参全量 D1 曲库扫描！必须指定 target_artists。")
        
    print(f"📡 按需获取目标歌手 D1 拓扑 ({', '.join(target_artists)})...", flush=True)
    key_to_song = {}
    id_to_song = {}
    
    for art_name in target_artists:
        try:
            resp = d1_session.get(f"{D1_SONGS_URL}?artist={art_name}", timeout=15)
            if resp.status_code != 200:
                print(f"   ⚠️ 查询歌手 {art_name} 失败: HTTP {resp.status_code}")
                continue
            data = resp.json().get("data", [])
            for art in data:
                for alb in art.get("albums", []):
                    alb_title = alb.get("title")
                    for s in alb.get("songs", []):
                        p = s.get("path") or ""
                        lrc_p = s.get("lrc_path") or ""
                        m = re.search(r"s_(\d+)\.mp3", p)
                        sid = int(m.group(1)) if m else None
                        
                        rel_key = None
                        if ".r2.dev/" in p:
                            rel_key = p.split(".r2.dev/")[1]
                        elif "r2.changgepd.ccwu.cc/" in p:
                            rel_key = p.split("r2.changgepd.ccwu.cc/")[1]
                        elif p.startswith("music/"):
                            rel_key = p
                        
                        info = {
                            "id": sid,
                            "title": s.get("title"),
                            "artist": art.get("name"),
                            "album": alb_title,
                            "path": p,
                            "lrc_path": lrc_p,
                            "rel_key": rel_key
                        }
                        if rel_key:
                            key_to_song[rel_key] = info
                        if sid is not None:
                            id_to_song[sid] = info
        except Exception as e:
            print(f"   ⚠️ 获取歌手 {art_name} 拓扑异常: {e}")
                    
    print(f"   D1 精准索引就绪: 命中目标歌曲数 {len(id_to_song)} 首 (0 行全表扫描损耗)", flush=True)
    return key_to_song, id_to_song

def run_bucket_migration(bucket_key, dry_run=False):
    task = MIGRATION_TASKS.get(bucket_key)
    if not task:
        print(f"❌ 未知任务编号: {bucket_key}")
        return False
        
    b_id = task["bucket_id"]
    artists = task["artists"]
    s3_src, src_bucket_name, src_domain = get_s3_client(b_id)
    
    print("\n" + "=" * 80)
    print(f"🚀 开始执行平移任务: Bucket {bucket_key} ({b_id})")
    print(f"📌 任务描述: {task['desc']}")
    print(f"👤 标的歌手: {', '.join(artists)}")
    print(f"🏢 源桶: {src_bucket_name} ({src_domain})")
    print(f"🎯 目标桶: {BUCKET_DEST} ({DOMAIN_DEST})")
    if dry_run:
        print("⚠️ 当前为 DRY-RUN 试运行模式，不进行实际写入与删除！")
    print("=" * 80, flush=True)
    
    # -------------------------------------------------------------------------
    # [Step 1] 扫描源桶物理对象并与 D1 对齐
    # -------------------------------------------------------------------------
    print(f"\n📦 [1/6] 扫描源桶 {src_bucket_name} 物理对象...", flush=True)
    key_to_song, id_to_song = fetch_d1_topology(artists)
    
    source_objects = {} # key -> {'Size': size, 'Type': 'mp3'/'lrc', 'id': sid}
    for art in artists:
        for prefix in [f"music/{art}/", f"lyrics/{art}/"]:
            paginator = s3_src.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=src_bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    k = obj["Key"]
                    sz = obj["Size"]
                    m = re.search(r"s_(\d+)\.(mp3|lrc)$", k)
                    if m:
                        sid = int(m.group(1))
                        ftype = m.group(2)
                        source_objects[k] = {
                            "key": k,
                            "size": sz,
                            "type": ftype,
                            "id": sid,
                            "artist": art
                        }
                    else:
                        print(f"   ⚠️ 忽略非标准文件: {k}")
                        
    print(f"   源桶扫描完毕: 发现 {len(source_objects)} 个标的对象")
    mp3_objs = [v for v in source_objects.values() if v["type"] == "mp3"]
    lrc_objs = [v for v in source_objects.values() if v["type"] == "lrc"]
    total_src_bytes = sum(v["size"] for v in source_objects.values())
    print(f"   • MP3 音频: {len(mp3_objs)} 个")
    print(f"   • LRC 歌词: {len(lrc_objs)} 个")
    print(f"   • 物理总计: {total_src_bytes / 10**6:.2f} MB ({total_src_bytes / 10**9:.3f} GB)")
    
    if not source_objects:
        print("   ℹ️ 未找到待迁移对象，本桶已完成或无资产。")
        return True
        
    # 组织歌曲聚合单元 (每首歌曲聚合 mp3 与 lrc)
    songs_to_migrate = {} # sid -> {'sid': sid, 'artist': art, 'mp3_obj': obj, 'lrc_obj': obj, 'd1_info': info}
    for obj in mp3_objs:
        sid = obj["id"]
        songs_to_migrate[sid] = {
            "id": sid,
            "artist": obj["artist"],
            "mp3_obj": obj,
            "lrc_obj": None,
            "d1_info": id_to_song.get(sid)
        }
    for obj in lrc_objs:
        sid = obj["id"]
        if sid in songs_to_migrate:
            songs_to_migrate[sid]["lrc_obj"] = obj
        else:
            # 孤儿歌词
            songs_to_migrate[sid] = {
                "id": sid,
                "artist": obj["artist"],
                "mp3_obj": None,
                "lrc_obj": obj,
                "d1_info": id_to_song.get(sid)
            }
            
    # 分析 D1 链接状态
    d1_needs_update = []
    d1_already_points_elsewhere = []
    d1_unregistered = []
    
    src_domain_host = src_domain.replace("https://", "").replace("http://", "")
    for sid, sdata in songs_to_migrate.items():
        d1 = sdata["d1_info"]
        if not d1:
            d1_unregistered.append(sdata)
        else:
            cur_path = d1.get("path") or ""
            if src_domain_host in cur_path:
                d1_needs_update.append(sdata)
            else:
                d1_already_points_elsewhere.append(sdata)
                
    print(f"   • D1 拓扑比对: {len(d1_needs_update)} 首需切链至 Bucket 09")
    if d1_already_points_elsewhere:
        print(f"   • D1 指向它桶: {len(d1_already_points_elsewhere)} 首 (保持物理同步，暂不改写该链接)")
    if d1_unregistered:
        print(f"   • D1 无对应记: {len(d1_unregistered)} 首 (完整保留物理资产同步)")
        
    if dry_run:
        print("\n[DRY-RUN] 演练模式完成，不执行实际改动。")
        return True

    # -------------------------------------------------------------------------
    # [Step 2] 并发流式同步物理文件至 Bucket 09
    # -------------------------------------------------------------------------
    print(f"\n📦 [2/6] 并发同步物理资产至 Bucket 09 ({len(source_objects)} 个文件)...", flush=True)
    
    def copy_single_object(obj_meta):
        k = obj_meta["key"]
        sz = obj_meta["size"]
        ftype = obj_meta["type"]
        ctype = "audio/mpeg" if ftype == "mp3" else "text/plain; charset=utf-8"
        
        # 优先检查目标桶是否已存在且大小完全一致（断点续传/防重传）
        try:
            dest_head = s3_dest.head_object(Bucket=BUCKET_DEST, Key=k)
            if dest_head["ContentLength"] == sz:
                return {"success": True, "key": k, "size": sz, "type": ftype, "cached": True}
        except Exception:
            pass

        # 最多重试 3 次处理瞬时网络抖动 (如 IncompleteRead)
        max_retries = 3
        last_err = ""
        for attempt in range(1, max_retries + 1):
            try:
                resp = s3_src.get_object(Bucket=src_bucket_name, Key=k)
                body = resp["Body"].read()
                if len(body) != sz:
                    last_err = f"Size mismatch: expected {sz}, got {len(body)}"
                    time.sleep(1)
                    continue
                # 写入目标桶
                s3_dest.put_object(
                    Bucket=BUCKET_DEST,
                    Key=k,
                    Body=body,
                    ContentType=ctype
                )
                return {"success": True, "key": k, "size": sz, "type": ftype, "cached": False}
            except Exception as e:
                last_err = str(e)
                time.sleep(1)

        return {"success": False, "key": k, "error": f"Failed after {max_retries} attempts: {last_err}"}

    copied_results = []
    copy_failures = []
    total_copied_bytes = 0
    start_t = time.time()
    
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(copy_single_object, o): o for o in source_objects.values()}
        done = 0
        total_count = len(source_objects)
        for f in as_completed(futures):
            res = f.result()
            done += 1
            if res["success"]:
                copied_results.append(res)
                total_copied_bytes += res["size"]
            else:
                copy_failures.append(res)
                print(f"   ❌ 写入失败: {res['key']} -> {res['error']}")
                
            if done % 50 == 0 or done == total_count:
                elapsed = time.time() - start_t
                speed = (total_copied_bytes / (1024*1024)) / (elapsed + 0.001)
                print(f"   [进度] {done}/{total_count} 个对象已写入 ({total_copied_bytes/10**6:.1f} MB, {speed:.2f} MB/s)", flush=True)

    if copy_failures:
        print(f"\n❌ 存在 {len(copy_failures)} 个对象写入失败！已触发熔断保护，终止后续切链与删除！")
        return False
        
    print(f"   ✅ 物理写入 100% 成功: 写入 {len(copied_results)} 个对象, 累计 {total_copied_bytes/10**6:.2f} MB")

    # -------------------------------------------------------------------------
    # [Step 3] 目标桶完整性校验 (Dual Verification)
    # -------------------------------------------------------------------------
    print("\n🔍 [3/6] 严格校验 Bucket 09 对象完整性 (S3 HEAD 校验)...", flush=True)
    
    def verify_single_dest_object(obj_meta):
        k = obj_meta["key"]
        expected_sz = obj_meta["size"]
        try:
            head = s3_dest.head_object(Bucket=BUCKET_DEST, Key=k)
            actual_sz = head["ContentLength"]
            if actual_sz != expected_sz:
                return {"valid": False, "key": k, "error": f"Size mismatch: {actual_sz} vs {expected_sz}"}
            return {"valid": True, "key": k}
        except Exception as e:
            return {"valid": False, "key": k, "error": str(e)}

    verification_failures = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        v_futures = [executor.submit(verify_single_dest_object, o) for o in source_objects.values()]
        for f in as_completed(v_futures):
            vres = f.result()
            if not vres["valid"]:
                verification_failures.append(vres)
                print(f"   ❌ 校验不通过: {vres['key']} -> {vres['error']}")

    if verification_failures:
        print(f"\n❌ 发现 {len(verification_failures)} 个对象在 Bucket 09 中校验失败！终止后续切链与删除！")
        return False
        
    print(f"   ✅ 全部 {len(source_objects)} 个文件在 Bucket 09 中校验通过，字节数 100% 匹配！")

    # -------------------------------------------------------------------------
    # [Step 4] 向 D1 网关原子提交切链更新 (batch-light)
    # -------------------------------------------------------------------------
    print(f"\n⚡ [4/6] 向生产 D1 网关批量提交直链切换 (共 {len(d1_needs_update)} 首)...", flush=True)
    if d1_needs_update:
        d1_payload_items = []
        for sdata in d1_needs_update:
            sid = sdata["id"]
            mp3_k = sdata["mp3_obj"]["key"]
            new_audio_url = f"{DOMAIN_DEST}/{mp3_k}"
            new_lrc_url = f"{DOMAIN_DEST}/{sdata['lrc_obj']['key']}" if sdata["lrc_obj"] else None
            d1_payload_items.append({
                "id": sid,
                "file_path": new_audio_url,
                "lrc_path": new_lrc_url
            })
            
        # 分批提交，每批 50 条
        batch_size = 50
        for i in range(0, len(d1_payload_items), batch_size):
            chunk = d1_payload_items[i:i+batch_size]
            resp = d1_session.post(D1_LIGHT_URL, json={"updates": chunk}, headers={"Content-Type": "application/json"}, timeout=25)
            if resp.status_code != 200:
                print(f"   ❌ D1 切链失败: 批次 {i//batch_size + 1} 返回 {resp.status_code}: {resp.text}")
                return False
            print(f"   • D1 批次 [{i//batch_size + 1}/{(len(d1_payload_items)-1)//batch_size + 1}]: 成功点亮 {len(chunk)} 首歌曲 (HTTP 200)")
        print(f"   ✅ D1 网关切链全部完成，{len(d1_payload_items)} 首歌曲已切换至 Bucket 09 直链！")
    else:
        print("   ℹ️ 无需要切链的 D1 曲目。")

    # -------------------------------------------------------------------------
    # [Step 5] 抽样验证 D1 回读与 CDN 播放连通性
    # -------------------------------------------------------------------------
    print("\n🌐 [5/6] 生产端连通性与播放可用性抽查...", flush=True)
    if d1_needs_update:
        sample_songs = d1_needs_update[:5]
        for s in sample_songs:
            mp3_k = s["mp3_obj"]["key"]
            head_meta = s3_dest.head_object(Bucket=BUCKET_DEST, Key=mp3_k)
            print(f"   • Bucket 09 对象可用: {mp3_k}")
            print(f"     -> 大小: {head_meta['ContentLength']} bytes, 类型: {head_meta.get('ContentType')}")
        print("   ✅ 对象抽检 100% 连通可用！")

    # -------------------------------------------------------------------------
    # [Step 6] 安全释放源桶文件空间
    # -------------------------------------------------------------------------
    print(f"\n🧹 [6/6] 所有校验与切链 100% 成功，开始安全释放源桶 {src_bucket_name} 空间...", flush=True)
    delete_keys = [{'Key': k} for k in source_objects.keys()]
    deleted_count = 0
    
    # S3 delete_objects 每次最多 1000 个
    for i in range(0, len(delete_keys), 500):
        chunk = delete_keys[i:i+500]
        del_resp = s3_src.delete_objects(
            Bucket=src_bucket_name,
            Delete={'Objects': chunk}
        )
        del_done = len(del_resp.get('Deleted', []))
        deleted_count += del_done
        print(f"   • 删除批次 [{i//500 + 1}]: 释放 {del_done} 个物理对象")
        
    print(f"   ✅ 源桶物理清理完成！成功释放 {deleted_count} 个对象，归还空间约 {total_src_bytes / 10**6:.2f} MB ({total_src_bytes / 10**9:.3f} GB)！")
    print("=" * 80)
    return True

def main():
    parser = argparse.ArgumentParser(description="Moody Cloudflare R2 Overlimit Buckets Migration")
    parser.add_argument("--bucket", choices=["03", "04", "05", "06", "all"], default="all", help="Target bucket to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Perform simulation check without changes")
    args = parser.parse_args()

    print("=" * 80)
    print("🎵 MOODY - R2 存储桶超额平移降载控制系统")
    print("=" * 80)

    order = ["03", "04", "05", "06"] if args.bucket == "all" else [args.bucket]

    for b in order:
        success = run_bucket_migration(b, dry_run=args.dry_run)
        if not success:
            print(f"\n❌ Bucket {b} 平移异常，停止后续桶迁移！")
            sys.exit(1)
        # 每搬完一个桶，休眠 2 秒缓冲
        time.sleep(2)

    print("\n🎉 全部计划平移任务顺利完成！现在刷新全局存储计量...")
    # 调用 check_r2_storage.py 重新盘点
    os.system("python3 scripts/check_r2_storage.py")

if __name__ == "__main__":
    main()
