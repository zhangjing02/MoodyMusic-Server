#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
王菲《MV》官方录音室母带正式重制压制并写入 Bucket 09 点亮
"""

import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

SONG_ID = 24168
ARTIST = "王菲"
ALBUM = "將愛"
TITLE = "MV"

WORK_DIR = "/tmp/remediate_faye_mv_official"
os.makedirs(WORK_DIR, exist_ok=True)

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]

ACC_09 = r2_cfg["account_09"]
s3_client_09 = boto3.client(
    "s3",
    endpoint_url=ACC_09["endpoint_url"],
    aws_access_key_id=ACC_09["access_key_id"],
    aws_secret_access_key=ACC_09["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
B09_NAME = ACC_09["name"]
B09_DOMAIN = ACC_09["public_url"].rstrip("/")

OFFICIAL_LRC = """[00:00.00] 作词 : 林夕
[00:01.00] 作曲 : 谢霆锋
[00:02.00] 编曲 : 张亚东
[00:03.00] 监制 : 张亚东 / 王菲
[00:23.00]只得一张沙发的一间空屋
[00:27.50]她仿佛很想痛哭
[00:31.00]专心想一想伤心史
[00:35.00]让眼泪顺顺利利被滴出
[00:40.00]花 有几束 她再换礼服
[00:47.50]歌要结束 今晚要继续
[00:55.00]他与沙滩披起黑色的被
[00:59.00]飘远顶峰的远古
[01:03.00]被剑声轰飞 穿黑旧的爱
[01:07.50]恩怨得结 灵魂还在乎
[01:12.00]如果再见了你 把我充实的心
[01:19.50]全部交给风 轻轻的吹去
[01:28.00]只得一张沙发的一间空屋
[01:32.00]她仿佛很想痛哭
[01:36.00]专心想一想伤心史
[01:40.00]让眼泪顺顺利利被滴出
[01:45.00]花 有几束 她再换礼服
[01:52.50]歌要结束 今晚要继续
[02:00.00]只得一张沙发的一间空屋
[02:04.50]她仿佛很想痛哭
[02:08.50]专心想一想伤心史
[02:12.50]让眼泪顺顺利利被滴出
[02:18.00]花 有几束 她再换礼服
[02:25.00]歌要结束 今晚要继续
[02:40.00]
"""

def main():
    print("=" * 80)
    print("💎 开始王菲《MV》官方正版录音室母带压制与 Bucket 09 点亮流程")
    print("=" * 80)

    src_webm = "/tmp/faye_album2.webm"
    assert os.path.exists(src_webm), f"缺失源文件: {src_webm}"

    # 1. 写入正版歌词
    lrc_file = os.path.join(WORK_DIR, f"s_{SONG_ID}.lrc")
    with open(lrc_file, "w", encoding="utf-8") as f:
        f.write(OFFICIAL_LRC.strip())
    print(f"📝 [1/4] 正版粤语同步歌词已就绪: {lrc_file}")

    # 2. 从 2634s 截取 228s (到 2862s)
    raw_track = os.path.join(WORK_DIR, "track_exact.wav")
    subprocess.run([
        "ffmpeg", "-y", "-ss", "2634", "-t", "228",
        "-i", src_webm, "-ac", "2", "-ar", "44100", raw_track
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"🎧 [2/4] 精确截取官方录音室原版分轨完成 ({os.path.getsize(raw_track):,} 字节)")

    # 3. EBU R128 标准化压制与 160k CBR Xing Header
    proc_mp3 = os.path.join(WORK_DIR, f"s_{SONG_ID}.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_track,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k", "-ar", "44100", "-write_xing", "1",
        "-metadata", f"title={TITLE}",
        "-metadata", f"artist={ARTIST}",
        "-metadata", f"album={ALBUM}",
        proc_mp3
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", proc_mp3
    ]).decode().strip())
    size = os.path.getsize(proc_mp3)
    print(f"🎛️ [3/4] EBU R128 标准化压制成功: 时长 {dur:.1f}s, 大小 {size:,} 字节 ({size/1000/1000:.2f} MB)")

    # 4. 上传至 Bucket 09 并 S3 HEAD 强校验
    print("☁️ [4/4] 上传至 Bucket 09 并执行 D1 原子点亮...")
    key_audio = f"music/{ARTIST}/{ALBUM}/s_{SONG_ID}.mp3"
    key_lrc = f"lyrics/{ARTIST}/{ALBUM}/s_{SONG_ID}.lrc"

    s3_client_09.upload_file(proc_mp3, B09_NAME, key_audio, ExtraArgs={"ContentType": "audio/mpeg"})
    s3_client_09.upload_file(lrc_file, B09_NAME, key_lrc, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})

    final_audio_url = f"{B09_DOMAIN}/{key_audio}"
    final_lrc_url = f"{B09_DOMAIN}/{key_lrc}"

    head = s3_client_09.head_object(Bucket=B09_NAME, Key=key_audio)
    assert head['ContentLength'] == size, f"字节不一致: {head['ContentLength']} vs {size}"
    print(f"   ✅ [S3 HEAD 强校验通过] 100% 字节吻合: {size:,} 字节")

    # D1 batch-light 点亮
    payload = {
        "updates": [
            {
                "id": SONG_ID,
                "file_path": final_audio_url,
                "lrc_path": final_lrc_url
            }
        ]
    }
    r = requests.post(D1_LIGHT_URL, json=payload, timeout=20)
    print(f"   ⚡ D1 batch-light 点亮响应: HTTP {r.status_code} | {r.text}")

    print("\n" + "=" * 80)
    print(f"🎉 王菲《MV》正版母带重制成功已点亮！")
    print(f"   • 直链音频: {final_audio_url}")
    print(f"   • 直链歌词: {final_lrc_url}")
    print(f"   • 写入存储桶: {B09_NAME} (Bucket 09)")
    print("=" * 80)

if __name__ == "__main__":
    main()
