import requests
import sys
import json
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8')
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
q = '梁静茹 我和自己的约会'
url = f'http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={urllib.parse.quote(q)}&page=1&pagesize=10'
r = requests.get(url, headers=headers, timeout=5)
if r.ok:
    info = r.json().get('data', {}).get('info', [])
    for s in info:
        songname = s.get('songname')
        singer = s.get('singername')
        album = s.get('album_name')
        dur = s.get('duration')
        h = s.get('hash')
        print(f"{songname} | {singer} | {album} | {dur}s | {h}")
