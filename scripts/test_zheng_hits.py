import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

def test_zheng(tit):
    url = f"http://search.kuwo.cn/r.s?client=kt&all=郑智化+{tit}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=5"
    r = requests.get(url, timeout=5)
    d = json.loads(r.text.replace("'", '"'))
    print(f"\n=== 郑智化 《{tit}》 in Kuwo ===")
    for item in d.get('abslist', [])[:3]:
        art = item.get('ARTIST')
        name = item.get('SONGNAME')
        alb = item.get('ALBUM')
        dur = item.get('DURATION')
        rid = item.get('DC_TARGETID')
        print(f"  • {art} - {name} | Album: {alb} | {dur}s | RID: {rid}")

for t in ['别哭，我最爱的人', '星星点灯', '麻花辫子', '你的生日', '表情', '达奇达奇嘟', '远离这个城市', '驿站']:
    test_zheng(t)
