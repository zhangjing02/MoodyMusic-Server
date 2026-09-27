import requests

for aid in [23103, 92138448]:
    r = requests.get(f'https://music.163.com/api/v1/album/{aid}', headers={'User-Agent': 'Mozilla/5.0'}).json()
    album = r.get('album', {})
    print(f"=== Album: {album.get('name')} (ID: {aid}, Size: {len(r.get('songs', []))}) ===")
    print(f"PicUrl: {album.get('picUrl')}")
    for idx, s in enumerate(r.get('songs', [])[:12], 1):
        sid = s.get('id')
        dt = (s.get('dt') or 0) // 1000
        resp = requests.head(f'https://music.163.com/song/media/outer/url?id={sid}.mp3', headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
        sz = int(resp.headers.get('Content-Length', '0'))
        print(f"  {idx:02d}. {s.get('name'):15s} ({dt}s) [ID: {sid}] -> Stream: {resp.status_code} ({sz} bytes)")
