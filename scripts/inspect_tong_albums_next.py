import requests

def inspect_album(keyword):
    print(f"=== Search Album: {keyword} ===")
    url = "https://music.163.com/api/search/get/web"
    params = {'s': f"童安格 {keyword}", 'type': 10, 'limit': 3}
    r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}).json()
    albums = r.get('result', {}).get('albums', [])
    for a in albums:
        aid = a['id']
        name = a['name']
        sz = a['size']
        print(f"Album: {name} (ID: {aid}, Size: {sz})")
        r_det = requests.get(f"https://music.163.com/api/v1/album/{aid}", headers={'User-Agent': 'Mozilla/5.0'}).json()
        songs = r_det.get('songs', [])
        for idx, s in enumerate(songs, 1):
            sid = s['id']
            sname = s['name']
            dt = (s.get('dt') or 0) // 1000
            print(f"  {idx:02d}. {sname} ({dt}s) [ID: {sid}]")

if __name__ == '__main__':
    inspect_album("一世情缘")
    inspect_album("爱与哀愁")
