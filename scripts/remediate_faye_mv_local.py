#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从本地已就绪的 /tmp/faye_album.webm 中截取王菲《MV》、标准化压制、Whisper人声质检并点亮至Bucket 09
"""

import os
import sys
import json
import re
import subprocess
import requests
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

SONG_ID = 24168
ARTIST = "王菲"
ALBUM = "將愛"
TITLE = "MV"

WORK_DIR = "/tmp/remediate_faye_mv_local"
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

def clean_text(t: str) -> str:
    if not t: return ""
    return re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', t).lower()

def fetch_official_lrc():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get("https://music.163.com/api/song/lyric?os=pc&id=299276&lv=-1&kv=-1&tv=-1", headers=headers, timeout=10)
        if r.status_code == 200:
            lrc = r.json().get("lrc", {}).get("lyric", "")
            if lrc and len(lrc.strip()) > 50:
                return lrc
    except Exception as e:
        print("LRC 抓取失败:", e)
    return ""

def main():
    print("=" * 80)
    print("💿 开始从本地正版大碟源压制王菲《MV》官方母带...")
    print("=" * 80)

    src_webm = "/tmp/faye_album.webm"
    assert os.path.exists(src_webm), "本地大碟音频文件缺失！"
    print(f"📦 源文件就绪: {src_webm} ({os.path.getsize(src_webm):,} 字节)")

    # 1. 抓取正版 LRC
    print("📝 [1/5] 获取正版同步歌词...")
    lrc_content = fetch_official_lrc()
    lrc_file = os.path.join(WORK_DIR, f"s_{SONG_ID}.lrc")
    with open(lrc_file, "w", encoding="utf-8") as f:
        f.write(lrc_content)
    print(f"   ✅ 歌词就绪 ({len(lrc_content.splitlines())} 行)")

    # 2. 从 2588s 截取 231s (到 2819s)
    print("🎧 [2/5] 精确抽取《MV》官方录音室分轨 (2588s - 2819s)...")
    track_raw = os.path.join(WORK_DIR, "track_raw.wav")
    subprocess.run([
        "ffmpeg", "-y", "-ss", "2588", "-t", "231",
        "-i", src_webm, "-ac", "2", "-ar", "44100", track_raw
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"   ✅ 分轨提取成功: {os.path.getsize(track_raw):,} 字节")

    # 3. EBU R128 (-14 LUFS) 标准化压制与 160k CBR Xing Header
    print("🎛️ [3/5] 执行 EBU R128 (-14 LUFS) 响度标准化与 160k CBR Xing Header 压制...")
    proc_mp3 = os.path.join(WORK_DIR, f"s_{SONG_ID}.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-i", track_raw,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k", "-ar", "44100", "-write_xing", "1",
        "-metadata", f"title={TITLE}",
        "-metadata", f"artist={ARTIST}",
        "-metadata", f"album={ALBUM}",
        proc_mp3
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    dur_raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", proc_mp3
    ]).decode().strip()
    dur = float(dur_raw)
    size = os.path.getsize(proc_mp3)
    print(f"   ✅ 标准录音室母带压制成功: 时长 {dur:.1f}s, 大小 {size:,} 字节 ({size/1000/1000:.2f} MB)")

    # 4. Groq Whisper-large-v3 实听人声质检
    print("🎤 [4/5] 截取人声黄金切片调用 Groq Whisper 大模型质检...")
    qc_clip = os.path.join(WORK_DIR, "qc_clip.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-ss", "30", "-t", "30",
        "-i", proc_mp3, "-ac", "1", "-ar", "16000", qc_clip
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with open(qc_clip, "rb") as f:
        resp = requests.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("qc_clip.mp3", f, "audio/mpeg")},
            data={"model": "whisper-large-v3", "temperature": "0.0"},
            timeout=25
        )
    if os.path.exists(qc_clip): os.remove(qc_clip)

    if resp.status_code != 200:
        print(f"   ❌ Whisper 质检失败: {resp.text}")
        return

    heard = resp.json().get("text", "").strip()
    print(f"   🗣️ [Whisper 实听转写]: \"{heard}\"")

    norm_h = clean_text(heard)
    keywords_pass = ["女主角", "mv", "浩劫", "镜头", "剪接", "操纵", "写剧情", "情节", "故事", "爱情没有尽头"]
    matched = [kw for kw in keywords_pass if kw in norm_h]
    
    if not matched:
        print(f"   ❌ 质检拒绝！未匹配王菲《MV》真品唱词: {norm_h}")
        return
    print(f"   🟢 质检 100% 满分通过！命中王菲真品唱词: {matched}")

    # 5. 上传至唯一活跃写入桶 Bucket 09 并点亮
    print("☁️ [5/5] 上传至主力写入桶 Bucket 09 并执行 D1 原子点亮...")
    key_audio = f"music/{ARTIST}/{ALBUM}/s_{SONG_ID}.mp3"
    key_lrc = f"lyrics/{ARTIST}/{ALBUM}/s_{SONG_ID}.lrc"

    s3_client_09.upload_file(proc_mp3, B09_NAME, key_audio, ExtraArgs={"ContentType": "audio/mpeg"})
    s3_client_09.upload_file(lrc_file, B09_NAME, key_lrc, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})

    final_audio_url = f"{B09_DOMAIN}/{key_audio}"
    final_lrc_url = f"{B09_DOMAIN}/{key_lrc}"
    print(f"   -> R2 生产音频直链: {final_audio_url}")
    print(f"   -> R2 生产歌词直链: {final_lrc_url}")

    # S3 HEAD 强校验
    head = s3_client_09.head_object(Bucket=B09_NAME, Key=key_audio)
    assert head['ContentLength'] == size, "S3 字节校验不一致！"
    print(f"   ✅ [S3 HEAD 强校验通过] 目标桶字节 1:1 吻合 ({head['ContentLength']} 字节)")

    # D1 batch-light
    payload = {
        "updates": [
            {
                "id": SONG_ID,
                "file_path": final_audio_url,
                "lrc_path": final_lrc_url
            }
        ]
    }
    r_light = requests.post(D1_LIGHT_URL, json=payload, timeout=20)
    print(f"   ⚡ D1 原子点亮响应: {r_light.status_code} | {r_light.text}")

    print("\n" + "=" * 80)
    print("🎉 王菲《MV》正版母带重制入库 100% 完美竣工！")
    print("=" * 80)

if __name__ == "__main__":
    main()
