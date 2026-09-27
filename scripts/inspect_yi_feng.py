import requests

r = requests.get('https://music.163.com/api/v1/album/489715', headers={'User-Agent': 'Mozilla/5.0'}).json()
album = r.get('album', {})
print('Album:', album.get('name'))
print('PicUrl:', album.get('picUrl'))
songs = r.get('songs', [])
for idx, s in enumerate(songs, 1):
    sid = s.get('id')
    sname = s.get('name')
    dt = (s.get('dt') or 0) // 1000
    url = f'https://music.163.com/song/media/outer/url?id={sid}.mp3'
    resp = requests.head(url, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
    cl = resp.headers.get('Content-Length', '0')
    print(f"  {idx:02d}. {sname:15s} (ID: {sid}) | Dur: {dt}s | Stream: {resp.status_code} ({cl} B)")
