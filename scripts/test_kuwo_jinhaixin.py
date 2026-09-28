import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

def test_kuwo(song_name):
    q = f"金海心 {song_name}"
    url = f"http://search.kuwo.cn/r.s?client=kt&all={q}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=5"
    r = requests.get(url, timeout=5)
    # kuwo json might have single quotes or unescaped characters
    text = r.text.replace("'", '"')
    d = json.loads(text)
    for item in d.get('abslist', []):
        rid = item.get('DC_TARGETID', '')
        art = item.get('ARTIST', '')
        alb = item.get('ALBUM', '')
        tit = item.get('SONGNAME', '')
        dur = item.get('DURATION', 0)
        anti = f"http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={rid}&format=mp3&response=url"
        play_url = requests.get(anti, timeout=5).text.strip()
        print(f"[{tit}] - {art} - 《{alb}》 ({dur}s) | RID: {rid} | URL: {play_url[:60]}")
        return play_url

tracks = [
    '送别', '天涯歌女', '我们的生活充满阳光', '乡恋', '牡丹之歌',
    '牧羊曲', '歌声与微笑', '月圆花好', '让我们荡起双桨', '小白船', '同一首歌'
]

for t in tracks:
    test_kuwo(t)




