#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_remediate_all.py
MoodyMusic 全库实锤错版与占位音轨 (158首) 全自动化定向重采、标准化与原子切链修复引擎
"""

import os
import sys
import json
import re
import time
import requests
import sqlite3
import subprocess
import boto3
import zhconv
from botocore.config import Config

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts')
from r2_safety_guard import safe_r2_put_object, get_r2_config

GROQ_KEY = os.environ.get('GROQ_API_KEY')
GROQ_API_URL = 'https://api.groq.com/openai/v1/audio/transcriptions'
TMP_DIR = r'G:\music-backup\tmp\remediate_158'
os.makedirs(TMP_DIR, exist_ok=True)

PROGRESS_FILE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\remediate_progress.json'
TASKS_FILE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\remediate_accurate_tasks.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/'
}

def get_proxy():
    for p in [7897, 7890, 10090, 10808]:
        try:
            r = requests.get("https://www.google.com", proxies={"https": f"http://127.0.0.1:{p}"}, timeout=1.5)
            if r.status_code == 200:
                return f"http://127.0.0.1:{p}"
        except Exception:
            pass
    return "http://127.0.0.1:7897"

PROXY = get_proxy()

def clean_title(title: str) -> str:
    return re.sub(r'\(.*?\)|\[.*?\]|（.*?）', '', title).strip()

def to_simplified(text: str) -> str:
    try:
        return zhconv.convert(text, 'zh-cn')
    except Exception:
        return text

# 1. NetEase Sourcing
def fetch_netease(artist: str, title: str, out_file: str) -> tuple[bool, str]:
    queries = [
        f"{artist} {title}",
        f"{to_simplified(artist)} {to_simplified(title)}",
        f"{artist} {clean_title(title)}"
    ]
    seen_q = set()
    for q in queries:
        if q in seen_q: continue
        seen_q.add(q)
        try:
            r = requests.post("https://music.163.com/api/cloudsearch/pc", data={"s": q, "type": 1, "limit": 6}, headers=HEADERS, timeout=6)
            if r.status_code == 200:
                songs = r.json().get("result", {}).get("songs", [])
                for s in songs:
                    art_name = s.get("artists", [{}])[0].get("name", "")
                    s_name = s.get("name", "")
                    # Match artist and exclude accompaniments
                    if (artist.lower() in art_name.lower() or art_name.lower() in artist.lower() or to_simplified(artist) in to_simplified(art_name) or "群星" in art_name) \
                       and not any(k in s_name for k in ["伴奏", "纯音乐", "instrumental", "karaoke"]):
                        sid = s.get("id")
                        mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                        head = requests.head(mp3_url, headers=HEADERS, allow_redirects=True, timeout=5)
                        if head.status_code == 200 and int(head.headers.get("Content-Length", 0)) > 600000:
                            dl = requests.get(mp3_url, headers=HEADERS, stream=True, timeout=20)
                            with open(out_file, "wb") as f:
                                for chunk in dl.iter_content(65536):
                                    if chunk: f.write(chunk)
                            if os.path.exists(out_file) and os.path.getsize(out_file) > 600000:
                                return True, f"NetEase 正版 (ID: {sid})"
        except Exception:
            pass
    return False, ""

# 2. Kuwo Sourcing
def fetch_kuwo(artist: str, title: str, out_file: str) -> tuple[bool, str]:
    queries = [
        f"{artist} {title}",
        f"{to_simplified(artist)} {to_simplified(title)}",
        f"{artist} {clean_title(title)}"
    ]
    seen_q = set()
    for q in queries:
        if q in seen_q: continue
        seen_q.add(q)
        encoded_q = requests.utils.quote(q)
        url = f"http://search.kuwo.cn/r.s?client=kt&all={encoded_q}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=8"
        try:
            r = requests.get(url, timeout=6)
            d = json.loads(r.text.replace("'", '"'))
            for item in d.get("abslist", []):
                art = item.get("ARTIST", "")
                sname = item.get("SONGNAME", "")
                rid = item.get("DC_TARGETID", "")
                if (artist.lower() in art.lower() or art.lower() in artist.lower() or to_simplified(artist) in to_simplified(art)) \
                   and not any(k in sname for k in ["伴奏", "纯音乐", "instrumental", "karaoke"]):
                    anti = f"http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={rid}&format=mp3&response=url"
                    r_anti = requests.get(anti, timeout=5)
                    if r_anti.text.startswith("http"):
                        dl = requests.get(r_anti.text, stream=True, timeout=20)
                        with open(out_file, "wb") as f:
                            for chunk in dl.iter_content(65536):
                                if chunk: f.write(chunk)
                        if os.path.exists(out_file) and os.path.getsize(out_file) > 600000:
                            return True, f"Kuwo 录音室 (RID: {rid})"
        except Exception:
            pass
    return False, ""

# 3. YouTube Sourcing
def fetch_youtube(artist: str, title: str, out_file: str) -> tuple[bool, str]:
    queries = [
        f"{artist} {title} 音频",
        f"{artist} {clean_title(title)} 官方",
        f"{artist} {title} Topic",
        f"{to_simplified(artist)} {to_simplified(title)}",
        f"{artist} {title}"
    ]
    base_raw = os.path.join(TMP_DIR, "yt_temp")
    seen = set()
    for q in queries:
        if q in seen: continue
        seen.add(q)
        cmd_search = [
            "yt-dlp", "--proxy", PROXY,
            "--extractor-args", "youtube:player_client=android",
            "--no-warnings", "--dump-json",
            f"ytsearch3:{q}"
        ]
        try:
            res = subprocess.run(cmd_search, capture_output=True, timeout=30)
            lines = res.stdout.decode('utf-8', errors='replace').splitlines()
            for line in lines:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    vid = data.get("id")
                    vtitle = data.get("title", "")
                    channel = data.get("uploader", "")
                    dur = data.get("duration", 0)
                    if not vid or dur < 50 or dur > 600:
                        continue
                    
                    ch_l = channel.lower()
                    vt_l = vtitle.lower()
                    art_l = artist.lower()
                    art_simp = to_simplified(artist).lower()
                    t_l = clean_title(title).lower()
                    t_simp = to_simplified(clean_title(title)).lower()
                    
                    art_match = (
                        art_l in ch_l or art_l in vt_l or 
                        art_simp in ch_l or art_simp in vt_l or 
                        'topic' in ch_l or 'rock records' in ch_l or 
                        '滾石唱片' in ch_l or 'power station' in ch_l or 
                        'joey yung' in ch_l or 'wakin chau' in ch_l or 
                        'elva' in ch_l or 'crowd lu' in ch_l or 'chyi chin' in ch_l
                    )
                    title_match = (
                        t_l in vt_l or t_simp in vt_l or 
                        to_simplified(title).lower() in vt_l or 
                        title.lower() in vt_l
                    )
                    
                    bad = any(k in vt_l for k in ["伴奏", "纯音乐", "piano cover", "guitar cover", "reaction", "tutorial", "舞蹈教室", "花絮"])
                    
                    if art_match and title_match and not bad:
                        cmd_dl = [
                            "yt-dlp", "--proxy", PROXY,
                            "--extractor-args", "youtube:player_client=android",
                            "-x", "--audio-format", "mp3", "--audio-quality", "0",
                            "-o", f"{base_raw}.%(ext)s",
                            f"https://www.youtube.com/watch?v={vid}"
                        ]
                        subprocess.run(cmd_dl, capture_output=True, timeout=60)
                        for ext in ["mp3", "m4a", "webm", "opus"]:
                            cand = f"{base_raw}.{ext}"
                            if os.path.exists(cand) and os.path.getsize(cand) > 600000:
                                subprocess.run(["ffmpeg", "-y", "-i", cand, "-b:a", "160k", out_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                os.remove(cand)
                                return True, f"YouTube 官方 ({vid} - {vtitle[:20]})"
                except Exception:
                    pass
        except Exception:
            pass
    return False, ""

def fetch_best_audio(artist: str, title: str, out_raw: str) -> tuple[bool, str]:
    # Tier 1: NetEase
    ok, desc = fetch_netease(artist, title, out_raw)
    if ok: return True, desc
    # Tier 2: Kuwo
    ok, desc = fetch_kuwo(artist, title, out_raw)
    if ok: return True, desc
    # Tier 3: YouTube
    ok, desc = fetch_youtube(artist, title, out_raw)
    if ok: return True, desc
    return False, "全渠道未收录或无合适音源"

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed": [], "failed": []}

def save_progress(prog):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)

def main():
    print("=" * 80)
    print("🚀 启动 MoodyMusic 全库 158 首实锤错版与占位音轨工业级自动化修复流水线")
    print("=" * 80)
    
    with open(TASKS_FILE, 'r', encoding='utf-8') as f:
        tasks = json.load(f)
    print(f"总待修复任务数: {len(tasks)}")
    
    progress = load_progress()
    done_ids = set(progress.get("completed", []))
    progress["failed"] = []
    print(f"已完成历史任务数: {len(done_ids)}")
    
    cfg = get_r2_config()
    acc_key = 'account_13'
    acc = cfg['buckets'][acc_key]
    
    s3 = boto3.client(
        's3',
        endpoint_url=f"https://{acc['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=acc['access_key_id'],
        aws_secret_access_key=acc['secret_access_key'],
        region_name='auto'
    )
    
    conn = sqlite3.connect(r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\database\catalog_sync.db')
    cur = conn.cursor()
    
    success_count = 0
    fail_count = 0
    
    for idx, t in enumerate(tasks, 1):
        sid = t['id']
        artist = t['artist']
        album = t['album']
        title = t['title']
        
        if sid in done_ids:
            continue
            
        print(f"\n[{idx}/{len(tasks)}] 正在治理: [{artist}] 《{album}》 - 《{title}》 (ID: {sid})")
        
        raw_path = os.path.join(TMP_DIR, f"raw_{sid}.mp3")
        opt_path = os.path.join(TMP_DIR, f"opt_{sid}.mp3")
        clip_path = os.path.join(TMP_DIR, f"clip_{sid}.mp3")
        
        for p in [raw_path, opt_path, clip_path]:
            if os.path.exists(p): os.remove(p)
            
        ok, src_desc = fetch_best_audio(artist, title, raw_path)
        if not ok:
            print(f"  ❌ 采录失败: {src_desc}")
            progress["failed"].append({"id": sid, "artist": artist, "title": title, "reason": src_desc})
            save_progress(progress)
            fail_count += 1
            continue
            
        print(f"  📥 采录成功: 来自 {src_desc} ({os.path.getsize(raw_path)//1024} KB)")
        
        try:
            # Standardize audio (loudnorm -14 LUFS, 160k CBR, 44.1kHz)
            cmd_ff = [
                "ffmpeg", "-y", "-i", raw_path,
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                "-codec:a", "libmp3lame", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                opt_path
            ]
            subprocess.run(cmd_ff, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            # Probe accurate duration
            cmd_probe = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", opt_path]
            probe_res = subprocess.run(cmd_probe, capture_output=True)
            probe_data = json.loads(probe_res.stdout.decode('utf-8', errors='replace'))
            dur = int(float(probe_data['format']['duration']))
            print(f"  🎵 压制标准化完成: 时长 {dur} 秒, 160k CBR")
            
            # Upload to account_13 via safe guard
            with open(opt_path, "rb") as f:
                audio_data = f.read()
                
            r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
            safe_r2_put_object(
                s3_client=s3,
                bucket_name=acc['name'],
                account_key=acc_key,
                key=r2_key,
                body=audio_data,
                content_type='audio/mpeg'
            )
            
            cdn_url = f"{acc['public_domain']}/{r2_key}"
            
            # Verify CDN HTTP 200
            chk = requests.head(cdn_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            if chk.status_code != 200:
                raise RuntimeError(f"CDN check failed: HTTP {chk.status_code}")
                
            print(f"  ☁️ R2 写入成功 & CDN 200 OK: {cdn_url}")
            
            # Update remote D1
            cmd_d1 = [
                'npx', 'wrangler', 'd1', 'execute', 'moody-d1-test', '--remote',
                f"--command=UPDATE songs SET file_path = '{cdn_url}', duration = {dur} WHERE id = {sid};"
            ]
            subprocess.run(cmd_d1, cwd=r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
            
            # Update local DB
            cur.execute("UPDATE songs SET file_path = ?, duration = ? WHERE id = ?", (cdn_url, dur, sid))
            conn.commit()
            
            print(f"  🎉 修复成功: ID {sid} 已恢复正版播放！")
            progress["completed"].append(sid)
            save_progress(progress)
            success_count += 1
            
        except Exception as e:
            print(f"  ❌ 处理/上传异常: {e}")
            progress["failed"].append({"id": sid, "artist": artist, "title": title, "reason": str(e)})
            save_progress(progress)
            fail_count += 1
            
        finally:
            for p in [raw_path, opt_path, clip_path]:
                if os.path.exists(p): os.remove(p)
                
        time.sleep(1.2)
        
    print("\n" + "=" * 80)
    print("全库自动化修复流水线执行完毕！")
    print(f"本次成功: {success_count} 首, 失败: {fail_count} 首, 历史累计完成: {len(progress['completed'])} 首")
    print("=" * 80)

if __name__ == "__main__":
    main()
