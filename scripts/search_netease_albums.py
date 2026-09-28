import urllib.request
import urllib.parse
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def search_album(name):
    url = f'https://music.163.com/api/search/get/web?csrf_token=hlpretag=&hlposttag=&s={urllib.parse.quote(name)}&type=10&offset=0&total=true&limit=3'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            albums = data.get('result', {}).get('albums', [])
            for a in albums:
                print(f"Album: {a.get('name')} | ID: {a.get('id')} | Artist: {a.get('artist', {}).get('name')} | Size: {a.get('size')} | Pic: {a.get('picUrl')}")
    except Exception as e:
        print(f"Error searching {name}: {e}")

if __name__ == '__main__':
    search_album('江美琪 再一次也好')
    search_album('江美琪 朋友的朋友')
    search_album('江美琪 恋人心中有一首诗')
    search_album('江美琪 爱哭鬼')
    search_album('江美琪 房间')
    search_album('江美琪 我们都是有歌的人')
    search_album('江美琪 圆的')
