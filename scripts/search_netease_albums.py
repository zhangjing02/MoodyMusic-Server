import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
headers = {'User-Agent': 'Mozilla/5.0'}

# 1. 查卢广仲网易云歌手页的所有专辑
artist_id = 3690 # 卢广仲网易云歌手 ID
r = requests.get(f"https://music.163.com/api/artist/albums/{artist_id}?offset=0&limit=50", headers=headers).json()
hotAlbums = r.get('hotAlbums', [])
print(f"Total hotAlbums for 卢广仲: {len(hotAlbums)}")
for a in hotAlbums:
    print(f"ID: {a['id']} | 《{a['name']}》 | 歌曲数: {a['size']} | 类型: {a.get('type')}")
