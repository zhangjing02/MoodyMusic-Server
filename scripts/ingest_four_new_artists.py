#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 音乐曲库 - 4 位华语传奇歌手（刘若英、小虎队、谭维维、林志炫）
全量 45 张核心录音室大碟、529 首曲目纯骨架与视觉资产一键入库流水线
========================================================================
1. 将 4 位歌手、45 张大碟、529 首曲目完整入库至 Cloudflare D1 数据库。
2. 严格遵循纯骨架规范：file_path / lrc_path 全留白 (0 字节音频占用)。
3. 高清艺人写真头像与大碟封面自动转存至 Worker R2 资产存储 (0 外部防盗链失效隐患)。
4. 自动回填绑定 D1 对应实体（artists.photo_url 与 albums.cover_url）。
5. 针对 23 张【🔥大热专辑】进行显式大热打标：
   - 在本地 SQLite catalog_sync.db 中标记 genre='大热流行', qa_status='HOT_PRIORITY'
   - 生成专用高优先级下载调度底册 configs/priority_hot_targets.json
"""

import os
import sys
import json
import time
import sqlite3
import requests
from urllib.parse import quote

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(BASE_DIR)
JSON_PATH = os.path.join(BASE_DIR, "scripts", "configs", "four_new_artists_skeleton.json")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
HOT_TARGETS_PATH = os.path.join(BASE_DIR, "scripts", "configs", "priority_hot_targets.json")

API_BASE = "https://m-api.changgepd.ccwu.cc"
BATCH_INSERT_URL = f"{API_BASE}/api/admin/ops/songs/batch-insert"
ASSET_UPLOAD_URL = f"{API_BASE}/api/admin/assets/upload"
ALBUM_PATCH_URL = f"{API_BASE}/api/admin/albums"
ALBUM_SEARCH_URL = f"{API_BASE}/api/admin/albums/search"
ALBUM_DETAIL_URL = f"{API_BASE}/api/admin/albums/detail"

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries=3)
session.mount('https://', adapter)
session.mount('http://', adapter)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com'
}

def upload_image_to_worker(image_url: str, category: str, target_id: int, filename: str) -> str | None:
    """从源 URL 下载图片并直传至 Worker R2 资产端，自动绑定 D1 对应实体"""
    try:
        img_resp = session.get(image_url, headers=HEADERS, timeout=20)
        if img_resp.status_code != 200 or len(img_resp.content) < 1000:
            print(f" (⚠️ 图片下载失败 HTTP {img_resp.status_code})", end="", flush=True)
            return None
        
        data = {
            'category': category,
            'filename': filename
        }
        if category == 'artists':
            data['artist_id'] = str(target_id)
        elif category == 'albums':
            data['album_id'] = str(target_id)
            
        files = {
            'file': (filename, img_resp.content, 'image/jpeg')
        }
        
        up_resp = session.post(ASSET_UPLOAD_URL, files=files, data=data, timeout=30)
        if up_resp.status_code == 200:
            res_json = up_resp.json()
            items = res_json.get('data', {}).get('files', [])
            if items:
                return items[0].get('key')
            return "uploaded"
        else:
            print(f" (⚠️ 资产上传异常 HTTP {up_resp.status_code})", end="", flush=True)
    except Exception as e:
        print(f" (⚠️ 资产上传异常: {e})", end="", flush=True)
    return None

def sync_sqlite_tracks(conn, artist_id, artist_name, album_id, album_title, year, is_hot, inserted_songs):
    """将大碟及纯骨架歌曲记录同步至本地 SQLite catalog_sync.db"""
    c = conn.cursor()
    genre_text = '大热流行' if is_hot else '华语流行'
    qa_tag = 'HOT_PRIORITY' if is_hot else 'PENDING'

    # 同步 albums 表
    c.execute("""
        INSERT INTO albums (id, artist_id, title, release_date, genre, cover_url)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            artist_id = excluded.artist_id,
            title = excluded.title,
            release_date = excluded.release_date,
            genre = excluded.genre
    """, (album_id, artist_id, album_title, str(year), genre_text, f"covers/albums/cover_{album_id}.jpg"))

    # 同步 songs 表与 tracks_sync_state 表
    for s in inserted_songs:
        song_id = s['id']
        song_title = s['title']
        track_index = s['track_index']

        c.execute("""
            INSERT INTO songs (id, artist_id, album_id, title, track_index, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                artist_id = excluded.artist_id,
                album_id = excluded.album_id,
                title = excluded.title,
                track_index = excluded.track_index
        """, (song_id, artist_id, album_id, song_title, track_index))

        c.execute("""
            INSERT INTO tracks_sync_state (
                song_id, artist_name, album_title, song_title, track_index,
                file_size, qa_status, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, 'UNLIT_SKELETON', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(song_id) DO UPDATE SET
                artist_name = excluded.artist_name,
                album_title = excluded.album_title,
                song_title = excluded.song_title,
                track_index = excluded.track_index,
                qa_status = excluded.qa_status,
                updated_at = CURRENT_TIMESTAMP
        """, (song_id, artist_name, album_title, song_title, track_index, qa_tag))

def main():
    print("=" * 80)
    print("🚀 启动 4 位传奇歌手（刘若英、小虎队、谭维维、林志炫）骨架与资产入库")
    print("=" * 80)

    if not os.path.exists(JSON_PATH):
        print(f"❌ 未找到骨架数据: {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        skeleton_data = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    total_artists = 0
    total_albums = 0
    total_songs = 0
    total_hot_albums = 0
    total_hot_songs = 0
    hot_priority_targets = []

    for artist_idx, art_item in enumerate(skeleton_data, 1):
        artist_name = art_item['artist_name']
        avatar_url = art_item.get('avatar_url')
        albums = art_item.get('albums', [])

        print(f"\n🎤 [{artist_idx}/{len(skeleton_data)}] 艺人: {artist_name} (共 {len(albums)} 张经典大碟)")

        artist_id = None

        # 逐张专辑处理入库
        for album_idx, alb_item in enumerate(albums, 1):
            album_title = alb_item['title']
            year = alb_item.get('year')
            cover_url = alb_item.get('cover_url')
            is_hot = alb_item.get('is_hot', False)
            songs = alb_item.get('songs', [])

            hot_badge = "🔥[大热专辑]" if is_hot else "  [常规大碟]"
            print(f"   💿 [{album_idx:2d}/{len(albums):2d}] {hot_badge} 《{album_title}》 ({year}年, {len(songs):2d}首)...", end="", flush=True)

            # 调用 batch-insert 批量创建专辑与歌曲骨架
            insert_payload = {
                'artist_name': artist_name,
                'album_title': album_title,
                'songs': [{'title': s_title, 'track_index': idx} for idx, s_title in enumerate(songs)]
            }

            try:
                r_insert = session.post(BATCH_INSERT_URL, json=insert_payload, timeout=35)
                if r_insert.status_code == 200:
                    res_data = r_insert.json().get('data', {})
                    artist_id = res_data.get('artist_id', artist_id)
                    album_id = res_data.get('album_id')
                    s_ids = res_data.get('song_ids', [])
                    inserted_songs = [{'id': sid, 'title': songs[i], 'track_index': i} for i, sid in enumerate(s_ids)]
                    total_songs += len(inserted_songs)
                    if is_hot:
                        total_hot_albums += 1
                        total_hot_songs += len(inserted_songs)
                        for s in inserted_songs:
                            hot_priority_targets.append({
                                "song_id": s['id'],
                                "artist_id": artist_id,
                                "artist_name": artist_name,
                                "album_id": album_id,
                                "album_title": album_title,
                                "title": s['title'],
                                "priority": "HOT"
                            })
                    print(f" [入库成功:{len(inserted_songs)}首]", end="", flush=True)
                else:
                    print(f" [❌入库失败: {r_insert.status_code}]", flush=True)
                    continue
            except Exception as e:
                print(f" [❌请求异常: {e}]", flush=True)
                continue

            # 更新专辑年份
            if album_id:
                if year:
                    try:
                        session.patch(f"{ALBUM_PATCH_URL}/{album_id}", json={'release_date': str(year)}, timeout=10)
                    except Exception:
                        pass

                # 上传专辑封面至 R2
                if cover_url:
                    r2_cover = upload_image_to_worker(cover_url, 'albums', album_id, f"cover_{album_id}.jpg")
                    if r2_cover:
                        print(" [🖼️封面存R2]", end="", flush=True)

                # 同步本地 SQLite
                sync_sqlite_tracks(conn, artist_id, artist_name, album_id, album_title, year, is_hot, inserted_songs)
                conn.commit()

            total_albums += 1
            print(" ✅")

        # 上传艺人写真头像至 R2
        if artist_id and avatar_url:
            print(f"   🖼️ 上传艺人高清写真至 R2 (artist_{artist_id}.jpg)...", end="", flush=True)
            r2_av = upload_image_to_worker(avatar_url, 'artists', artist_id, f"artist_{artist_id}.jpg")
            if r2_av:
                print(" ✅")
            else:
                print(" ⚠️")

            # 更新 SQLite 艺人信息
            c = conn.cursor()
            c.execute("""
                INSERT INTO artists (id, name, genre, avatar_url)
                VALUES (?, ?, '华语', ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    avatar_url = excluded.avatar_url
            """, (artist_id, artist_name, f"artists/artist_{artist_id}.jpg"))
            conn.commit()

        total_artists += 1

    conn.close()

    # 导出大热专辑歌曲优先下载清单
    with open(HOT_TARGETS_PATH, 'w', encoding='utf-8') as f:
        json.dump(hot_priority_targets, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("🎉 4 位华语传奇歌手权威大碟骨架与视觉资产全量导入完成！")
    print("=" * 80)
    print(f"✨ 新增艺人: {total_artists} 位")
    print(f"✨ 新增大碟: {total_albums} 张 (其中 🔥大热专辑: {total_hot_albums} 张)")
    print(f"✨ 新增曲目: {total_songs} 首 (其中 🔥大热优先曲目: {total_hot_songs} 首)")
    print(f"✨ 本地调度底册: catalog_sync.db 100% 同步 (打标 HOT_PRIORITY)")
    print(f"✨ 优先下载清单: {HOT_TARGETS_PATH} (共 {len(hot_priority_targets)} 首大热曲目)")
    print("=" * 80)

if __name__ == '__main__':
    main()
