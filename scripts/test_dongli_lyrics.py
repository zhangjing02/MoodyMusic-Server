import sys
import syncedlyrics
import requests
import json
import base64

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def search_kugou_lrc(artist: str, title: str):
    keyword = f"{artist} - {title}"
    url = f"http://lyrics.kugou.com/search?ver=1&man=yes&client=pc&keyword={requests.utils.quote(keyword)}&duration=&hash="
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            candidates = r.json().get('candidates', [])
            if candidates:
                cand = candidates[0]
                cand_id = cand['id']
                accesskey = cand['accesskey']
                down_url = f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cand_id}&accesskey={accesskey}&fmt=lrc&charset=utf8"
                dr = requests.get(down_url, timeout=5)
                if dr.status_code == 200:
                    content_b64 = dr.json().get('content', '')
                    if content_b64:
                        return base64.b64decode(content_b64).decode('utf-8', errors='replace')
    except Exception as e:
        # print("Kugou err:", e)
        pass
    return None

songs = [
    (25718, '动力火车', '忠孝东路走九遍', '酒醉的探戈2001'),
    (25719, '动力火车', '忠孝东路走九遍', '忠孝东路走九遍'),
    (25720, '动力火车', '忠孝东路走九遍', '我若不曾爱过你'),
    (25721, '动力火车', '忠孝东路走九遍', '寄生人'),
    (25722, '动力火车', '忠孝东路走九遍', '乱乱的'),
    (25723, '动力火车', '忠孝东路走九遍', '酒醉的探戈'),
    (25724, '动力火车', '忠孝东路走九遍', '回家'),
    (25725, '动力火车', '忠孝东路走九遍', 'Selena'),
    (25726, '动力火车', '忠孝东路走九遍', '管你嫁给谁'),
    (25727, '动力火车', '忠孝东路走九遍', '好吧')
]

for sid, art, alb, tit in songs:
    print(f"Testing {art} - {tit}...")
    lrc = None
    try:
        lrc = syncedlyrics.search(f"{art} {tit}", providers=['NetEase', 'Lrclib'])
    except Exception as e:
        print("syncedlyrics err:", e)
    if not lrc:
        print("Fallback to Kugou...")
        lrc = search_kugou_lrc(art, tit)
    if lrc:
        first_line = [line for line in lrc.splitlines() if line.strip() and '[' in line][:2]
        print(f"  -> SUCCESS! Lines: {len(lrc.splitlines())}, Preview: {first_line}")
    else:
        print("  -> FAILED!")
