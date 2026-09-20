#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - 曾轶可《Anti ! Yico》剩余曲目收官母带重制与覆盖
涵盖：
- 28832 《同类》 (YouTube 官方录音室真唱母带覆盖 Zither Harp)
- 28835 《三的颜色》 (网易云 862098067)
- 28836 《黑色的路》 (网易云 862102068)
- 28837 《守望星》 (网易云 862100068)
- 28838 《I Need Love》 (网易云 862100069)
- 28839 《爱是一切》 (网易云 862102069)
- 28840 《午夜旅馆》 (网易云 862099061)
- 28841 《不如我们重新来过》 (网易云 862099062)
==============================================================================
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import requests
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
TMP_DIR = "/tmp/moody_recov_c"
os.makedirs(TMP_DIR, exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]["account_07"]

s3_client = boto3.client(
    's3',
    endpoint_url=r2_cfg['endpoint_url'],
    aws_access_key_id=r2_cfg['access_key_id'],
    aws_secret_access_key=r2_cfg['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4')
)
BUCKET_NAME = r2_cfg['name']
PUBLIC_DOMAIN = r2_cfg.get('public_url', r2_cfg.get('public_domain', '')).rstrip('/')

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_PROXIES = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

RECOV_TASKS = [
    {"album": "Anti ! Yico", "id": 28832, "title": "同类", "source": "youtube", "ytid": "lQWmeAEV_iM", "nid": 862102067},
    {"album": "Anti ! Yico", "id": 28835, "title": "三的颜色", "source": "netease", "nid": 862098067},
    {"album": "Anti ! Yico", "id": 28836, "title": "黑色的路", "source": "netease", "nid": 862102068},
    {"album": "Anti ! Yico", "id": 28837, "title": "守望星", "source": "netease", "nid": 862100068},
    {"album": "Anti ! Yico", "id": 28838, "title": "I Need Love", "source": "netease", "nid": 862100069},
    {"album": "Anti ! Yico", "id": 28839, "title": "爱是一切", "source": "netease", "nid": 862102069},
    {"album": "Anti ! Yico", "id": 28840, "title": "午夜旅馆", "source": "netease", "nid": 862099061},
    {"album": "Anti ! Yico", "id": 28841, "title": "不如我们重新来过", "source": "netease", "nid": 862099062},
]

def download_audio(nid: int, target_path: str) -> bool:
    url = f"http://music.163.com/song/media/outer/url?id={nid}.mp3"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            if len(content) < 500 * 1024:
                return False
            with open(target_path, "wb") as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"      ❌ 下载失败: {e}", flush=True)
        return False

def download_youtube_audio(ytid: str, target_path: str) -> bool:
    url = f"https://www.youtube.com/watch?v={ytid}"
    cmd = [
        "yt-dlp",
        "--proxy", "http://127.0.0.1:7897",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", target_path,
        url
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return os.path.exists(target_path) and os.path.getsize(target_path) > 500 * 1024
    except Exception as e:
        print(f"      ❌ YouTube 下载失败: {e}", flush=True)
        return False

def download_lrc(nid: int, target_path: str) -> bool:
    url = f"http://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            lrc_text = data.get('lrc', {}).get('lyric', '')
            if lrc_text and len(lrc_text.strip()) > 20:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(lrc_text)
                return True
    except Exception:
        pass
    return False

def standardize_audio(input_path: str, output_path: str) -> dict:
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k",
        "-write_xing", "1",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
        "-of", "default=noprint_wrappers=1:nokey=1", output_path
    ]
    res = subprocess.check_output(probe_cmd).decode('utf-8').strip().split('\n')
    return {"duration": float(res[0]), "size": int(res[1])}

def verify_with_whisper(audio_path: str) -> tuple:
    clip_path = audio_path.replace(".mp3", "_clip.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "00:00:25", "-t", "30", "-i", audio_path, "-ac", "1", "-ar", "16000", clip_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    with open(clip_path, "rb") as f:
        files = {
            'file': (os.path.basename(clip_path), f, 'audio/mpeg'),
            'model': (None, 'whisper-large-v3')
        }
        resp = requests.post(
            'https://api.groq.com/openai/v1/audio/transcriptions',
            headers=headers, files=files, proxies=GROQ_PROXIES, timeout=30
        )
    if os.path.exists(clip_path):
        os.remove(clip_path)
    text = resp.json().get('text', '').strip()
    return (len(text) > 5 and 'zither harp' not in text.lower()), text

def main():
    print("=" * 80, flush=True)
    print("🚀 曾轶可《Anti ! Yico》剩余 8 首收官重制与直链点亮", flush=True)
    print("=" * 80, flush=True)
    
    success_items = []
    
    for idx, t in enumerate(RECOV_TASKS, 1):
        sid = t["id"]
        title = t["title"]
        album = t["album"]
        source = t["source"]
        
        print(f"\n[{idx:02d}/08] 🛠️ 重制《{album}》 - 《{title}》 (Song ID: {sid}, 来源: {source})", flush=True)
        
        raw_file = os.path.join(TMP_DIR, f"raw_{sid}.mp3")
        norm_file = os.path.join(TMP_DIR, f"s_{sid}.mp3")
        lrc_file = os.path.join(TMP_DIR, f"s_{sid}.lrc")
        
        # 1. 获取母带音频
        print(f"     • [1/5] 下载官方录音室母带音轨 ({source})...", flush=True)
        if source == "youtube":
            ok = download_youtube_audio(t["ytid"], raw_file)
        else:
            ok = download_audio(t["nid"], raw_file)
            
        if not ok or not os.path.exists(raw_file):
            print(f"     ❌ 获取母带失败，跳过", flush=True)
            continue
            
        # 2. 标准化压制
        print("     • [2/5] EBU R128 标准化 (-14 LUFS) 与 160k CBR Xing MP3 压制...", flush=True)
        try:
            meta = standardize_audio(raw_file, norm_file)
            print(f"       ✅ 压制成功: 时长 {meta['duration']:.1f}s, 大小 {meta['size']/(1024*1024):.2f} MB", flush=True)
        except Exception as e:
            print(f"     ❌ 压制异常: {e}", flush=True)
            continue
            
        # 3. Whisper 质检
        print("     • [3/5] Groq Whisper 大模型声乐与唱词核验 (25s-55s 黄金切片)...", flush=True)
        try:
            ok_whisper, text = verify_with_whisper(norm_file)
            clean_text = text.replace('\n', ' ')[:60]
            if ok_whisper:
                print(f"       🟢 质检合格! 听到: \"{clean_text}...\"", flush=True)
            else:
                print(f"       ⚠️ 质检存疑: 听到: \"{clean_text}...\"", flush=True)
        except Exception as e:
            print(f"       ⚠️ 质检网络异常: {e}", flush=True)
            
        # 4. LRC 歌词
        print("     • [4/5] 抓取毫秒级同步歌词...", flush=True)
        has_lrc = False
        if "nid" in t:
            has_lrc = download_lrc(t["nid"], lrc_file)
        if has_lrc:
            print("       ✅ 歌词获取成功", flush=True)
        else:
            print("       ℹ️ 保持既有歌词", flush=True)
            
        # 5. 上传至 R2 Bucket 07
        print("     • [5/5] 上传至 Cloudflare R2 Bucket 07 物理覆盖...", flush=True)
        r2_audio_key = f"music/曾轶可/{album}/s_{sid}.mp3"
        r2_lrc_key = f"lyrics/曾轶可/{album}/s_{sid}.lrc"
        
        try:
            s3_client.upload_file(norm_file, BUCKET_NAME, r2_audio_key, ExtraArgs={'ContentType': 'audio/mpeg'})
            audio_url = f"{PUBLIC_DOMAIN}/{r2_audio_key}"
            lrc_url = f"{PUBLIC_DOMAIN}/{r2_lrc_key}"
            if has_lrc and os.path.exists(lrc_file):
                s3_client.upload_file(lrc_file, BUCKET_NAME, r2_lrc_key, ExtraArgs={'ContentType': 'text/plain; charset=utf-8'})
                
            print(f"       🚀 云端物理覆盖成功 -> {audio_url}", flush=True)
            success_items.append({
                "id": sid,
                "file_path": audio_url,
                "lrc_path": lrc_url
            })
        except Exception as e:
            print(f"       ❌ R2 上传失败: {e}", flush=True)
            
    # 批量调用 D1 点亮
    if success_items:
        print("\n" + "=" * 80, flush=True)
        print(f"⚡ [D1] 向生产网关提交 batch-light 点亮数据库 (共 {len(success_items)} 首)...", flush=True)
        payload = {"updates": success_items}
        headers = {"Content-Type": "application/json"}
        resp = requests.post(D1_LIGHT_URL, json=payload, headers=headers, timeout=20)
        print(f"D1 响应: {resp.status_code} - {resp.text}", flush=True)
        
    print("=" * 80, flush=True)
    print(f"🏁 收官重制完成! 成功: {len(success_items)} / {len(RECOV_TASKS)} 首", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
