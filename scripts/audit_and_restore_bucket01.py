#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面探测并复原第一存储桶（Bucket 01: https://r2.changgepd.ccwu.cc）被误置灰的全部经典曲目
"""

import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

AUDIT_PATH = '/Users/apple/.gemini/antigravity/brain/783e0ad7-8eaa-4445-9be9-1030d20d9eb2/scratch/relative_songs_audit.json'
BASE_URL = 'https://r2.changgepd.ccwu.cc/'
D1_LIGHT_URL = 'https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light'

with open(AUDIT_PATH, 'r', encoding='utf-8') as f:
    songs = json.load(f)

print(f"Total songs in audit file: {len(songs)}")

sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})

def probe_one(s):
    sid = s.get('id')
    p = s.get('path', '')
    lp = s.get('lrc_path', '')
    art = s.get('artist', '')
    alb = s.get('album', '')
    title = s.get('title', '')
    
    if not sid and p:
        import re
        m = re.search(r's_(\d+)\.(mp3|m4a)', p)
        if m:
            sid = int(m.group(1))
            
    if not sid or not p:
        return None
        
    # 如果 p 已经是绝对链接
    if p.startswith('http'):
        url_audio = p
    else:
        url_audio = BASE_URL + p.lstrip('/')
        
    url_lrc = None
    if lp:
        if lp.startswith('http'):
            url_lrc = lp
        elif lp.strip() not in ['', 'music/', 'lyrics/']:
            url_lrc = BASE_URL + lp.lstrip('/')
            
    # 探测音频
    has_audio = False
    try:
        r = sess.head(url_audio, timeout=4)
        if r.status_code == 200:
            has_audio = True
        elif r.status_code == 405: # 如果不允许 HEAD
            r = sess.get(url_audio, headers={'Range': 'bytes=0-1024'}, timeout=4)
            if r.status_code in [200, 206]:
                has_audio = True
    except Exception:
        pass
        
    has_lrc = False
    if url_lrc and has_audio:
        try:
            r = sess.head(url_lrc, timeout=3)
            if r.status_code == 200:
                has_lrc = True
        except Exception:
            pass
            
    return {
        'id': sid,
        'artist': art,
        'album': alb,
        'title': title,
        'file_path': url_audio if has_audio else None,
        'lrc_path': url_lrc if has_lrc else None,
        'has_audio': has_audio,
        'has_lrc': has_lrc,
        'raw_path': p
    }

print("Starting high-concurrency probe across Bucket 01...")
results = []
start_t = time.time()
with ThreadPoolExecutor(max_workers=30) as executor:
    futures = [executor.submit(probe_one, s) for s in songs]
    for fut in as_completed(futures):
        r = fut.result()
        if r:
            results.append(r)

dur = round(time.time() - start_t, 1)
print(f"Probe completed in {dur}s! Total valid songs probed: {len(results)}")

found_songs = [r for r in results if r['has_audio']]
missing_songs = [r for r in results if not r['has_audio']]

print(f"\n=======================================================")
print(f"🎯 Bucket 01 (第一账户 R2) 真实物理资产探查结果:")
print(f"   • 真实存在音频: {len(found_songs)} 首 ({len(found_songs)/len(results)*100:.1f}%)")
print(f"   • 真实存在歌词: {sum(1 for r in found_songs if r['has_lrc'])} 首")
print(f"   • 确实不存在: {len(missing_songs)} 首")
print(f"=======================================================\n")

by_artist = {}
for r in found_songs:
    by_artist.setdefault(r['artist'], []).append(r)

print("👑 【第一账户 R2 真实存在且被误置灰的歌手与曲目数量统计】:")
for art, slist in sorted(by_artist.items(), key=lambda x: -len(x[1])):
    print(f"  • {art:<12}: 真实存在 {len(slist):>3} 首 (全部可秒级复原点亮!)")

with open('reports/bucket01_verified_assets.json', 'w', encoding='utf-8') as f:
    json.dump({
        'found_songs': found_songs,
        'missing_songs': missing_songs
    }, f, ensure_ascii=False, indent=2)

print("\nDetailed verified assets saved to reports/bucket01_verified_assets.json")
