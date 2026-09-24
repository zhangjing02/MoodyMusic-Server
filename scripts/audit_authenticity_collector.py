#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 华语重点天王天后及热门歌手全盘已点亮曲目抽取与特征初筛脚本
"""

import os
import sys
import json
import time
import requests
from collections import defaultdict

CORE_ARTISTS = [
    # 华语天王天后与殿堂级
    "周杰伦", "陈奕迅", "王菲", "张学友", "刘德华", "张国荣", "黎明", "郭富城",
    "孙燕姿", "蔡依林", "林俊杰", "王力宏", "陶喆", "梁静茹", "莫文蔚", "萧亚轩",
    "张惠妹", "田馥甄", "S.H.E", "五月天", "Beyond", "邓丽君", "谭咏麟", "周华健",
    "费玉清", "任贤齐", "伍佰", "李宗盛", "罗大佑", "齐秦", "齐豫", "童安格",
    "张信哲", "许茹芸", "苏慧伦", "郑智化", "迪克牛仔", "曾轶可", "刀郎", "容祖儿",
    "古巨基", "品冠", "游鸿明", "动力火车", "杨丞琳", "萧煌奇", "郁可唯", "张韶涵",
    "蔡琴", "范晓萱", "范玮琪", "林忆莲", "潘玮柏", "汪峰", "薛之谦", "毛不易",
    "朴树", "李荣浩", "黄小琥", "黄品源", "李玟", "万芳", "高胜美"
]

API_BASE = "https://m-api.changgepd.ccwu.cc"

def collect_artists_data():
    print("=" * 80)
    print(f"🔍 启动重点华语歌手全盘已点亮资产检索 (目标重点歌手: {len(CORE_ARTISTS)} 位)...")
    print("=" * 80)
    
    # 1. 获取 skeleton 确认实际名字和 ID
    r = requests.get(f"{API_BASE}/api/skeleton", timeout=20)
    if not r.ok:
        print(f"❌ 获取 skeleton 失败: {r.status_code}")
        return []
    
    all_artists = r.json().get('data', {}).get('artists', [])
    artist_lookup = {}
    for a in all_artists:
        name = a['name']
        artist_lookup[name] = a['id']
        # 兼容 JOLIN蔡依林 等
        for core in CORE_ARTISTS:
            if core.lower() in name.lower() or name.lower() in core.lower():
                artist_lookup[core] = a['id']
    
    matched_artists = []
    for core in CORE_ARTISTS:
        if core in artist_lookup:
            matched_artists.append((core, artist_lookup[core]))
        else:
            print(f"⚠️ 未在曲库名册中精确匹配歌手: {core}")
            
    print(f"\n✅ 成功匹配到 {len(matched_artists)} 位核心重点歌手")
    
    all_lit_songs = []
    
    for idx, (core_name, art_id) in enumerate(matched_artists, 1):
        clean_id = art_id.replace('db_', '')
        try:
            res = requests.get(f"{API_BASE}/api/songs", params={"artistId": clean_id}, timeout=20)
            if not res.ok:
                print(f"[{idx:02d}/{len(matched_artists):02d}] ❌ {core_name} 拉取失败: {res.status_code}")
                continue
            data = res.json().get('data', [])
            if not data:
                continue
            art_obj = data[0]
            albums = art_obj.get('albums', [])
            art_lit_count = 0
            for alb in albums:
                alb_title = alb.get('title', '')
                alb_id = alb.get('id')
                for song in alb.get('songs', []):
                    fpath = song.get('file_path') or song.get('path')
                    if fpath:
                        art_lit_count += 1
                        all_lit_songs.append({
                            "song_id": song.get('id'),
                            "artist_id": clean_id,
                            "artist": art_obj.get('name'),
                            "album_id": alb_id,
                            "album": alb_title,
                            "title": song.get('title'),
                            "file_path": fpath,
                            "lrc_path": song.get('lrc_path'),
                            "track_index": song.get('track_index')
                        })
            print(f"[{idx:02d}/{len(matched_artists):02d}] 🎤 {art_obj.get('name')} (ID: {clean_id}): {len(albums)} 张专辑, {art_lit_count} 首已点亮")
        except Exception as e:
            print(f"[{idx:02d}/{len(matched_artists):02d}] ❌ {core_name} 请求异常: {e}")
            
    print("\n" + "=" * 80)
    print(f"📊 重点歌手已点亮总曲目数: {len(all_lit_songs)} 首")
    print("=" * 80)
    
    out_file = "reports/CORE_ARTISTS_LIT_SONGS.json"
    os.makedirs("reports", exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_lit_songs, f, ensure_ascii=False, indent=2)
    print(f"💾 数据已成功缓存至 {out_file}")
    return all_lit_songs

if __name__ == "__main__":
    collect_artists_data()
