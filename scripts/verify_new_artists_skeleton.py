# -*- coding: utf-8 -*-
import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

api_base = 'https://m-api.changgepd.ccwu.cc'
r = requests.get(f'{api_base}/api/skeleton', timeout=15).json()
artists = r.get('data', {}).get('artists', [])

target_names = ['刘若英', '小虎队', '谭维维', '林志炫']
print("=== 4 位新歌手在 D1 骨架验证 ===")
for a in artists:
    if a.get('name') in target_names:
        print(f"艺人: {a.get('name'):<6} ID: {a.get('id'):<8} 大碟数: {a.get('albumCount'):<4} 头像: {a.get('avatar')}")
        # 探活头像
# 抽验一张大热专辑曲目
rene_albs = requests.get(f'{api_base}/api/admin/albums/search?artist_id=162').json().get('data', {}).get('albums', [])
if rene_albs:
    sample_alb = rene_albs[3]
    print(f"\n[刘若英样本专辑] 《{sample_alb.get('title')}》 ID: {sample_alb.get('id')}, Cover: {sample_alb.get('cover_url')}")
    detail = requests.get(f'{api_base}/api/admin/albums/detail?album_id={sample_alb.get("id")}').json().get('data', {})
    print(f"歌曲总数: {len(detail.get('songs', []))}")
    for s in detail.get('songs', [])[:5]:
        print(f"  - {s.get('track_index')}: {s.get('title')}")

