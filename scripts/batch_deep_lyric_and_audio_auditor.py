#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发全量扫描重点歌曲 LRC 歌词内容，排查李鬼翻唱、Zither Harp、视频广告等异常
"""

import os
import sys
import json
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

SONGS_FILE = "reports/CORE_ARTISTS_LIT_SONGS.json"

SUSPECT_KEYWORDS = [
    'zither harp', 'zither', 'piano cover', '翻唱', '原唱', '伴奏', '纯音乐',
    '微信公众号', '独播剧场', '关注我们', '欢迎收听', '电台', '广告', '代录', '翻唱网',
    'subtitle', 'volunteer', '字幕组', '优优独播', '官方频道', 'tiktok', '快手',
    'subscribe', 'ghièn mì gõ', 'ghiènmìgõ', 'ghiền mì gõ', 'bilibili'
]

def check_lrc(song):
    lpath = song.get('lrc_path')
    if not lpath:
        return None
    try:
        r = requests.get(lpath, timeout=5)
        if r.status_code == 200:
            text = r.text.lower()
            hit_kws = [kw for kw in SUSPECT_KEYWORDS if kw in text]
            if hit_kws:
                return {
                    "song_id": song.get('song_id'),
                    "artist": song.get('artist'),
                    "album": song.get('album'),
                    "title": song.get('title'),
                    "file_path": song.get('file_path'),
                    "lrc_path": lpath,
                    "hit_keywords": hit_kws,
                    "snippet": r.text[:150]
                }
    except Exception:
        pass
    return None

def main():
    with open(SONGS_FILE, "r", encoding="utf-8") as f:
        songs = json.load(f)
    print(f"📊 载入 {len(songs)} 首歌曲，开始并发抓取并审查 LRC 歌词文本...")
    
    songs_with_lrc = [s for s in songs if s.get('lrc_path')]
    print(f"  • 含有 LRC 歌词的曲目数: {len(songs_with_lrc)} 首")

    suspect_lyrics = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(check_lrc, s): s for s in songs_with_lrc}
        done_cnt = 0
        for f in as_completed(futures):
            done_cnt += 1
            if done_cnt % 1000 == 0:
                print(f"    -> 已审查 {done_cnt}/{len(songs_with_lrc)} 首歌词...")
            res = f.result()
            if res:
                suspect_lyrics.append(res)

    print("\n" + "=" * 80)
    print(f"🚨 歌词命中敏感特征的曲目数: {len(suspect_lyrics)} 首")
    for item in suspect_lyrics:
        print(f"  • ID {item['song_id']}: [{item['artist']}] 《{item['title']}》 - 命中: {item['hit_keywords']}")
        print(f"    片段: {item['snippet'].replace(chr(10), ' ')[:80]}")
    print("=" * 80)

    with open("reports/SUSPECT_LYRICS_AUDIT.json", "w", encoding="utf-8") as f:
        json.dump(suspect_lyrics, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
