#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_and_finalize_skeletons.py
1. 清理 7 位歌手现有专辑中的所有重复冗余骨架曲目，确保每专保留精确规范曲目。
2. 补齐娃娃剩余 3 张专辑（《我对爱情不灰心》《随风》《放了爱》）及《四季》属性。
3. 全量同构同步至本地 backend/database/catalog_sync.db。
"""

import os
import sys
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
CLEAN_DUP_URL = "https://m-api.changgepd.ccwu.cc/api/admin/albums/cleanup-duplicates"

HEADERS = {'User-Agent': 'NeteaseMusic/9.0.90 (iPhone; iOS 16.5; Scale/3.00)'}
NO_PROXY = {'http': None, 'https': None}

def req_with_retry(method, url, max_retries=5, **kwargs):
    kwargs.setdefault('proxies', NO_PROXY)
    kwargs.setdefault('timeout', 15)
    for attempt in range(1, max_retries + 1):
        try:
            return requests.request(method, url, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                raise e
            time.sleep(attempt * 1.5)

# 1. 补齐娃娃的缺失专辑与属性
WAWA_PENDING = [
    (2238, 29612, "四季", "1992", 12),  # 需补 patch cover & year
    (None, 29610, "我对爱情不灰心", "1993", 9),
    (None, 29606, "随风", "1995", 12),
    (None, 29603, "放了爱", "1996", 10),
]

print("=" * 80)
print("🛠️ 步骤 1: 补全【娃娃】缺失大碟及属性...")
print("=" * 80)

for alb_id, nid, title, year, max_tracks in WAWA_PENDING:
    # 抓取封面与曲目
    r_alb = req_with_retry('GET', f'https://music.163.com/api/v1/album/{nid}', headers=HEADERS).json()
    raw_songs = r_alb.get('songs', [])
    pic_url = r_alb.get('album', {}).get('picUrl', '')

    if alb_id is not None:
        # Patch 四季
        req_with_retry('PATCH', f"{PATCH_ALBUM_URL}{alb_id}", json={"release_date": year, "cover_url": pic_url})
        print(f"  ✅ 补丁《{title}》 (Album ID: {alb_id}) 属性成功 (Year: {year})")
    else:
        # 检查是否已存在
        r_srch = req_with_retry('GET', f"{ALBUM_SEARCH_URL}?artist_id=177&limit=50").json()
        exist = next((a for a in r_srch.get('data', {}).get('albums', []) if a['title'] == title), None)
        if exist:
            cur_aid = exist['id']
            print(f"  • 《{title}》已存在 (Album ID: {cur_aid})")
        else:
            filtered_songs = []
            seen_t = set()
            for s in raw_songs:
                st = s['name'].strip()
                if any(k in st for k in ['(伴奏)', '伴奏', '(Karaoke)', 'Kala']):
                    continue
                if st in seen_t:
                    continue
                seen_t.add(st)
                filtered_songs.append(st)
                if len(filtered_songs) >= max_tracks:
                    break

            payload = {
                "artist_name": "娃娃",
                "album_title": title,
                "songs": [{"title": t, "track_index": i + 1} for i, t in enumerate(filtered_songs)]
            }
            res_ins = req_with_retry('POST', BATCH_INSERT_URL, json=payload, headers={'Content-Type': 'application/json'}).json()
            assert res_ins.get('code') == 200, f"插入失败: {res_ins}"
            cur_aid = res_ins['data']['album_id']
            print(f"  ✅ 《{title}》新建入库成功 (Album ID: {cur_aid}, 曲目数: {len(filtered_songs)})")

        req_with_retry('PATCH', f"{PATCH_ALBUM_URL}{cur_aid}", json={"release_date": year, "cover_url": pic_url})
        print(f"  🎨 《{title}》属性更新完毕")

# 2. 清理所有 7 位歌手的冗余重复曲目
ARTIST_MAP = {
    171: '金海心',
    172: '老狼',
    173: '杨乃文',
    174: '阿雅',
    175: '大张伟',
    176: '江美琪',
    177: '娃娃'
}

print("\n" + "=" * 80)
print("🧹 步骤 2: 全面巡检与清理 7 位歌手所有专辑的重复曲目...")
print("=" * 80)

total_cleaned = 0

for aid, ar_name in ARTIST_MAP.items():
    r_srch = req_with_retry('GET', f"{ALBUM_SEARCH_URL}?artist_id={aid}&limit=50").json()
    albums = r_srch.get('data', {}).get('albums', [])
    print(f"\n🎤 [{aid}] {ar_name} (专辑共 {len(albums)} 张):")

    for a in sorted(albums, key=lambda x: str(x.get('release_date', ''))):
        alb_id = a['id']
        alb_title = a['title']
        
        detail_res = req_with_retry('GET', f"{ALBUM_DETAIL_URL}?album_id={alb_id}").json()
        songs = detail_res.get('data', {}).get('songs', [])

        seen_titles = {}
        dup_ids = []
        for s in songs:
            st = s['title'].strip()
            if st in seen_titles:
                dup_ids.append(s['id'])
            else:
                seen_titles[st] = s['id']

        if dup_ids:
            clean_res = req_with_retry('POST', CLEAN_DUP_URL, json={'album_id': alb_id, 'song_ids': dup_ids}).json()
            del_count = clean_res.get('data', {}).get('deleted_count', 0)
            total_cleaned += del_count
            print(f"  ✂️  《{alb_title}》 (ID: {alb_id}): 清除重复歌曲 {del_count} 首，剩余标准曲目 {len(seen_titles)} 首")
        else:
            print(f"  ✨ 《{alb_title}》 (ID: {alb_id}): 曲目纯净 ({len(songs)} 首)，无重复")

print(f"\n🎉 冗余清洗完成！累计清除重复骨架曲目: {total_cleaned} 首")

# 3. 本地 catalog_sync.db 权威同步
print("\n" + "=" * 80)
print("💾 步骤 3: 全量同构同步至本地 catalog_sync.db...")
print("=" * 80)

conn = sqlite3.connect(LOCAL_DB_PATH)
cur = conn.cursor()

# 清理 local SQLite 中 7 位歌手的旧骨架数据，准备全新全量权威导入
artist_ids_tuple = tuple(ARTIST_MAP.keys())
cur.execute(f"DELETE FROM songs WHERE artist_id IN ({','.join(['?']*len(artist_ids_tuple))})", artist_ids_tuple)
cur.execute(f"DELETE FROM albums WHERE artist_id IN ({','.join(['?']*len(artist_ids_tuple))})", artist_ids_tuple)
conn.commit()

total_synced_albums = 0
total_synced_songs = 0

for aid, ar_name in ARTIST_MAP.items():
    cur.execute("INSERT OR REPLACE INTO artists (id, name) VALUES (?, ?)", (aid, ar_name))
    r_srch = req_with_retry('GET', f"{ALBUM_SEARCH_URL}?artist_id={aid}&limit=50").json()
    albums = r_srch.get('data', {}).get('albums', [])
    
    for a in sorted(albums, key=lambda x: str(x.get('release_date', ''))):
        alb_id = a['id']
        alb_title = a['title']
        rel_date = a.get('release_date') or ''
        cover_url = a.get('cover_url') or ''

        cur.execute(
            "INSERT OR REPLACE INTO albums (id, artist_id, title, release_date, cover_url) VALUES (?, ?, ?, ?, ?)",
            (alb_id, aid, alb_title, rel_date, cover_url)
        )
        total_synced_albums += 1

        detail_res = req_with_retry('GET', f"{ALBUM_DETAIL_URL}?album_id={alb_id}").json()
        songs = detail_res.get('data', {}).get('songs', [])

        for s in songs:
            cur.execute("""
                INSERT OR REPLACE INTO songs (id, artist_id, album_id, title, duration, file_path, lrc_path, track_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s['id'],
                aid,
                alb_id,
                s['title'],
                s.get('duration', 0),
                s.get('file_path') or '',
                s.get('lrc_path') or '',
                s.get('track_index', 0)
            ))
            total_synced_songs += 1

    conn.commit()

conn.close()

print(f"✅ 本地 catalog_sync.db 同步完毕！")
print(f"📊 同步歌手: {len(ARTIST_MAP)} 位")
print(f"📊 同步专辑: {total_synced_albums} 张")
print(f"📊 同步歌曲骨架: {total_synced_songs} 首")
print("=" * 80)
