import requests

tracks = [
    ('春在岁岁年年', 229721, 189),
    ('奈何', 229723, 164),
    ('伊人何处', 229724, 206),
    ('告诉你告诉我', 229725, 195),
    ('心事知多少', 229727, 165),
    ('你怎么说', 229729, 202),
    ('在水一方', 229731, 225),
    ('小小的秘密', 229733, 204),
    ('星月泪痕', 229735, 172),
    ('艳红小曲', 229737, 74),
    ('妈妈呼唤你', 229739, 227),
    ('让心儿圈起你', 229741, 221)
]

for t, orig_id, exp_dur in tracks:
    # 检查原始 ID
    url = f"https://music.163.com/song/media/outer/url?id={orig_id}.mp3"
    r = requests.head(url, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
    sz = int(r.headers.get('Content-Length', '0'))
    if sz > 1000000:
        print(f"✅ {t:12s} (Orig ID: {orig_id}) -> {sz} bytes")
        continue
    
    # 搜索其他版本
    search_url = "https://music.163.com/api/search/get/web"
    sr = requests.get(search_url, params={'s': f"邓丽君 {t}", 'type': 1, 'limit': 5}, headers={'User-Agent': 'Mozilla/5.0'}).json()
    songs = sr.get('result', {}).get('songs', [])
    found = False
    for s in songs:
        sid = s['id']
        dur = s.get('duration', 0) // 1000
        if abs(dur - exp_dur) <= 5: # 时长匹配录音室母带
            resp = requests.head(f"https://music.163.com/song/media/outer/url?id={sid}.mp3", headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
            ssz = int(resp.headers.get('Content-Length', '0'))
            if ssz > 1000000:
                print(f"🔍 {t:12s} (Alt ID: {sid}) -> {ssz} bytes, dur: {dur}s, album: {s.get('album', {}).get('name')}")
                found = True
                break
    if not found:
        print(f"❌ {t:12s} -> Need YouTube fallback (exp: {exp_dur}s)")
