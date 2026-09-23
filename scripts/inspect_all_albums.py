# -*- coding: utf-8 -*-
import requests
import json
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/'
}

def get_all_albums(artist_id):
    offset = 0
    all_albums = []
    while True:
        url = f"http://music.163.com/api/artist/albums/{artist_id}?offset={offset}&limit=50"
        r = requests.get(url, headers=headers, timeout=10).json()
        hot = r.get('hotAlbums', [])
        if not hot:
            break
        all_albums.extend(hot)
        if not r.get('more'):
            break
        offset += 50
    return all_albums

# 打印刘若英的所有专辑
print("=== 刘若英全量专辑 ===")
rene_albs = get_all_albums(8326)
for a in rene_albs:
    t = a.get('publishTime')
    y = time.gmtime(t/1000).tm_year if t else 0
    print(f"{y} 《{a.get('name')}》 (size={a.get('size')}, id={a.get('id')}, type={a.get('type')})")

print("\n=== 小虎队全量专辑 ===")
tiger_albs = get_all_albums(13286)
for a in tiger_albs:
    t = a.get('publishTime')
    y = time.gmtime(t/1000).tm_year if t else 0
    print(f"{y} 《{a.get('name')}》 (size={a.get('size')}, id={a.get('id')}, type={a.get('type')})")

print("\n=== 谭维维全量专辑 ===")
tan_albs = get_all_albums(9489)
for a in tan_albs:
    t = a.get('publishTime')
    y = time.gmtime(t/1000).tm_year if t else 0
    # 过滤单曲只有 1-2 首的，主要找录音室大碟
    if a.get('size') >= 4 or a.get('type') in ['专辑', 'EP']:
        print(f"{y} 《{a.get('name')}》 (size={a.get('size')}, id={a.get('id')}, type={a.get('type')})")
