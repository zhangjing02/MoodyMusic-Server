import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')
url = "http://search.kuwo.cn/r.s?client=kt&all=郑智化+老幺的故事&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=15"
r = requests.get(url, timeout=5)
d = json.loads(r.text.replace("'", '"'))
for item in d.get('abslist', []):
    name = item.get('SONGNAME')
    alb = item.get('ALBUM')
    dur = item.get('DURATION')
    print(f"{name:20s} | {alb:20s} | {dur}s")
