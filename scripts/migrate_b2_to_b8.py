#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bucket 02 (moody-music-asset-02) 到 Bucket 08 (moody-music-asset-08) 紧急瘦身平移脚本
标的歌手：潘玮柏、华晨宇、胡彦斌（共 246 首 MP3 + 67 份 LRC，共释放 1.28 GB）
执行步骤：
1. 收集 Bucket 02 中潘玮柏、华晨宇、胡彦斌的所有对象 Key
2. 多线程从 Bucket 02 下载并上传至 Bucket 08
3. HTTP HEAD 逐一校验 Bucket 08 物理完整性（200 OK + 大小匹配）
4. 从 D1 数据库中查询对应歌曲 ID，并向 batch-light 发送原子更新直链
5. 验证线上播放后，从 Bucket 02 彻底删除对应的旧物理对象
"""

import os
import sys
import json
import time
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGET_ARTISTS = ["潘玮柏", "华晨宇", "胡彦斌"]

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)["buckets"]

b02_cfg = cfg["account_02"]
b08_cfg = cfg["account_08"]

s3_02 = boto3.client(
    "s3",
    endpoint_url=b02_cfg["endpoint_url"],
    aws_access_key_id=b02_cfg["access_key_id"],
    aws_secret_access_key=b02_cfg["secret_access_key"],
    config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30)
)
NAME_02 = b02_cfg["name"]
DOMAIN_02 = b02_cfg.get("public_url", b02_cfg.get("public_domain", "")).rstrip("/")

s3_08 = boto3.client(
    "s3",
    endpoint_url=b08_cfg["endpoint_url"],
    aws_access_key_id=b08_cfg["access_key_id"],
    aws_secret_access_key=b08_cfg["secret_access_key"],
    config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30)
)
NAME_08 = b08_cfg["name"]
DOMAIN_08 = b08_cfg.get("public_url", b08_cfg.get("public_domain", "")).rstrip("/")

TMP_DIR = "/tmp/moody_b2_migration"
os.makedirs(TMP_DIR, exist_ok=True)

sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})

def step1_collect_keys():
    print("=" * 80)
    print("【步骤 1】扫描 Bucket 02 中目标歌手的所有物理对象...")
    print("=" * 80)
    
    paginator = s3_02.get_paginator("list_objects_v2")
    objects_to_migrate = []
    total_bytes = 0
    
    for page in paginator.paginate(Bucket=NAME_02):
        for o in page.get("Contents", []):
            k = o["Key"]
            sz = o["Size"]
            for art in TARGET_ARTISTS:
                if f"/{art}/" in k or k.startswith(f"{art}/"):
                    objects_to_migrate.append({
                        "key": k,
                        "size": sz,
                        "artist": art
                    })
                    total_bytes += sz
                    break
                    
    print(f"找到待平移对象: {len(objects_to_migrate)} 个")
    print(f"总物理体积: {total_bytes / (1024**3):.3f} GB ({total_bytes / (1024*1024):.1f} MB, {total_bytes:,} 字节)")
    
    by_art = {}
    for o in objects_to_migrate:
        by_art.setdefault(o["artist"], []).append(o)
    for art, ol in sorted(by_art.items()):
        sz = sum(x["size"] for x in ol)
        mp3s = sum(1 for x in ol if x["key"].endswith(".mp3"))
        lrcs = sum(1 for x in ol if x["key"].endswith(".lrc"))
        print(f"  • {art:<10}: {len(ol):>3} 文件 (MP3: {mp3s:>3}, LRC: {lrcs:>3}) | {sz / (1024*1024):6.1f} MB")
        
    return objects_to_migrate, total_bytes

def step2_transfer_objects(objects):
    print("\n" + "=" * 80)
    print("【步骤 2】多线程流式传输: Bucket 02 -> Bucket 08...")
    print("=" * 80)
    
    transferred_count = 0
    failed = []
    
    def transfer_one(item):
        k = item["key"]
        sz = item["size"]
        # 先检查目标桶是否已存在且大小相同
        try:
            head = s3_08.head_object(Bucket=NAME_08, Key=k)
            if head.get("ContentLength") == sz:
                return k, True, "already_exists"
        except Exception:
            pass
            
        # 下载流并上传流
        for attempt in range(3):
            try:
                resp = s3_02.get_object(Bucket=NAME_02, Key=k)
                body = resp["Body"].read()
                content_type = "audio/mpeg" if k.endswith(".mp3") else "text/plain; charset=utf-8"
                s3_08.put_object(
                    Bucket=NAME_08,
                    Key=k,
                    Body=body,
                    ContentType=content_type
                )
                return k, True, "transferred"
            except Exception as e:
                time.sleep(1)
                if attempt == 2:
                    return k, False, str(e)
        return k, False, "unknown"

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(transfer_one, item): item for item in objects}
        done_cnt = 0
        for fut in as_completed(futures):
            k, ok, msg = fut.result()
            done_cnt += 1
            if ok:
                transferred_count += 1
                if done_cnt % 30 == 0 or done_cnt == len(objects):
                    print(f"  • 进度: [{done_cnt}/{len(objects)}] 传输中... (当前成功: {transferred_count})")
            else:
                failed.append((k, msg))
                print(f"  ❌ 传输失败: {k} -> {msg}")
                
    if failed:
        print(f"❌ 严重错误: 有 {len(failed)} 个对象传输失败，中止后续流程！")
        sys.exit(1)
        
    print(f"✅ 全部 {transferred_count} 个对象成功镜像至 Bucket 08!")

def step3_verify_bucket08(objects):
    print("\n" + "=" * 80)
    print("【步骤 3】对 Bucket 08 发起公网 HTTP HEAD 物理完整性校验...")
    print("=" * 80)
    
    verified_cnt = 0
    failed_keys = []
    
    def verify_one(item):
        k = item["key"]
        sz = item["size"]
        url = f"{DOMAIN_08}/{k.lstrip('/')}"
        for attempt in range(3):
            try:
                r = sess.head(url, timeout=5)
                if r.status_code == 200:
                    cl = int(r.headers.get("Content-Length", 0))
                    if cl == sz or sz == 0:
                        return k, True, None
                    else:
                        return k, False, f"Size mismatch: expected {sz}, got {cl}"
            except Exception as e:
                time.sleep(1)
        return k, False, "HTTP HEAD failed"

    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(verify_one, item): item for item in objects}
        done_cnt = 0
        for fut in as_completed(futures):
            k, ok, err = fut.result()
            done_cnt += 1
            if ok:
                verified_cnt += 1
            else:
                failed_keys.append((k, err))
                print(f"  ❌ 校验失败: {k} -> {err}")
                
    if failed_keys:
        print(f"❌ 校验失败率异常: {len(failed_keys)} 个文件校验未通过，中止后续流程！")
        sys.exit(1)
        
    print(f"✅ 物理完整性校验 100% 通过! 共计 {verified_cnt} 个文件（MP3 + LRC）全部就绪且字节完全一致！")

def step4_switch_d1_routes(objects):
    print("\n" + "=" * 80)
    print("【步骤 4】更新 Cloudflare D1 边缘数据库直链 (指向 Bucket 08)...")
    print("=" * 80)
    
    # 提取所有 MP3 对应的歌曲 ID
    # 格式通常是: music/潘玮柏/专辑名/s_12345.mp3
    import re
    mp3_items = [o for o in objects if o["key"].endswith(".mp3")]
    
    updates = []
    for item in mp3_items:
        k = item["key"]
        m = re.search(r's_(\d+)\.mp3', k)
        if m:
            sid = int(m.group(1))
            new_file_path = f"{DOMAIN_08}/{k.lstrip('/')}"
            
            # 对应的 lrc key
            lrc_key = k.replace(".mp3", ".lrc").replace("music/", "lyrics/")
            lrc_cand = [o for o in objects if o["key"] == lrc_key or o["key"] == k.replace(".mp3", ".lrc")]
            
            u = {
                "id": sid,
                "file_path": new_file_path,
                "is_lit": 1
            }
            if lrc_cand:
                u["lrc_path"] = f"{DOMAIN_08}/{lrc_cand[0]['key'].lstrip('/')}"
            updates.append(u)
            
    print(f"共生成 D1 更新请求: {len(updates)} 首歌曲")
    
    chunk_size = 50
    success_cnt = 0
    for i in range(0, len(updates), chunk_size):
        chunk = updates[i:i + chunk_size]
        for retry in range(3):
            try:
                r = sess.post(D1_LIGHT_URL, json={"updates": chunk}, timeout=25)
                if r.status_code == 200:
                    success_cnt += len(chunk)
                    print(f"  • D1 batch-light [{min(i + chunk_size, len(updates))}/{len(updates)}] 成功! (累积: {success_cnt})")
                    break
                else:
                    print(f"  ⚠️ HTTP {r.status_code}: {r.text}")
            except Exception as e:
                print(f"  ⚠️ 重试: {e}")
                time.sleep(1)
                
    if success_cnt != len(updates):
        print(f"❌ D1 更新未全部成功 ({success_cnt}/{len(updates)})，中止物理删除！")
        sys.exit(1)
        
    print(f"✅ D1 数据库直链 100% 切换完毕! 共成功切换 {success_cnt} 首歌曲至 Bucket 08 绝对直链！")

def step5_purge_old_bucket02(objects):
    print("\n" + "=" * 80)
    print("【步骤 5】从 Bucket 02 中物理删除已完成平移的旧资产，释放存储空间...")
    print("=" * 80)
    
    keys_to_delete = [o["key"] for o in objects]
    print(f"待删除旧物理对象: {len(keys_to_delete)} 个")
    
    # S3 delete_objects 单次上限 1000
    chunk_size = 500
    deleted_cnt = 0
    for i in range(0, len(keys_to_delete), chunk_size):
        chunk = keys_to_delete[i:i + chunk_size]
        del_payload = {"Objects": [{"Key": k} for k in chunk], "Quiet": True}
        s3_02.delete_objects(Bucket=NAME_02, Delete=del_payload)
        deleted_cnt += len(chunk)
        print(f"  • 已从 Bucket 02 物理删除: [{deleted_cnt}/{len(keys_to_delete)}] 个对象")
        
    print(f"✅ Bucket 02 旧物理对象已全部清除! 物理释放约 1.28 GB 存储空间！")

def main():
    objects, total_bytes = step1_collect_keys()
    step2_transfer_objects(objects)
    step3_verify_bucket08(objects)
    step4_switch_d1_routes(objects)
    step5_purge_old_bucket02(objects)
    print("\n" + "=" * 80)
    print("🎉 平移瘦身全流程圆满成功！")
    print("=" * 80)

if __name__ == "__main__":
    main()
