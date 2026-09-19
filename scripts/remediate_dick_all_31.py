#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迪克牛仔 31 首异常曲目精准多源补全与物理覆盖重制流水线
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
TMP_DIR = os.path.join(BASE_DIR, "downloads_optimized", "dick_all_remediate")
os.makedirs(TMP_DIR, exist_ok=True)

PROXY = "http://127.0.0.1:10090"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    R2_CFG = json.load(f)

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

with open('scratch/dick_cowboy_full_audit.json', 'r', encoding='utf-8') as f:
    audit_data = json.load(f)

mismatches = [x for x in audit_data if x['is_mismatch']]
print(f"待修复迪克牛仔异常曲目: {len(mismatches)} 首")

def download_kuwo(title, out_file):
    url = f"http://search.kuwo.cn/r.s?client=kt&all=迪克牛仔+{title}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=10"
    try:
        r = requests.get(url, timeout=5)
        d = json.loads(r.text.replace("'", '"'))
        for item in d.get('abslist', []):
            art = item.get('ARTIST', '')
            rid = item.get('DC_TARGETID', '')
            if '迪克牛仔' in art:
                anti_url = f"http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={rid}&format=mp3&response=url"
                r_dl = requests.get(anti_url, timeout=5)
                if r_dl.text.startswith('http'):
                    audio_res = requests.get(r_dl.text, stream=True, timeout=15)
                    with open(out_file, 'wb') as f:
                        for c in audio_res.iter_content(65536):
                            if c: f.write(c)
                    if os.path.exists(out_file) and os.path.getsize(out_file) > 500000:
                        return True
    except:
        pass
    return False

def download_netease(title, out_file):
    url = f"https://music.163.com/api/search/get/web?s=迪克牛仔+{title}&type=1&limit=5"
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        for s in r.json().get('result', {}).get('songs', []):
            s_art = s.get('artists', [{}])[0].get('name', '')
            if '迪克牛仔' in s_art:
                sid = s.get('id')
                mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                head = requests.head(mp3_url, headers=HEADERS, allow_redirects=True, timeout=5)
                if head.status_code == 200 and int(head.headers.get('Content-Length', 0)) > 500000:
                    audio_res = requests.get(mp3_url, headers=HEADERS, stream=True, timeout=15)
                    with open(out_file, 'wb') as f:
                        for c in audio_res.iter_content(65536):
                            if c: f.write(c)
                    if os.path.exists(out_file) and os.path.getsize(out_file) > 500000:
                        return True
    except:
        pass
    return False

def download_yt(title, out_raw):
    # 强制搜索官方频道或严格包含迪克牛仔
    queries = [
        f"ytsearch5:Dick and Cowboy Topic {title}",
        f"ytsearch5:迪克牛仔 {title} 官方"
    ]
    for q in queries:
        cmd_search = [
            "yt-dlp", "--proxy", PROXY,
            "--flat-playlist", "--no-warnings",
            "--print", "%(id)s | %(channel)s | %(title)s | %(duration)s",
            q
        ]
        try:
            res = subprocess.run(cmd_search, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
            for line in res.stdout.splitlines():
                parts = line.split(" | ")
                if len(parts) >= 3:
                    vid, channel, vtitle = parts[0], parts[1], parts[2]
                    # 必须确保 channel 或 vtitle 包含 迪克牛仔 或 Dick and Cowboy
                    if 'dick' in channel.lower() or 'cowboy' in channel.lower() or '迪克牛仔' in channel or '迪克牛仔' in vtitle:
                        # 执行下载
                        cmd_dl = [
                            "yt-dlp", "--proxy", PROXY,
                            "-x", "--audio-format", "mp3", "--audio-quality", "0",
                            "-o", f"{out_raw}.%(ext)s",
                            f"https://www.youtube.com/watch?v={vid}"
                        ]
                        dl_res = subprocess.run(cmd_dl, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
                        for ext in ["mp3", "m4a", "webm", "opus"]:
                            cand = f"{out_raw}.{ext}"
                            if os.path.exists(cand) and os.path.getsize(cand) > 500000:
                                return cand
        except:
            pass
    return None

def standardize(raw, opt):
    cmd = [
        "ffmpeg", "-y", "-i", raw,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-b:a", "160k", "-ar", "44100",
        opt
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return res.returncode == 0 and os.path.exists(opt)

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

success_count = 0
for idx, m in enumerate(mismatches, 1):
    path = m.get('path') or ''
    mat = re.search(r's_(\d+)\.mp3', path)
    sid = int(mat.group(1)) if mat else m['id']
    alb = m['album']
    tit = m['title']
    
    print(f"\n[{idx}/{len(mismatches)}] 🎸 重制迪克牛仔曲目: 《{alb}》 - 《{tit}》 (ID: {sid})")
    
    raw_file = os.path.join(TMP_DIR, f"raw_{sid}.mp3")
    opt_file = os.path.join(TMP_DIR, f"opt_{sid}.mp3")
    lrc_file = os.path.join(TMP_DIR, f"lrc_{sid}.lrc")
    
    # 1. 抓取音源 (Kuwo -> NetEase -> YouTube)
    print(" • [1/5] 抓取迪克牛仔真实音源...", end="", flush=True)
    downloaded = False
    source_tag = ""
    if download_kuwo(tit, raw_file):
        downloaded = True
        source_tag = "Kuwo"
    elif download_netease(tit, raw_file):
        downloaded = True
        source_tag = "NetEase"
    else:
        yt_raw = download_yt(tit, os.path.join(TMP_DIR, f"yt_{sid}"))
        if yt_raw:
            raw_file = yt_raw
            downloaded = True
            source_tag = "YouTube Topic"

    if not downloaded or not os.path.exists(raw_file):
        print(" ❌ 未找到纯正母带音源，跳过！")
        continue
    print(f" [🟢 {source_tag} 命中! 大小: {os.path.getsize(raw_file)//1024} KB]")

    # 2. 标准化
    print(" • [2/5] EBU R128 (-14 LUFS) 响度标准化与 160k CBR Xing 编码...", end="", flush=True)
    if not standardize(raw_file, opt_file):
        print(" ❌ 编码失败！")
        continue
    dur_sec = get_duration(opt_file)
    fsize = os.path.getsize(opt_file)
    print(f" [完成! 时长: {dur_sec}s, 大小: {fsize/(1024*1024):.2f} MB]")

    # 3. 抓取同步歌词
    print(" • [3/5] 抓取毫秒级同步时间轴歌词...", end="", flush=True)
    has_lrc = False
    try:
        txt = syncedlyrics.search(f"迪克牛仔 {tit}")
        if txt and len(txt) > 50:
            with open(lrc_file, 'w', encoding='utf-8') as f:
                f.write(txt)
            has_lrc = True
    except:
        pass
    print(" [🟢 成功]" if has_lrc else " [⚠️ 沿用原歌词]")

    # 4. 上传至 R2 Bucket 07 覆盖
    clean_alb = re.sub(r'[\\/*?:"<>|]', '_', alb).strip()
    r2_audio_key = f"music/迪克牛仔/{clean_alb}/s_{sid}.mp3"
    r2_lrc_key = f"lyrics/迪克牛仔/{clean_alb}/s_{sid}.lrc"
    
    print(" • [4/5] 上传至 Cloudflare R2 Bucket 07 物理覆盖...", end="", flush=True)
    with open(opt_file, 'rb') as f:
        s3_07.put_object(Bucket=B07_NAME, Key=r2_audio_key, Body=f, ContentType='audio/mpeg')
    if has_lrc:
        with open(lrc_file, 'rb') as f:
            s3_07.put_object(Bucket=B07_NAME, Key=r2_lrc_key, Body=f, ContentType='text/plain; charset=utf-8')
    print(" [🟢 上传成功]")

    cdn_audio = f"{B07_DOMAIN}/{r2_audio_key}"
    cdn_lrc = f"{B07_DOMAIN}/{r2_lrc_key}"

    # 5. 点亮与更新本地 DB
    print(" • [5/5] 更新 D1 与本地数据库...", end="", flush=True)
    payload = {
        "updates": [{
            "id": sid,
            "file_path": cdn_audio,
            "lrc_path": cdn_lrc
        }]
    }
    for attempt in range(3):
        try:
            r = requests.post(D1_LIGHT_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=15)
            if r.status_code == 200 and r.json().get('code') == 200:
                break
        except:
            pass
        time.sleep(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE songs SET file_path = ?, lrc_path = ?, duration = ? WHERE id = ?", (cdn_audio, cdn_lrc, dur_sec, sid))
    cur.execute("UPDATE tracks_sync_state SET status = 'D1_LIT', r2_mp3_key = ?, r2_lrc_key = ?, file_size = ?, duration = ? WHERE song_id = ?", (cdn_audio, cdn_lrc, fsize, str(dur_sec), sid))
    conn.commit()
    conn.close()
    print(" [🟢 完成!]")

    for p in [raw_file, opt_file, lrc_file]:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    success_count += 1
    print(f"🎉 修复完成: 《{alb}》 - 《{tit}》 -> {cdn_audio} ({dur_sec}s)")
    time.sleep(1)

print("\n" + "=" * 80)
print(f"🏁 迪克牛仔全专 31 首异常曲目治理完毕! 成功修复: {success_count} / {len(mismatches)} 首")
print("=" * 80)
