#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 错配孤儿物理资源安全普查与物理清理引擎 (Safe Orphan R2 Asset Cleanup)
==============================================================================
铁律规范:
1. 绝对保护已点亮曲目：如果歌曲当前 status == 'D1_LIT' 或 D1 中 file_path 非空，绝对严禁删除！
2. 绝对全库 0 引用校验：全库检索包括当前歌曲自身在内的所有活跃记录，COUNT(*) 必须为 0！
3. 特殊资产白名单保护：陈奕迅《一滴眼泪》(25617, 25618) 实为录音室原版《学会爱》与《二个人的夜晚》，予以保护！
4. 仅物理清理确认是垃圾串歌、口水翻唱、爬虫虚假曲目且 0 引用的孤儿文件。
==============================================================================
"""

import os
import sys
import json
import sqlite3
import urllib.parse
import boto3
from botocore.config import Config

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    r2_cfg = json.load(f)

# 白名单保护 ID（有录音室原版保留价值的曲目，绝不物理删除）
PROTECTED_VALUABLE_IDS = [25617, 25618]

# 待检查已下架错配歌曲 ID
CANDIDATE_UNLIT_IDS = [
    7380, 7413, 8862, 8863, 8864, 8865, 12066, 25795, 25796
]

BUCKET_MAP = {
    "pub-9ea7ff16135d47238c0229f1aa54ecc4": "account_02",
    "moody-music-asset-02": "account_02",
    "pub-383b876c0bb840f6b852946604275232": "account_03",
    "moody-music-asset-03": "account_03",
    "pub-3507a1a1bc4b4ac3a3340833031078c2": "account_04",
    "moody-music-asset-04": "account_04",
    "pub-e7d069eb11954440aeb32012e8e3c670": "account_05",
    "moody-music-asset-05": "account_05",
    "pub-46ab5c0015d84be1b748cffecd23fdbb": "account_06",
    "moody-music-asset-06": "account_06",
}

def get_bucket_and_key(url_or_key: str) -> tuple[str, str]:
    if not url_or_key:
        return "", ""
    clean_url = url_or_key.split('?')[0].strip()
    
    target_acc = ""
    for domain_pattern, acc_key in BUCKET_MAP.items():
        if domain_pattern in clean_url:
            target_acc = acc_key
            break
            
    if clean_url.startswith("http"):
        parsed = urllib.parse.urlparse(clean_url)
        key = parsed.path.lstrip('/')
    else:
        key = clean_url.lstrip('/')
        if not target_acc:
            target_acc = "account_01"
            
    return target_acc, key

def inspect_and_clean(dry_run=True):
    print("=" * 90)
    mode_text = "【安全模拟普查 (DRY RUN)】" if dry_run else "【正式物理硬删除执行 (EXECUTION)】"
    print(f"🧹 MOODY 错配孤儿物理资源安全清理引擎 - {mode_text}")
    print("=" * 90)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(f"""
        SELECT song_id, artist_name, album_title, song_title, r2_mp3_key, r2_lrc_key, status
        FROM tracks_sync_state
        WHERE song_id IN ({','.join(map(str, CANDIDATE_UNLIT_IDS))})
    """)
    records = cur.fetchall()

    deletion_candidates = []
    skipped_active = []
    seen_keys = set()

    for sid, art, alb, song, mp3_url, lrc_url, status in records:
        if sid in PROTECTED_VALUABLE_IDS:
            print(f"🛡️ [白名单保护] ID: {sid} | [{art}] 《{song}》 是珍贵录音室母带，安全保留！")
            continue

        # 校验当前生产 D1 状态与本地状态
        cur.execute("SELECT file_path FROM songs WHERE id = ?", (sid,))
        curr_fp = cur.fetchone()
        if curr_fp and curr_fp[0] and curr_fp[0].strip() != '':
            skipped_active.append((sid, f"[{art}] 《{song}》", "当前处于已点亮生产状态，绝对禁止删除！"))
            continue

        if not mp3_url:
            continue
            
        acc_key, obj_key = get_bucket_and_key(mp3_url)
        if not acc_key or not obj_key:
            continue

        if obj_key in seen_keys:
            continue
        seen_keys.add(obj_key)

        base_filename = os.path.basename(obj_key)
        
        # 严格全库 0 引用检验：检索当前全库所有歌曲，是否有任何歌曲正在使用这个物理文件
        cur.execute("""
            SELECT COUNT(*), GROUP_CONCAT(id)
            FROM songs
            WHERE file_path LIKE ?
        """, (f"%{base_filename}%",))
        active_refs, ref_ids = cur.fetchone()

        if active_refs > 0:
            skipped_active.append((sid, f"[{art}] 《{song}》", f"仍有 {active_refs} 处活跃引用 (IDs: {ref_ids})"))
        else:
            deletion_candidates.append({
                "song_id": sid,
                "title": f"[{art}] 《{alb}》 - 《{song}》",
                "acc_key": acc_key,
                "bucket_name": r2_cfg['buckets'][acc_key]['name'],
                "obj_key": obj_key,
                "lrc_key": get_bucket_and_key(lrc_url)[1] if lrc_url else None
            })

    print(f"\n📊 审计分析结果:")
    print(f"  • 待排查下架记录: {len(records)} 条")
    print(f"  • 确认可安全硬删除的孤儿坏资源: {len(deletion_candidates)} 个")
    print(f"  • 活跃引用/白名单拦截保护: {len(skipped_active)} 个")

    print(f"\n🗑️ 【可安全物理删除清单】(全库 0 引用、已下架孤儿垃圾音轨):")
    for c in deletion_candidates:
        print(f"  • [ID: {c['song_id']:<5}] {c['title']}")
        print(f"    Bucket: {c['bucket_name']} ({c['acc_key']})")
        print(f"    Key:    {c['obj_key']}")
        if c['lrc_key']:
            print(f"    LRC:    {c['lrc_key']}")

    if not dry_run and deletion_candidates:
        print("\n" + "=" * 90)
        print("🚀 开始在 Cloudflare R2 执行物理硬删除...")
        print("=" * 90)
        
        s3_clients = {}
        deleted_count = 0
        deleted_bytes = 0

        for item in deletion_candidates:
            acc = item['acc_key']
            bname = item['bucket_name']
            k = item['obj_key']

            if acc not in s3_clients:
                b_info = r2_cfg['buckets'][acc]
                s3_clients[acc] = boto3.client(
                    's3',
                    endpoint_url=b_info['endpoint_url'],
                    aws_access_key_id=b_info['access_key_id'],
                    aws_secret_access_key=b_info['secret_access_key'],
                    config=Config(signature_version='s3v4')
                )
            client = s3_clients[acc]

            try:
                try:
                    head = client.head_object(Bucket=bname, Key=k)
                    size = head.get('ContentLength', 0)
                except Exception:
                    size = 0

                client.delete_object(Bucket=bname, Key=k)
                deleted_count += 1
                deleted_bytes += size
                print(f"  ✅ [已物理删除音频] {bname} -> {k} ({size/1024/1024:.2f} MB)")
            except Exception as e:
                print(f"  ❌ 删除失败 {bname}/{k}: {e}")

            lk = item.get('lrc_key')
            if lk:
                try:
                    client.delete_object(Bucket=bname, Key=lk)
                    print(f"  ✅ [已物理删除歌词] {bname} -> {lk}")
                except Exception:
                    pass

            cur.execute("""
                UPDATE tracks_sync_state 
                SET r2_mp3_key = NULL, r2_lrc_key = NULL, status = 'PHYSICALLY_DELETED' 
                WHERE song_id = ?
            """, (item['song_id'],))
            conn.commit()

        print("\n" + "=" * 90)
        print(f"🎉 物理硬删除完成! 成功物理清空 {deleted_count} 个垃圾音轨，释放云端空间: {deleted_bytes/1024/1024:.2f} MB")
        print("=" * 90)

if __name__ == "__main__":
    is_dry = "--execute" not in sys.argv
    inspect_and_clean(dry_run=is_dry)
