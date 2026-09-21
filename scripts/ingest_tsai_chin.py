#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 蔡琴殿堂级发烧天碟从 0 到 1 纳管与采录点亮流水线
==============================================================================
执行时机：明早 08:00 (UTC 00:00) D1 配额重置后执行
功能：
1. 调用 /api/admin/ops/songs/batch-insert 自动在 D1 创建艺人【蔡琴】及 3 张大碟：
   - 《民歌蔡琴》 (12 首)
   - 《机遇 - 淡水小镇原声带》 (12 首)
   - 《金声演奏厅》 (10 首)
2. 获取真实 Song ID 并自动调用 master_sparse_remediator 执行 EBU R128 + Whisper 盲听压制；
3. 音频与歌词直接写入 Bucket 09 (moody-music-asset-09) 并实时毫秒级点亮！
==============================================================================
"""

import os
import sys
import json
import requests
import subprocess

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKER = "https://m-api.changgepd.ccwu.cc"
REMEDIATOR = os.path.join(BASE_DIR, "scripts", "master_sparse_remediator.py")

tsai_chin_albums = [
    {
        "album": "民歌蔡琴",
        "songs": [
            "被遗忘的时光", "你的眼神", "恰似你的温柔", "出塞曲", 
            "微风往事", "抉择", "渡口", "怎么能", 
            "再爱我一次", "谢幕曲", "跟我说爱我", "走不完的圆"
        ]
    },
    {
        "album": "机遇 - 淡水小镇原声带",
        "songs": [
            "机遇 I", "白发吟", "偶然", "六月茉莉", "蝶衣", 
            "痴情意外", "机遇 II", "绿岛小夜曲", "月光小夜曲", 
            "明月千里寄相思", "尘缘", "机遇 III"
        ]
    },
    {
        "album": "金声演奏厅",
        "songs": [
            "天天天蓝", "祝我幸福", "用心良苦", "其实你不懂我的心", 
            "为了爱梦一生", "只有分离", "吻别", "一场游戏一场梦", 
            "假如我是真的", "点亮霓虹迎人生"
        ]
    }
]

def main():
    print("==================================================================")
    print("👑 启动华语殿堂级发烧天后【蔡琴】从 0 到 1 纳管与点亮流程")
    print("==================================================================")

    resolved_songs = []

    for item in tsai_chin_albums:
        atitle = item["album"]
        songs_payload = [{"title": s, "track_index": idx} for idx, s in enumerate(item["songs"], 1)]
        
        payload = {
            "artist_name": "蔡琴",
            "album_title": atitle,
            "songs": songs_payload,
            "dry_run": False
        }
        
        try:
            r = requests.post(f"{WORKER}/api/admin/ops/songs/batch-insert", json=payload, timeout=20)
            res = r.json()
            print(f"💿 录入大碟《{atitle}》: {res.get('message')}")
            song_ids = res.get("data", {}).get("song_ids", [])
            
            for s_name, sid in zip(item["songs"], song_ids):
                resolved_songs.append({
                    "id": sid,
                    "artist": "蔡琴",
                    "album": atitle,
                    "title": s_name,
                    "search_title": f"{s_name} 蔡琴"
                })
        except Exception as e:
            print(f"❌ 录入大碟《{atitle}》失败: {e}")

    out_file = os.path.join(BASE_DIR, "sparse_tsai_chin_resolved.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(resolved_songs, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 蔡琴全部 {len(resolved_songs)} 首歌曲已成功录入 D1 并解析真实 ID！")
    print(f"🚀 启动母带重制、EBU R128 标准化、Whisper 人声盲听质检并写入 Bucket 09...")

    env = os.environ.copy()
    env["MOODY_OFFLINE"] = "0" # 开启实时秒级点亮
    subprocess.run([sys.executable, REMEDIATOR, out_file, "tsai_chin"], env=env, cwd=BASE_DIR)

if __name__ == "__main__":
    main()
