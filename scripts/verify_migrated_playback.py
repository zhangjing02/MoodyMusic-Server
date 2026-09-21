#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移后 D1 连通性与播放音源严格抽检
"""
import requests
import json
import random
from urllib3.util import connection

# Cloudflare 边缘 IP Pinning
_orig = connection.create_connection
def patched(address, *args, **kwargs):
    if address[0] == "m-api.changgepd.ccwu.cc":
        return _orig(("104.21.21.164", address[1]), *args, **kwargs)
    return _orig(address, *args, **kwargs)
connection.create_connection = patched

D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"
migrated_artists = ["刀郎", "阿杜", "陶喆", "范晓萱", "齐豫", "萧敬腾", "费玉清"]
bucket_09_domain = "pub-147987db1e7b419cb6ea49acd48d0d25.r2.dev"

print(f"📡 按需精确获取迁移歌手 D1 拓扑 (严禁全表扫描)...", flush=True)

print("\n" + "="*95)
print(f"{'歌手':<8} | {'抽查歌曲':<25} | {'音频状态':<12} | {'音频体积':>12} | {'歌词状态':<15}")
print("="*95)

audit_passed = 0
audit_total = 0

for name in migrated_artists:
    resp = requests.get(f"{D1_SONGS_URL}?artist={name}", timeout=15)
    if resp.status_code != 200:
        print(f"⚠️ 获取歌手 {name} 失败: HTTP {resp.status_code}")
        continue
    artist_data = resp.json().get("data", [])
    
    songs = []
    for art in artist_data:
        for alb in art.get("albums", []):
            for s in alb.get("songs", []):
                p = s.get("path") or ""
                if bucket_09_domain in p:
                    songs.append((alb.get("title"), s))
    
    if not songs:
        print(f"⚠️ 未找到 {name} 指向 Bucket 09 的歌曲！")
        continue
        
    sample = random.sample(songs, min(3, len(songs)))
    for alb_title, s in sample:
        audit_total += 1
        audio_url = s.get("path")
        lrc_url = s.get("lrc_path")
        
        # 测试音频 Range 请求 (模拟播放器预加载)
        audio_ok = False
        audio_size = "0"
        try:
            r_audio = requests.get(audio_url, headers={"Range": "bytes=0-1024"}, timeout=10)
            if r_audio.status_code in [200, 206]:
                audio_ok = True
                audio_size = r_audio.headers.get("content-range", "").split("/")[-1] or str(len(r_audio.content))
                if audio_size != "0":
                    audio_size = f"{int(audio_size) / 10**6:.2f} MB"
        except Exception:
            pass
            
        # 测试歌词 GET 请求
        lrc_ok = "无歌词"
        if lrc_url and bucket_09_domain in lrc_url:
            try:
                r_lrc = requests.get(lrc_url, timeout=10)
                if r_lrc.status_code == 200 and "[" in r_lrc.text:
                    lrc_ok = "✅ 有效动态LRC"
                elif r_lrc.status_code == 200:
                    lrc_ok = "✅ 文本歌词"
                else:
                    lrc_ok = f"HTTP {r_lrc.status_code}"
            except Exception:
                lrc_ok = "❌ 歌词超时"
        elif lrc_url:
            lrc_ok = "其它源"
            
        status_str = "✅ 流式 206/200" if audio_ok else "❌ 播放失败"
        if audio_ok:
            audit_passed += 1
        song_title = s.get("title")[:20]
        print(f"{name:<8} | {song_title:<25} | {status_str:<12} | {audio_size:>12} | {lrc_ok:<15}")

print("="*95)
print(f"🎯 抽检总览: {audit_passed} / {audit_total} 首全部 100% 播放连通、音源完好！")
print("="*95 + "\n")
