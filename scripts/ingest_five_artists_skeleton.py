#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 音乐曲库 - 5 位经典歌手（迪克牛仔、零点乐队、曾轶可、郑智化、萧煌奇）
纯骨架与视觉资产一键入库流水线
========================================================================
1. 将 5 位歌手、44 张经典大碟、458 首曲目完整入库至 Cloudflare D1 数据库。
2. 严格遵循纯骨架规范：file_path / lrc_path 全留白 (0 字节音频占用)。
3. 高清艺人头像与大碟封面自动转存至 Worker R2 资产存储 (0 外部防盗链失效隐患)。
4. 自动回填绑定 D1 对应实体（artists.photo_url 与 albums.cover_url）。
"""

import os
import sys
import json
import time
import requests
from urllib.parse import quote

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "scripts", "configs", "five_artists_skeleton.json")

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
    'Referer': 'https://y.qq.com'
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
            items = res_json.get('data', {}).get('results', [])
            if items:
                return items[0].get('key')
        else:
            print(f" (⚠️ 资产上传异常 HTTP {up_resp.status_code})", end="", flush=True)
    except Exception as e:
        print(f" (⚠️ 资产上传异常: {e})", end="", flush=True)
    return None

def main():
    print("=" * 80)
    print("🚀 启动 5 位经典歌手（迪克牛仔、零点乐队、曾轶可、郑智化、萧煌奇）骨架入库")
    print("=" * 80)

    if not os.path.exists(JSON_PATH):
        print(f"❌ 未找到骨架配置文件: {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        skeleton_data = json.load(f)

    print(f"📦 已加载骨架清单: 共 {len(skeleton_data)} 位艺人")

    total_artists_processed = 0
    total_albums_processed = 0
    total_songs_processed = 0
    total_covers_uploaded = 0
    total_avatars_uploaded = 0

    for artist_idx, artist_item in enumerate(skeleton_data, 1):
        artist_name = artist_item['artist_name']
        avatar_url = artist_item.get('avatar_url')
        albums = artist_item.get('albums', [])

        print(f"\n🎤 [{artist_idx}/{len(skeleton_data)}] 艺人: {artist_name} (共 {len(albums)} 张经典大碟)")

        artist_id = None

        # 逐张专辑入库
        for album_idx, alb_item in enumerate(albums, 1):
            album_title = alb_item['title']
            year = alb_item.get('year')
            cover_url = alb_item.get('cover_url')
            songs = alb_item.get('songs', [])

            print(f"   💿 [{album_idx:2d}/{len(albums):2d}] 《{album_title}》 ({year}年, {len(songs):2d}首)...", end="", flush=True)

            # 调用 batch-insert 批量创建专辑与歌曲
            insert_payload = {
                'artist_name': artist_name,
                'album_title': album_title,
                'songs': [{'title': s_title, 'track_index': idx} for idx, s_title in enumerate(songs)]
            }
            
            try:
                r_insert = session.post(BATCH_INSERT_URL, json=insert_payload, timeout=30)
                if r_insert.status_code == 200:
                    res_data = r_insert.json().get('data', {})
                    artist_id = res_data.get('artist_id', artist_id)
                    album_id = res_data.get('album_id')
                    s_ids = res_data.get('song_ids', [])
                    total_songs_processed += len(songs)
                    print(f" [入库成功]", end="", flush=True)
                else:
                    print(f" [❌入库失败: {r_insert.status_code} {r_insert.text}]", flush=True)
                    continue
            except Exception as e:
                print(f" [❌请求异常: {e}]", flush=True)
                continue

            # 更新专辑发行年份与封面
            if album_id:
                if year:
                    try:
                        session.patch(f"{ALBUM_PATCH_URL}/{album_id}", json={'release_date': str(year)}, timeout=10)
                    except Exception:
                        pass

                if cover_url:
                    r2_cover = upload_image_to_worker(cover_url, 'albums', album_id, f"cover_{album_id}.jpg")
                    if r2_cover:
                        total_covers_uploaded += 1
                        print(" [🖼️封面转存成功]", end="", flush=True)

            total_albums_processed += 1
            print(" ✅")

        # 补齐/上传艺人高清写真头像
        if artist_id and avatar_url:
            print(f"   🖼️ 上传艺人高清头像至 R2 (artist_{artist_id}.jpg)...", end="", flush=True)
            r2_av = upload_image_to_worker(avatar_url, 'artists', artist_id, f"artist_{artist_id}.jpg")
            if r2_av:
                total_avatars_uploaded += 1
                print(" ✅")
            else:
                print(" ⚠️")

        total_artists_processed += 1

    print("\n" + "=" * 80)
    print("🎉 5 位经典歌手权威录音室大碟骨架与视觉资产全量导入完成！")
    print("=" * 80)
    print(f"✨ 新增艺人: {total_artists_processed} 位")
    print(f"✨ 新增大碟: {total_albums_processed} 张")
    print(f"✨ 新增曲目: {total_songs_processed} 首 (纯骨架 0 字节音频占用)")
    print(f"✨ 转存封面: {total_covers_uploaded} 张 (直存 R2 covers/albums/)")
    print(f"✨ 转存头像: {total_avatars_uploaded} 张 (直存 R2 artists/)")
    print("=" * 80)

if __name__ == '__main__':
    main()
