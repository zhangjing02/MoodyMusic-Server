import sys
import json
import subprocess

sys.stdout.reconfigure(encoding='utf-8')

def curl_get(url):
    res = subprocess.run(['curl.exe', '-s', '--noproxy', '*', url], capture_output=True, text=True, encoding='utf-8')
    return json.loads(res.stdout)

skel = curl_get('https://m-api.changgepd.ccwu.cc/api/skeleton')
artists = skel.get('data', {}).get('artists', [])
dick_id = None
for a in artists:
    if a['name'] == '迪克牛仔':
        dick_id = a['id']
        break

print(f"迪克牛仔 Artist ID: {dick_id}")
songs_resp = curl_get(f'https://m-api.changgepd.ccwu.cc/api/songs?artistId={dick_id}')
data = songs_resp.get('data', [])

all_dick_songs = []
for art in data:
    for alb in art.get('albums', []):
        alb_title = alb.get('title')
        print(f"\n=== 《{alb_title}》 ({len(alb.get('songs', []))} 首) ===")
        for s in alb.get('songs', []):
            sid = s.get('id')
            title = s.get('title')
            path = s.get('path')
            lrc = s.get('lrc_path')
            all_dick_songs.append({
                'id': sid,
                'album': alb_title,
                'title': title,
                'path': path,
                'lrc': lrc
            })
            print(f"  • [{s.get('TrackIndex')}] {title} (ID: {sid}) -> {path}")

with open('scratch/dick_cowboy_all_songs.json', 'w', encoding='utf-8') as f:
    json.dump(all_dick_songs, f, ensure_ascii=False, indent=2)

print(f"\nTotal 迪克牛仔 songs: {len(all_dick_songs)}")
