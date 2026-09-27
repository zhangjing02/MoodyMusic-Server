import requests

for aid, name in [(15209, '一世情缘'), (15207, '爱与哀愁')]:
    r = requests.get(f'https://music.163.com/api/v1/album/{aid}', headers={'User-Agent': 'Mozilla/5.0'}).json()
    songs = r.get('songs', [])
    print(f'=== {name} ({len(songs)} tracks) ===')
    for s in songs:
        sid = s['id']
        sname = s['name']
        url = f'https://music.163.com/song/media/outer/url?id={sid}.mp3'
        resp = requests.head(url, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
        print(f"  {sname:15s} ({sid}) -> {resp.status_code} | {resp.headers.get('Content-Length', '0')} B")
