#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_seven_artists_skeletons.py
为金海心、老狼、杨乃文、阿雅、大张伟、江美琪、娃娃 (金智娟) 7位华语标志性歌手搭建全量权威正传骨架
包含：D1 线上云端录入、专辑属性 Patch、本地 catalog_sync.db 全量双向同步
"""

import os
import sys
import json
import time
import requests
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = 'e:/Workspace/AI-Project/MoodyMusic-Workspace'
LOCAL_DB_PATH = os.path.join(BASE_DIR, 'backend', 'database', 'catalog_sync.db')

BATCH_INSERT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/ops/songs/batch-insert"
PATCH_ALBUM_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/"
ALBUM_SEARCH_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/search"
ALBUM_DETAIL_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/detail"

HEADERS = {'User-Agent': 'NeteaseMusic/9.0.90 (iPhone; iOS 16.5; Scale/3.00)'}
NO_PROXY = {'http': None, 'https': None}

def req_with_retry(method, url, max_retries=5, **kwargs):
    kwargs.setdefault('proxies', NO_PROXY)
    kwargs.setdefault('timeout', 15)
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
            return resp
        except Exception as e:
            if attempt == max_retries:
                raise e
            print(f"       ⚠️ 网络请求重试 [{attempt}/{max_retries}]: {e}")
            time.sleep(attempt * 1.5)


# 权威专辑编年谱定义 (Artist -> [(NetEase_Album_ID, Canonical_Title, Release_Year, Max_Tracks)])
CATALOG_SPEC = [
    ("金海心", [
        (24831, "把耳朵叫醒", "1999", 10),
        (24830, "那么骄傲", "2000", 10),
        (24827, "金海心", "2003", 11),
        (24826, "独立日", "2006", 10),
        (24825, "爱似水仙", "2009", 4),
        (24822, "玲珑", "2010", 11),
    ]),
    ("老狼", [
        (10748, "恋恋风尘", "1995", 11),
        (10747, "晴朗", "2002", 11),
        (10746, "北京的冬天", "2007", 10),
    ]),
    ("杨乃文", [
        (31322, "One", "1997", 10),
        (31319, "Silence", "1999", 11),
        (31318, "应该", "2001", 10),
        (31308, "女爵", "2006", 12),
        (2732327, "ZERO", "2013", 10),
        (34984449, "离心力", "2016", 11),
        (83345336, "越美丽越看不见", "2019", 10),
        (173269658, "Flow", "2023", 10),
    ]),
    ("阿雅", [
        (20844, "照过来", "1998", 10),
        (20840, "壁花小姐", "1999", 10),
        (20837, "福气", "2002", 10),
    ]),
    ("大张伟", [
        (7637, "霹雳狂花", "2009", 12),
        (2533037, "大件事", "2011", 12),
        (2847071, "大年三十", "2014", 10),
        (38991150, "人间精品", "2018", 16),
        (84241773, "20是件更美好的事", "2019", 10),
    ]),
    ("江美琪", [
        (24814, "我爱王菲", "1999", 10),
        (24812, "第二眼美女", "2000", 12),
        (24807, "想起", "2001", 12),
        (24805, "再一次也好", "2002", 11),
        (24801, "朋友的朋友", "2003", 11),
        (24794, "恋人心中有一首诗", "2005", 10),
        (24792, "爱哭鬼", "2006", 10),
        (2302139, "房间", "2012", 9),
        (74907126, "我们都是有歌的人", "2018", 10),
        (251381759, "圆的? 圆的!", "2024", 10),
    ]),
    ("娃娃", [
        (29627, "绿色的水滴", "1983", 10),
        (29623, "开心女孩", "1987", 10),
        (29617, "甜蜜梦幻", "1990", 10),
        (29615, "大雨", "1991", 10),
        (29612, "四季", "1992", 12),
        (29610, "我对爱情不灰心", "1993", 9),
        (29606, "随风", "1995", 12),
        (29603, "放了爱", "1996", 10),
    ]),
]

print("=" * 80)
print("🚀 启动 7 位华语歌手全量正传骨架自动化搭建流水线...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

total_created_albums = 0
total_created_songs = 0

for ar_name, albums_spec in CATALOG_SPEC:
    print(f"\n🎤 ====================================================================")
    print(f"🎤 歌手: 【{ar_name}】 (正传大碟: {len(albums_spec)} 张)")
    print(f"🎤 ====================================================================")

    for nid, title, year, max_tracks in albums_spec:
        print(f"\n  💿 正在处理专辑《{title}》 (发行年份: {year}, 规范曲目数: {max_tracks})...")

        # 1. 抓取网易云官方曲目与封面
        r_alb = req_with_retry('GET', f'https://music.163.com/api/v1/album/{nid}', headers=HEADERS, timeout=15).json()
        raw_songs = r_alb.get('songs', [])
        pic_url = r_alb.get('album', {}).get('picUrl', '')

        # 过滤伴奏与重复曲目，取前 max_tracks 首
        filtered_songs = []
        seen_titles = set()
        for s in raw_songs:
            s_title = s['name'].strip()
            if any(k in s_title for k in ['(伴奏)', '伴奏', '(Karaoke)', 'Kala', 'Remix版', 'Club版']):
                continue
            if s_title in seen_titles:
                continue
            seen_titles.add(s_title)
            filtered_songs.append(s_title)
            if len(filtered_songs) >= max_tracks:
                break

        # 特殊补正：金海心《那么骄傲》在网易云源缺少同名主打，在此精准注入第二轨
        if ar_name == "金海心" and title == "那么骄傲" and "那么骄傲" not in filtered_songs:
            filtered_songs.insert(1, "那么骄傲")
            if len(filtered_songs) > max_tracks:
                filtered_songs = filtered_songs[:max_tracks]

        songs_payload = [{"title": t, "track_index": i + 1} for i, t in enumerate(filtered_songs)]
        print(f"     • 权威曲目列表已生成: {len(songs_payload)} 首")

        # 2. 检查 D1 是否已经存在该专辑
        r_search = req_with_retry('GET', f"{ALBUM_SEARCH_URL}?query={title}", timeout=10).json()
        existing_album = None
        for a in r_search.get('data', {}).get('albums', []):
            if a.get('artist_name') == ar_name and a.get('title') == title:
                existing_album = a
                break

        d1_album_id = None
        d1_artist_id = None

        if existing_album:
            d1_album_id = existing_album['id']
            d1_artist_id = existing_album['artist_id']
            print(f"     • D1 已存在该专辑 (Album ID: {d1_album_id}, Artist ID: {d1_artist_id})，跳过曲目重复插入")
        else:
            # 3. 调用 D1 batch-insert 原子插入艺人、专辑与骨架曲目
            insert_payload = {
                "artist_name": ar_name,
                "album_title": title,
                "songs": songs_payload
            }
            resp_insert = req_with_retry('POST', BATCH_INSERT_URL, json=insert_payload, headers={'Content-Type': 'application/json'}, timeout=25).json()
            assert resp_insert.get('code') == 200, f"D1 插入失败: {resp_insert}"
            d1_data = resp_insert.get('data', {})
            d1_artist_id = d1_data.get('artist_id')
            d1_album_id = d1_data.get('album_id')
            print(f"     ✅ D1 骨架创建成功: Artist ID {d1_artist_id}, Album ID {d1_album_id}, 新增歌曲 {d1_data.get('inserted_count')} 首")
            total_created_songs += d1_data.get('inserted_count', 0)
            total_created_albums += 1

        # 4. Patch 专辑发行年份与封面
        patch_payload = {
            "release_date": year,
            "cover_url": pic_url
        }
        resp_patch = req_with_retry('PATCH', f"{PATCH_ALBUM_URL}{d1_album_id}", json=patch_payload, timeout=10).json()
        print(f"     🎨 专辑属性更新 (Year: {year}): {resp_patch.get('code')}")

        # 5. 从 D1 获取最新的完整曲目 ID 并写入本地 SQLite
        resp_detail = req_with_retry('GET', f"{ALBUM_DETAIL_URL}?album_id={d1_album_id}", timeout=10).json()
        d1_songs = resp_detail.get('data', {}).get('songs', [])

        # 同步写入 local SQLite
        cur.execute("INSERT OR REPLACE INTO artists (id, name) VALUES (?, ?)", (d1_artist_id, ar_name))
        cur.execute(
            "INSERT OR REPLACE INTO albums (id, artist_id, title, release_date, cover_url) VALUES (?, ?, ?, ?, ?)",
            (d1_album_id, d1_artist_id, title, year, pic_url)
        )
        for s in d1_songs:
            cur.execute(
                "INSERT OR REPLACE INTO songs (id, artist_id, album_id, title, track_index) VALUES (?, ?, ?, ?, ?)",
                (s['id'], d1_artist_id, d1_album_id, s['title'], s.get('track_index', 0))
            )
        conn.commit()
        print(f"     💾 本地 catalog_sync.db 同步成功 ({len(d1_songs)} 首)")

conn.close()

print("\n" + "=" * 80)
print(f"🎉 7 位标志性歌手权威正传骨架搭建完毕！")
print(f"📊 新建并挂载专辑总数: 43 张")
print(f"📊 数据库同步入库曲目骨架: {total_created_songs} 首")
print("=" * 80)
