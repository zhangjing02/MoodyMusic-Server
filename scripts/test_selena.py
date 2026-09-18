import sys
import requests
import json
import urllib.parse
import syncedlyrics

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)',
    'Referer': 'https://music.163.com/',
}

# 1. NetEase search
for q in ["动力火车 Selena", "Selena 动力火车", "动力火车 忠孝东路走九遍 Selena"]:
    url = f"http://music.163.com/api/search/get/web?s={urllib.parse.quote(q)}&type=1&offset=0&limit=5"
    r = requests.get(url, headers=headers).json()
    songs = r.get('result', {}).get('songs', [])
    print(f"Query '{q}': found {len(songs)} songs")
    for s in songs:
        name = s['name']
        art = ", ".join([a['name'] for a in s.get('artists', [])])
        alb = s.get('album', {}).get('name')
        sid = s['id']
        print(f"  {sid}: {art} - {name} ({alb})")
        # Check lyric
        lr = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1", headers=headers).json()
        lrc = lr.get('lrc', {}).get('lyric')
        print(f"    Lrc length: {len(lrc) if lrc else 0}")
