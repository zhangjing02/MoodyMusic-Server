import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'NeteaseMusic/9.0.90 (iPhone; iOS 16.5; Scale/3.00)'}

albums = [
    (24831, "把耳朵叫醒", 1999),
    (24830, "那么骄傲", 2000),
]

for nid, title, year in albums:
    res = requests.get(f'https://music.163.com/api/v1/album/{nid}', headers=headers).json()
    songs = res.get('songs', [])
    pic = res.get('album', {}).get('picUrl', '')
    print(f"=== {title} ({year}, NID: {nid}) ===")
    print(f"Cover: {pic}")
    print(f"Total songs: {len(songs)}")
    for i, s in enumerate(songs, 1):
        dt = (s.get('dt') or 0) // 1000
        print(f"  {i}. [{s['id']}] {s['name']} ({dt}s)")
