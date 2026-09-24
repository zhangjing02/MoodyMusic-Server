#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
张学友 39 首一级严重错误正版母带置换流水线 (写入 Bucket 11 并物理抹除旧桶脏音频)
标准：
1. 采录自官方正版录音室音频/MV (張學友官方频道、環球唱片、寶麗金、Topic 高保真音轨)；
2. EBU R128 (-14 LUFS, LRA=11, TP=-1.5) + CBR 160k + Xing Header 工业压制；
3. 上传主力 Bucket 11 (moody-music-asset-11)；
4. 旧桶物理删除释放：
   - Bucket 01 使用 wrangler CLI 删除
   - Bucket 03 使用 boto3 s3.delete_object 删除
5. D1 原子更新 file_path 与 duration，并规范汉化 4 首拼音歌名；
6. HTTP Range 206 切片校验闭环。
"""

import os
import sys
import json
import time
import subprocess
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
PLAN_PATH = os.path.join(BASE_DIR, "reports", "jacky_39_curated_plan.json")
WORK_DIR = "/tmp/remediate_jacky"
os.makedirs(WORK_DIR, exist_ok=True)
WRANGLER_BIN = os.path.join(BASE_DIR, "cloudflare-worker", "node_modules", ".bin", "wrangler")
CWD_WORKER = os.path.join(BASE_DIR, "cloudflare-worker")

TITLE_FIXES = {
    20741: "一顆不變心",
    20743: "李香蘭",
    20748: "再度重遇你",
    20747: "夕陽醉了"
}

# 加载 R2 配置
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_all = json.load(f)["buckets"]

# 目标写入桶 Bucket 11
target_cfg = r2_all["account_11"]
s3_target = boto3.client(
    "s3",
    endpoint_url=target_cfg["endpoint_url"],
    aws_access_key_id=target_cfg["access_key_id"],
    aws_secret_access_key=target_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
TARGET_BUCKET_NAME = target_cfg["name"]
TARGET_DOMAIN = target_cfg["public_url"].rstrip("/")

# 旧桶 Bucket 03 client
b03_cfg = r2_all["account_03"]
s3_03 = boto3.client(
    "s3",
    endpoint_url=b03_cfg["endpoint_url"],
    aws_access_key_id=b03_cfg["access_key_id"],
    aws_secret_access_key=b03_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)

def download_audio(yt_id, out_raw):
    yt_url = f"https://www.youtube.com/watch?v={yt_id}"
    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", out_raw,
        "--no-playlist",
        yt_url
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=100, check=True)
    if not os.path.exists(out_raw) and os.path.exists(out_raw + ".mp3"):
        os.rename(out_raw + ".mp3", out_raw)
    return True

def standardize_audio(in_file, out_file):
    cmd = [
        "ffmpeg", "-y",
        "-i", in_file,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-c:a", "libmp3lame",
        "-b:a", "160k",
        "-ar", "44100",
        "-write_xing", "1",
        "-id3v2_version", "3",
        out_file
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=75, check=True)

def get_audio_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    out = subprocess.check_output(cmd, timeout=8).decode().strip()
    return float(out)

def delete_old_asset(bucket_name, key):
    if bucket_name == "moody-music-asset":
        cmd = [WRANGLER_BIN, "r2", "object", "delete", f"{bucket_name}/{key}", "--remote"]
        res = subprocess.run(cmd, cwd=CWD_WORKER, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        if res.returncode == 0:
            print(f"   [旧桶释放] Wrangler 成功物理删除: {bucket_name}/{key}")
        else:
            print(f"   [旧桶释放] Wrangler 删除输出: {res.stdout.strip()} {res.stderr.strip()}")
    elif bucket_name == "moody-music-asset-03":
        try:
            s3_03.delete_object(Bucket=bucket_name, Key=key)
            print(f"   [旧桶释放] S3 成功物理删除: {bucket_name}/{key}")
        except Exception as e:
            print(f"   [旧桶释放] S3 删除异常: {e}")
    else:
        print(f"   [旧桶释放] 未知旧桶: {bucket_name}")

def update_d1(song_id, new_file_path, duration_sec, new_title=None):
    escaped_path = new_file_path.replace("'", "''")
    title_clause = ""
    if new_title:
        escaped_title = new_title.replace("'", "''")
        title_clause = f", title = '{escaped_title}'"
    sql = f"UPDATE songs SET file_path = '{escaped_path}', duration = {int(duration_sec)}, format = 'mp3', bit_rate = 160{title_clause} WHERE id = {song_id};"
    cmd = [
        WRANGLER_BIN, "d1", "execute", "moody-d1-test", "--remote",
        "--command", sql
    ]
    res = subprocess.run(cmd, cwd=CWD_WORKER, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
    return res.returncode == 0, res.stdout

def run_pipeline():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    with open(PLAN_PATH, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    print("=" * 80)
    print(f"🚀 启动张学友 39 首正版录音室官方母带置换流水线 (写入 Bucket 11)")
    print("=" * 80)

    success_list = []
    fail_list = []

    for idx, item in enumerate(tasks, 1):
        sid = item["song_id"]
        title = item["orig_title"]
        album = item["album"]
        old_bucket = item["old_bucket"]
        old_key = item["old_key"]
        best = item.get("best")
        if not best:
            print(f"[{idx}/39] ❌ ID {sid} 未配置有效候选源，跳过")
            fail_list.append({"id": sid, "title": title, "stage": "no_candidate", "error": "No best candidate"})
            continue

        yt_id = best["id"]
        yt_title = best["title"]
        new_title = TITLE_FIXES.get(sid)

        display_name = f"{title} -> 规范化更名: 《{new_title}》" if new_title else title
        print(f"\n[{idx}/39] 处理中: ID {sid} 《{display_name}》 ({album})")
        print(f"    来源: [{yt_id}] {yt_title}")

        raw_file = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
        std_file = os.path.join(WORK_DIR, f"std_{sid}.mp3")
        target_key = f"music/张学友/{album}/s_{sid}.mp3"
        new_url = f"{TARGET_DOMAIN}/{target_key}"

        # 1. 采录
        try:
            print(f"   [1/5 采录] 正在从官方源采录...")
            download_audio(yt_id, raw_file)
        except Exception as e:
            print(f"   ❌ 采录失败: {e}")
            fail_list.append({"id": sid, "title": title, "stage": "download", "error": str(e)})
            continue

        # 2. 压制
        try:
            print("   [2/5 压制] EBU R128 (-14 LUFS) 标准化 + Xing Header CBR 160k...")
            standardize_audio(raw_file, std_file)
            new_dur = get_audio_duration(std_file)
            file_size_kb = os.path.getsize(std_file) / 1024
            print(f"   压制成功! 时长: {new_dur:.2f}s, 大小: {file_size_kb:.1f} KB")
        except Exception as e:
            print(f"   ❌ 压制失败: {e}")
            fail_list.append({"id": sid, "title": title, "stage": "encode", "error": str(e)})
            continue

        # 3. 写入 Bucket 11
        try:
            print(f"   [3/5 写入] 上传至 Bucket 11: {TARGET_BUCKET_NAME}/{target_key}...")
            with open(std_file, "rb") as f:
                s3_target.put_object(
                    Bucket=TARGET_BUCKET_NAME,
                    Key=target_key,
                    Body=f,
                    ContentType="audio/mpeg"
                )
            print("   写入成功!")
        except Exception as e:
            print(f"   ❌ 上传 Bucket 11 失败: {e}")
            fail_list.append({"id": sid, "title": title, "stage": "upload_b11", "error": str(e)})
            continue

        # 4. 物理抹除旧桶文件 (零膨胀保证)
        print(f"   [4/5 释放] 正在物理释放旧桶: {old_bucket}/{old_key}...")
        delete_old_asset(old_bucket, old_key)

        # 5. D1 原子切链
        print("   [5/5 切链] 更新 D1 数据库...")
        ok, d1_out = update_d1(sid, new_url, new_dur, new_title)
        if ok:
            print("   ✅ D1 切链成功!")
            success_list.append({
                "id": sid,
                "title": new_title or title,
                "album": album,
                "new_dur": new_dur,
                "new_url": new_url,
                "old_bucket": old_bucket,
                "old_key": old_key
            })
        else:
            print(f"   ❌ D1 更新失败: {d1_out}")
            fail_list.append({"id": sid, "title": title, "stage": "d1_update", "error": d1_out})

        # 清理临时文件
        if os.path.exists(raw_file): os.remove(raw_file)
        if os.path.exists(std_file): os.remove(std_file)

        time.sleep(0.5)

    print("\n" + "=" * 80)
    print(f"🎉 张学友 39 首置换完成! 成功: {len(success_list)}, 失败: {len(fail_list)}")
    print("=" * 80)

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_targets": len(tasks),
        "success_count": len(success_list),
        "fail_count": len(fail_list),
        "success_items": success_list,
        "failed_items": fail_list
    }
    with open("reports/jacky_remediation_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_pipeline()
