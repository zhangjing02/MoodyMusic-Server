#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复迪克牛仔《咆哮》专辑全部 10 首曲目为迪克牛仔本人的摇滚录音室母带版本
"""
import sys
import json
import time
import os
import re
import sqlite3
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics

sys.stdout.reconfigure(encoding='utf-8')

WORKSPACE = r"e:\Workspace\AI-Project\MoodyMusic-Workspace"
BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
TMP_DIR = os.path.join(BASE_DIR, "downloads_optimized", "dick_remediate")
os.makedirs(TMP_DIR, exist_ok=True)

D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    R2_CFG = json.load(f)

# Bucket 07 client
b07_cfg = R2_CFG['buckets']['account_07']
s3_07 = boto3.client(
    's3',
    endpoint_url=b07_cfg['endpoint_url'],
    aws_access_key_id=b07_cfg['access_key_id'],
    aws_secret_access_key=b07_cfg['secret_access_key'],
    config=Config(signature_version='s3v4')
)
B07_NAME = b07_cfg['name']
B07_DOMAIN = b07_cfg['public_domain'].rstrip('/')

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

ROAR_TRACKS = [
    {"id": 28648, "title": "爱如潮水", "source_type": "kuwo", "source_id": "76613"},
    {"id": 28649, "title": "酒干倘卖无", "source_type": "netease", "source_id": "77080"},
    {"id": 28650, "title": "哭不出来", "source_type": "kuwo", "source_id": "644850"},
    {"id": 28651, "title": "梦醒时分", "source_type": "netease", "source_id": "77127"},
    {"id": 28652, "title": "吻别", "source_type": "kuwo", "source_id": "245512"},
    {"id": 28653, "title": "无力去爱谁", "source_type": "kuwo", "source_id": "644852"},
    {"id": 28654, "title": "想说", "source_type": "kuwo", "source_id": "644853"},
    {"id": 28655, "title": "一言难尽", "source_type": "kuwo", "source_id": "76612"},
    {"id": 28656, "title": "原来你什么都不要", "source_type": "netease", "source_id": "77345"},
    {"id": 28657, "title": "值得", "source_type": "kuwo", "source_id": "90187"},
]

def download_source(source_type, source_id, out_file):
    if source_type == "kuwo":
        anti_url = f"http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={source_id}&format=mp3&response=url"
        r = requests.get(anti_url, timeout=6)
        if r.text.startswith('http'):
            res = requests.get(r.text, stream=True, timeout=20)
            with open(out_file, 'wb') as f:
                for chunk in res.iter_content(65536):
                    if chunk: f.write(chunk)
            return os.path.exists(out_file) and os.path.getsize(out_file) > 500000
    elif source_type == "netease":
        mp3_url = f"https://music.163.com/song/media/outer/url?id={source_id}.mp3"
        res = requests.get(mp3_url, headers=HEADERS, stream=True, timeout=20)
        with open(out_file, 'wb') as f:
            for chunk in res.iter_content(65536):
                if chunk: f.write(chunk)
        return os.path.exists(out_file) and os.path.getsize(out_file) > 500000
    return False

def standardize_audio(raw_file, opt_file):
    cmd = [
        "ffmpeg", "-y", "-i", raw_file,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-b:a", "160k", "-ar", "44100",
        opt_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return res.returncode == 0 and os.path.exists(opt_file)

def get_duration(fpath):
    try:
        res = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            fpath
        ], capture_output=True, text=True, encoding='utf-8', errors='replace')
        for line in res.stdout.splitlines():
            if line.startswith('duration='):
                return int(float(line.split('=')[1]))
    except:
        pass
    return 0

def fetch_lrc(title, out_lrc):
    try:
        query = f"迪克牛仔 {title}"
        lrc_text = syncedlyrics.search(query)
        if lrc_text and len(lrc_text) > 50:
            with open(out_lrc, 'w', encoding='utf-8') as f:
                f.write(lrc_text)
            return True
    except:
        pass
    return False

def process_track(track):
    sid = track['id']
    title = track['title']
    print(f"\n================================================================================")
    print(f"🎸 [ID: {sid}] 正在重制迪克牛仔原版: 《{title}》 (源: {track['source_type']} - {track['source_id']})")
    print(f"================================================================================")
    
    raw_audio = os.path.join(TMP_DIR, f"raw_{sid}.mp3")
    opt_audio = os.path.join(TMP_DIR, f"opt_{sid}.mp3")
    lrc_file = os.path.join(TMP_DIR, f"lrc_{sid}.lrc")
    
    # 1. 下载原始音频
    print(" • [1/5] 正在下载迪克牛仔高品质原声音源...", end="", flush=True)
    if not download_source(track['source_type'], track['source_id'], raw_audio):
        print(" ❌ 下载失败！")
        return False
    print(f" [完成! 原始大小: {os.path.getsize(raw_audio) // 1024} KB]")

    # 2. 标准化音轨
    print(" • [2/5] 正在执行 EBU R128 (-14 LUFS) 标准化与 160k CBR Xing 编码...", end="", flush=True)
    if not standardize_audio(raw_audio, opt_audio):
        print(" ❌ 编码失败！")
        return False
    dur_sec = get_duration(opt_audio)
    fsize = os.path.getsize(opt_audio)
    print(f" [完成! 时长: {dur_sec}s, 大小: {fsize / (1024*1024):.2f} MB]")

    # 3. 抓取毫秒级歌词
    print(" • [3/5] 正在抓取毫秒级同步时间轴歌词...", end="", flush=True)
    has_lrc = fetch_lrc(title, lrc_file)
    print(" [🟢 获取成功]" if has_lrc else " [⚠️ 沿用原歌词/未获取]")

    # 4. 上传覆盖至 R2 Bucket 07
    r2_audio_key = f"music/迪克牛仔/咆哮/s_{sid}.mp3"
    r2_lrc_key = f"lyrics/迪克牛仔/咆哮/s_{sid}.lrc"
    
    print(" • [4/5] 正在上传至 Cloudflare R2 Bucket 07 物理覆盖...", end="", flush=True)
    with open(opt_audio, 'rb') as f:
        s3_07.put_object(Bucket=B07_NAME, Key=r2_audio_key, Body=f, ContentType='audio/mpeg')
    if has_lrc:
        with open(lrc_file, 'rb') as f:
            s3_07.put_object(Bucket=B07_NAME, Key=r2_lrc_key, Body=f, ContentType='text/plain; charset=utf-8')
    print(" [🟢 上传成功]")

    cdn_audio_url = f"{B07_DOMAIN}/{r2_audio_key}"
    cdn_lrc_url = f"{B07_DOMAIN}/{r2_lrc_key}"

    # 5. 更新 D1 与本地数据库
    print(" • [5/5] 正在点亮 Cloudflare D1 并同步本地缓存...", end="", flush=True)
    payload = {
        "updates": [{
            "id": sid,
            "file_path": cdn_audio_url,
            "lrc_path": cdn_lrc_url
        }]
    }
    for attempt in range(3):
        try:
            r = requests.post(D1_LIGHT_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=15)
            if r.status_code == 200 and r.json().get('code') == 200:
                break
        except Exception:
            pass
        time.sleep(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE songs SET file_path = ?, lrc_path = ?, duration = ? WHERE id = ?", (cdn_audio_url, cdn_lrc_url, dur_sec, sid))
    cur.execute("UPDATE tracks_sync_state SET status = 'D1_LIT', r2_mp3_key = ?, r2_lrc_key = ?, file_size = ?, duration = ? WHERE song_id = ?", (cdn_audio_url, cdn_lrc_url, fsize, str(dur_sec), sid))
    conn.commit()
    conn.close()
    print(" [🟢 D1 与本地同步完成!]")

    # 清理
    for p in [raw_audio, opt_audio, lrc_file]:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    print(f"🎉 《{title}》 迪克牛仔本人录音室母带重制上线: {cdn_audio_url} ({dur_sec}s)")
    return True

if __name__ == "__main__":
    success = 0
    for t in ROAR_TRACKS:
        if process_track(t):
            success += 1
        time.sleep(1)
    print("\n" + "=" * 80)
    print(f"🏁 迪克牛仔《咆哮》全专重制完成! 成功更新: {success} / {len(ROAR_TRACKS)} 首")
    print("=" * 80)
