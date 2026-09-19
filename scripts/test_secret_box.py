import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

# NetEase
r = requests.get('https://music.163.com/api/search/get/web?s=郑智化+Secret+Box&type=1&limit=5', headers={'User-Agent': 'Mozilla/5.0'}).json()
print("NetEase Secret Box:")
for s in r.get('result', {}).get('songs', [])[:5]:
    print(f"  • {s.get('name')} (ID: {s.get('id')}) | Album: {s.get('album', {}).get('name')}")

# Kuwo
r2 = requests.get('http://search.kuwo.cn/r.s?client=kt&all=郑智化+Secret+Box&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=5').text
print("Kuwo Secret Box:")
try:
    d = json.loads(r2.replace("'", '"'))
    for item in d.get('abslist', [])[:5]:
        print(f"  • {item.get('SONGNAME')} (RID: {item.get('DC_TARGETID')}) | Album: {item.get('ALBUM')}")
except Exception as e:
    print("Kuwo json parse error:", e)
