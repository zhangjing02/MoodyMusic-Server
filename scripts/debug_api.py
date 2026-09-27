import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://m-api.changgepd.ccwu.cc/api/songs?artistId=15&artist=%E9%82%93%E4%B8%BD%E5%90%9B'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print('Code:', data.get('code'))
        if data.get('data') and len(data['data']) > 0:
            artist = data['data'][0]
            print('Artist Name:', artist.get('name'))
            albums = artist.get('albums', [])
            print('Albums count in response:', len(albums))
            for i, alb in enumerate(albums[:20]):
                songs = alb.get('songs', [])
                lit = sum(1 for s in songs if s.get('path'))
                print(f"{i+1}. {alb.get('title')} ({alb.get('year')}) - {len(songs)} songs, lit={lit}")
            all_songs = [s for alb in albums for s in alb.get('songs', [])]
            lit_total = sum(1 for s in all_songs if s.get('path'))
            print('Total songs returned:', len(all_songs), 'Total lit songs in response:', lit_total)
except Exception as e:
    print('Error:', e)
