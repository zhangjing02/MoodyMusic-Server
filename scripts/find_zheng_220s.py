import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

for pn in range(3):
    url = f"http://search.kuwo.cn/r.s?client=kt&all=郑智化&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn={pn}&rn=50"
    r = requests.get(url, timeout=5)
    d = json.loads(r.text.replace("'", '"'))
    for item in d.get('abslist', []):
        dur = int(item.get('DURATION', 0))
        if 218 <= dur <= 222:
            name = item.get('SONGNAME')
            alb = item.get('ALBUM')
            rid = item.get('DC_TARGETID')
            print(f"Match: {name:20s} | {alb:20s} | {dur}s | RID: {rid}")
