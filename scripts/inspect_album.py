import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

album_id = sys.argv[1] if len(sys.argv) > 1 else '24805'
url = f'http://music.163.com/api/v1/album/{album_id}'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://music.163.com/'})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        album = data.get('album', {})
        songs = data.get('songs', album.get('songs', []))
        print(f"Album: {album.get('name')} | Artist: {album.get('artist', {}).get('name')}")
        print(f"Cover: {album.get('picUrl')}")
        print(f"Songs count: {len(songs)}")
        for s in songs:
            print(f"{s.get('id')} | {s.get('name')}")
except Exception as e:
    print(f"Error: {e}")
