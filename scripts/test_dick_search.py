import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

def test_search(artist, song):
    print(f"\n==================== Searching: {artist} - {song} ====================")
    # 1. Kuwo
    url_kw = f"http://search.kuwo.cn/r.s?client=kt&all={artist}+{song}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=5"
    try:
        r = requests.get(url_kw, timeout=5)
        text = r.text.replace("'", '"')
        d = json.loads(text)
        print("Kuwo:")
        for item in d.get('abslist', [])[:3]:
            print(f"  • {item.get('ARTIST')} - {item.get('SONGNAME')} (Album: {item.get('ALBUM')}) [RID: {item.get('DC_TARGETID')}]")
    except Exception as e:
        print("Kuwo error:", e)

    # 2. NetEase
    url_ne = f"https://music.163.com/api/search/get/web?s={artist}+{song}&type=1&limit=5"
    try:
        r = requests.get(url_ne, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        songs = r.json().get('result', {}).get('songs', [])
        print("NetEase:")
        for s in songs[:3]:
            arts = ', '.join([a.get('name') for a in s.get('artists', [])])
            print(f"  • {arts} - {s.get('name')} (Album: {s.get('album', {}).get('name')}) [ID: {s.get('id')}]")
    except Exception as e:
        print("NetEase error:", e)

songs_to_test = ['爱如潮水', '酒干倘卖无', '哭不出来', '梦醒时分', '吻别', '一言难尽']
for s in songs_to_test:
    test_search('迪克牛仔', s)
