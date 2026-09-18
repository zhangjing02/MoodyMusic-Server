import requests
import json
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

test_artists = ['告五人', '草东没有派对', '郑钧']

for name in test_artists:
    print(f'=== Testing: {name} ===')
    r = requests.get('http://music.163.com/api/search/get/web?s=' + requests.utils.quote(name) + '&type=100', timeout=5).json()
    artists = r.get('result', {}).get('artists', [])
    if not artists:
        print('  Not found')
        continue
    a = artists[0]
    aid = a['id']
    avatar = a.get('picUrl')
    print(f"  Artist: {a.get('name')} (ID: {aid})")
    print(f"  Avatar: {avatar}")
    
    r_albs = requests.get(f'http://music.163.com/api/artist/albums/{aid}?offset=0&limit=20', timeout=5).json()
    albs = r_albs.get('hotAlbums', [])
    for alb in albs:
        albid = alb['id']
        alb_name = alb['name']
        cover = alb.get('picUrl')
        pub_year = str(time.gmtime(alb.get('publishTime', 0) / 1000).tm_year) if alb.get('publishTime') else ''
        size = alb.get('size', 0)
        # 过滤纯单曲/Live/伴奏
        if size >= 5 and '伴奏' not in alb_name and '演唱会' not in alb_name and 'Live' not in alb_name:
            print(f"    💿 Album: 《{alb_name}》 ({pub_year}) | Tracks: {size} | Cover: {cover[:60]}...")
            r_detail = requests.get(f'http://music.163.com/api/album/{albid}', timeout=5).json()
            songs = r_detail.get('album', {}).get('songs', [])
            for i, s in enumerate(songs[:4]):
                print(f"       {i+1}. {s.get('name')}")
            if len(songs) > 4:
                print(f"       ... and {len(songs)-4} more tracks")
