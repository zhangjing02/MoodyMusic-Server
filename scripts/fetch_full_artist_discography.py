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

# 4 位歌手的 163 ID
# 刘若英: 8326
# 小虎队: 13286
# 谭维维: 9489
# 林志炫: 3692
artists = [
    {"name": "刘若英", "id": 8326},
    {"name": "小虎队", "id": 13286},
    {"name": "谭维维", "id": 9489},
    {"name": "林志炫", "id": 3692}
]

for art in artists:
    url = f"http://music.163.com/api/artist/albums/{art['id']}?offset=0&limit=50"
    r = requests.get(url, headers=headers, timeout=10).json()
    hot_albums = r.get('hotAlbums', [])
    print(f"\n==================== 艺人: {art['name']} (共找到 {len(hot_albums)} 张专辑) ====================")
    for idx, alb in enumerate(hot_albums, 1):
        alb_id = alb.get('id')
        name = alb.get('name')
        publish_time = alb.get('publishTime')
        year = time.gmtime(publish_time / 1000).tm_year if publish_time else "未知"
        size = alb.get('size')
        sub_type = alb.get('subType')
        alb_type = alb.get('type')
        print(f"[{idx:2d}] {year} 《{name}》 (ID: {alb_id}, 歌曲数: {size}, 类型: {alb_type}/{sub_type})")
