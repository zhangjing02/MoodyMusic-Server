import requests

keywords = ['邓丽君 小城故事', '邓丽君 甜蜜蜜', '邓丽君 在水一方', '邓丽君 淡淡幽情']
for q in keywords:
    r = requests.get('https://music.163.com/api/search/get/web', params={'s': q, 'type': 10, 'limit': 3}, headers={'User-Agent': 'Mozilla/5.0'}).json()
    albums = r.get('result', {}).get('albums', [])
    print(f"=== {q} ===")
    for a in albums:
        aid = a['id']
        name = a['name']
        sz = a['size']
        pub = a.get('publishTime')
        print(f"  ID: {aid} | Name: {name} | Size: {sz} | Pub: {pub}")
