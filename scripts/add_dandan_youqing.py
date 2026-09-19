#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 邓丽君传世经典《淡淡幽情》（1983）宋词巅峰大碟骨架注入脚本
==================================================================
1. 建立专辑《淡淡幽情》（发行年份 1983，歌手：邓丽君）
2. 注入完整 12 首传世宋词曲目骨架（独上西楼、但愿人长久、几多愁等）
3. 注入经典专辑封面
"""

import requests
import json
import os
import sys

API_BASE = "https://m-api.changgepd.ccwu.cc"
BATCH_INSERT_URL = f"{API_BASE}/api/admin/ops/songs/batch-insert"
ALBUM_PATCH_URL = f"{API_BASE}/api/admin/albums"
ASSET_UPLOAD_URL = f"{API_BASE}/api/admin/assets/upload"

SONGS_LIST = [
    "独上西楼",
    "但愿人长久",
    "几多愁",
    "芳草无情",
    "清夜悠悠",
    "有谁知我此时情",
    "胭脂泪",
    "万叶千声",
    "人约黄昏后",
    "相看泪眼",
    "欲说还休",
    "思君"
]

# 高清经典封面 (QQ音乐/网易云高清原版黑胶封面)
COVER_URLS = [
    "https://y.qq.com/music/photo_new/T002R300x300M000003zTf3N3C8sK8_1.jpg",
    "http://p1.music.126.net/H4a8G0d6k-t9f1V_n3b9oQ==/109951163428989524.jpg"
]

def main():
    print("=" * 80)
    print("📜 启动邓丽君巅峰神专《淡淡幽情》（1983）骨架构建与注入...")
    print("=" * 80)

    # 1. 检查是否已有该专辑
    r_check = requests.get(f"{API_BASE}/api/admin/albums/search", params={"artist_id": "15", "keyword": "淡淡幽情"}, timeout=10)
    if r_check.ok:
        albums = r_check.json().get("data", {}).get("albums", [])
        for a in albums:
            if "淡淡幽情" in a["title"]:
                print(f"⚠️ 《淡淡幽情》已存在于 D1 (ID: {a['id']})，无需重复创建骨架！")
                return a["id"]

    # 2. 调用 batch-insert 批量创建
    payload = {
        "artist_name": "邓丽君",
        "album_title": "淡淡幽情",
        "songs": [{"title": s, "track_index": idx} for idx, s in enumerate(SONGS_LIST)]
    }

    print(f"📦 正在提交专辑与 12 首曲目骨架到 D1...")
    r = requests.post(BATCH_INSERT_URL, json=payload, timeout=20)
    if not r.ok:
        print(f"❌ 注入失败: {r.status_code} {r.text}")
        return None

    res = r.json().get("data", {})
    album_id = res.get("album_id")
    song_ids = res.get("song_ids", [])
    print(f"✅ 成功创建专辑 ID: {album_id}, 歌曲 IDs: {song_ids}")

    # 3. 设置年份 1983
    if album_id:
        r_patch = requests.patch(f"{ALBUM_PATCH_URL}/{album_id}", json={"release_date": "1983"}, timeout=10)
        if r_patch.ok:
            print("📅 成功设置发行年份: 1983")

        # 4. 下载并转存高清封面
        for c_url in COVER_URLS:
            try:
                resp = requests.get(c_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                if resp.status_code == 200 and len(resp.content) > 5000:
                    files = {"file": (f"cover_{album_id}.jpg", resp.content, "image/jpeg")}
                    data = {"category": "albums", "filename": f"cover_{album_id}.jpg", "album_id": str(album_id)}
                    up_resp = requests.post(ASSET_UPLOAD_URL, files=files, data=data, timeout=20)
                    if up_resp.status_code == 200:
                        print(f"🖼️ 专辑《淡淡幽情》高清黑胶封面转存并关联成功！")
                        break
            except Exception as e:
                print(f"⚠️ 封面抓取转存重试中: {e}")

    print("=" * 80)
    print("🎉 邓丽君《淡淡幽情》大碟全套骨架已成功入驻云端 D1 数据库！")
    print("=" * 80)
    return album_id

if __name__ == "__main__":
    main()
