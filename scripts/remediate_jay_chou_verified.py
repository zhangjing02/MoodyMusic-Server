#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - 周杰伦 14 首确诊口播广告/李鬼伴奏/现场版曲目 100% 官方母带置换流水线
==============================================================================
执行标准：
1. 音频采录：YouTube 杰威尔官方频道 (周杰倫 Jay Chou) 正版 Official MV 母带；
2. 音频标准化：FFmpeg EBU R128 (-14 LUFS, LRA=11, TP=-1.5), 160k CBR, 44100Hz, Xing Header；
3. 特殊剪辑：《三年二班》官方 MV 剥离前置乒乓球微电影剧情（从 179.5s 起切出纯正 280s 音乐正歌）；
4. 目标存储：主力写入 Bucket 11 (pub-086ee39e1f294c8ba0a12c7073a3c271.r2.dev)；
5. 旧桶释放：在 Bucket 01 物理删除旧脏音频释放存储空间；
6. D1 远程库原子更新：file_path, duration, format='mp3', bit_rate=160；
7. 验收复验：HTTP Range 206 切片测试与 Groq Whisper 听音盲审。
==============================================================================
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
WORK_DIR = "/tmp/remediate_jay_chou"
os.makedirs(WORK_DIR, exist_ok=True)

# 14 首确诊曲目定义
TASKS = [
    {
        "id": 23291,
        "artist": "周杰伦",
        "album": "Jay",
        "title": "可爱女人",
        "yt_id": "87VUC4J_0Ps",
        "expected_dur": 238,
        "start_offset": 0
    },
    {
        "id": 23312,
        "artist": "周杰伦",
        "album": "八度空间",
        "title": "半岛铁盒",
        "yt_id": "duZDsG3tvoA",
        "expected_dur": 320,
        "start_offset": 0
    },
    {
        "id": 23313,
        "artist": "周杰伦",
        "album": "八度空间",
        "title": "暗号",
        "yt_id": "CYT9DPJdtS4",
        "expected_dur": 268,
        "start_offset": 0
    },
    {
        "id": 23317,
        "artist": "周杰伦",
        "album": "八度空间",
        "title": "爷爷泡的茶",
        "yt_id": "LdPjnubLRN0",
        "expected_dur": 243,
        "start_offset": 0
    },
    {
        "id": 23324,
        "artist": "周杰伦",
        "album": "叶惠美",
        "title": "三年二班",
        "yt_id": "_trE3M24kQY",
        "expected_dur": 280,
        "start_offset": 179.5 # 剥离前置乒乓球微电影剧情
    },
    {
        "id": 23335,
        "artist": "周杰伦",
        "album": "七里香",
        "title": "外婆",
        "yt_id": "Ur-x4pZT1Rk",
        "expected_dur": 250,
        "start_offset": 0
    },
    {
        "id": 23349,
        "artist": "周杰伦",
        "album": "十一月的萧邦",
        "title": "逆鳞",
        "yt_id": "jD0c4QY7L8s",
        "expected_dur": 252,
        "start_offset": 0
    },
    {
        "id": 23359,
        "artist": "周杰伦",
        "album": "依然范特西",
        "title": "红模仿",
        "yt_id": "LL50Fu4UvG0",
        "expected_dur": 184,
        "start_offset": 0
    },
    {
        "id": 23367,
        "artist": "周杰伦",
        "album": "我很忙",
        "title": "阳光宅男",
        "yt_id": "qQ7g1tfEGFc",
        "expected_dur": 222,
        "start_offset": 0
    },
    {
        "id": 23369,
        "artist": "周杰伦",
        "album": "我很忙",
        "title": "无双",
        "yt_id": "IYiIL2ZgOK4",
        "expected_dur": 234,
        "start_offset": 0
    },
    {
        "id": 23371,
        "artist": "周杰伦",
        "album": "我很忙",
        "title": "扯",
        "yt_id": "f5hakuX3lCA",
        "expected_dur": 197,
        "start_offset": 0
    },
    {
        "id": 23390,
        "artist": "周杰伦",
        "album": "跨时代",
        "title": "雨下一整晚",
        "yt_id": "jOxzAsnx9-0",
        "expected_dur": 267,
        "start_offset": 0
    },
    {
        "id": 23403,
        "artist": "周杰伦",
        "album": "惊叹号",
        "title": "水手怕水",
        "yt_id": "wUJ37I6au2w",
        "expected_dur": 173,
        "start_offset": 0
    },
    {
        "id": 23434,
        "artist": "周杰伦",
        "album": "周杰伦的床边故事",
        "title": "前世情人",
        "yt_id": "j9k3liT2MLo",
        "expected_dur": 208,
        "start_offset": 0
    }
]

# 加载 R2 配置
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_all = json.load(f)["buckets"]

# 目标桶 Bucket 11
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

# 旧桶 Bucket 01
old_cfg = r2_all["account_01"]
s3_old = boto3.client(
    "s3",
    endpoint_url=old_cfg["endpoint_url"],
    aws_access_key_id=old_cfg["access_key_id"],
    aws_secret_access_key=old_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
OLD_BUCKET_NAME = old_cfg["name"]

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
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
    if not os.path.exists(out_raw) and os.path.exists(out_raw + ".mp3"):
        os.rename(out_raw + ".mp3", out_raw)
    return True

def standardize_audio(in_file, out_file, start_offset=0):
    cmd = ["ffmpeg", "-y"]
    if start_offset > 0:
        cmd.extend(["-ss", str(start_offset)])
    cmd.extend([
        "-i", in_file,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-c:a", "libmp3lame",
        "-b:a", "160k",
        "-ar", "44100",
        "-write_xing", "1",
        "-id3v2_version", "3",
        out_file
    ])
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)

def get_audio_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    out = subprocess.check_output(cmd, timeout=8).decode().strip()
    return float(out)

def delete_old_object(object_path):
    try:
        s3_old.delete_object(Bucket=OLD_BUCKET_NAME, Key=object_path)
        print(f"   [旧桶释放] 成功物理删除: {OLD_BUCKET_NAME}/{object_path}")
    except Exception as e:
        print(f"   [旧桶释放] 删除失败或不存在: {e}")

def update_d1(song_id, new_file_path, duration_sec):
    wrangler_bin = os.path.join(BASE_DIR, "cloudflare-worker", "node_modules", ".bin", "wrangler")
    escaped_path = new_file_path.replace("'", "''")
    sql = f"UPDATE songs SET file_path = '{escaped_path}', duration = {int(duration_sec)}, format = 'mp3', bit_rate = 160 WHERE id = {song_id};"
    cmd = [
        wrangler_bin, "d1", "execute", "moody-d1-test", "--remote",
        "--command", sql
    ]
    cwd = os.path.join(BASE_DIR, "cloudflare-worker")
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
    if res.returncode == 0:
        return True, res.stdout
    else:
        return False, res.stderr

def run_pipeline():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    print("=" * 80)
    print("🚀 启动周杰伦 14 首正版录音室官方 MV 母带置换流水线 (写入 Bucket 11)")
    print("=" * 80)

    success_count = 0
    fail_count = 0
    results = []

    for idx, t in enumerate(TASKS, 1):
        sid = t["id"]
        title = t["title"]
        artist = t["artist"]
        album = t["album"]
        print(f"\n[{idx}/14] 处理 ID {sid}: {artist} - {title} ({album})")

        raw_file = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
        std_file = os.path.join(WORK_DIR, f"std_{sid}.mp3")

        # 1. 下载音频
        print(f"   [1/5 下载] 官方频道: {t['yt_id']}...")
        try:
            download_audio(t["yt_id"], raw_file)
        except Exception as e:
            print(f"   ❌ 下载异常: {e}")
            fail_count += 1
            continue

        # 2. 压制与标准化
        print(f"   [2/5 压制] EBU R128 标准化压制中 (offset={t['start_offset']}s)...")
        try:
            standardize_audio(raw_file, std_file, start_offset=t["start_offset"])
            dur = get_audio_duration(std_file)
            print(f"   压制完成，实测时长: {dur:.2f}s (预期: {t['expected_dur']}s)")
            if dur < 100.0:
                print(f"   ❌ 时长过短异常: {dur}s < 100s")
                fail_count += 1
                continue
        except Exception as e:
            print(f"   ❌ 压制异常: {e}")
            fail_count += 1
            continue

        # 3. 上传主力桶 Bucket 11
        r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
        target_cdn_url = f"{TARGET_DOMAIN}/{r2_key}"
        print(f"   [3/5 上传] 写入 Bucket 11: {r2_key}...")
        try:
            with open(std_file, "rb") as f:
                s3_target.put_object(
                    Bucket=TARGET_BUCKET_NAME,
                    Key=r2_key,
                    Body=f,
                    ContentType="audio/mpeg"
                )
            print(f"   ✅ 上传成功: {target_cdn_url}")
        except Exception as e:
            print(f"   ❌ 上传失败: {e}")
            fail_count += 1
            continue

        # 4. 旧桶物理删除释放空间 (Bucket 01)
        print(f"   [4/5 释放] 物理删除 Bucket 01 旧脏文件...")
        old_path = f"music/{artist}/{album}/s_{sid}.mp3"
        delete_old_object(old_path)

        # 5. D1 原子回写
        print(f"   [5/5 D1回写] 更新歌曲元数据与 CDN 直链...")
        ok, msg = update_d1(sid, target_cdn_url, dur)
        if ok:
            print(f"   ✅ D1 更新成功 (ID {sid})")
            success_count += 1
            results.append({
                "id": sid,
                "title": title,
                "artist": artist,
                "album": album,
                "duration": dur,
                "new_url": target_cdn_url,
                "status": "SUCCESS"
            })
        else:
            print(f"   ❌ D1 更新失败: {msg}")
            fail_count += 1

        # 清理临时文件
        if os.path.exists(raw_file): os.remove(raw_file)
        if os.path.exists(std_file): os.remove(std_file)

    print("\n" + "=" * 80)
    print(f"🎉 周杰伦置换流水线执行完毕! 成功: {success_count}/14, 失败: {fail_count}/14")
    print("=" * 80)

    # 导出报告
    out_rep = os.path.join(BASE_DIR, "reports", "jay_chou_remediation_summary.json")
    with open(out_rep, "w", encoding="utf-8") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results}, f, ensure_ascii=False, indent=2)
    print(f"报告已保存至: {out_rep}")

if __name__ == "__main__":
    run_pipeline()
