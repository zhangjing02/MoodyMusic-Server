import urllib.request
import urllib.parse
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

keyword = '江美琪 恋人心中有一首诗'
url = f'https://api.bilibili.com/x/web-interface/search/type?keyword={urllib.parse.quote(keyword)}&search_type=video'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        for item in data.get('data', {}).get('result', [])[:5]:
            t = item.get('title', '').replace('<em class="keyword">', '').replace('</em>', '')
            print(f"{item.get('bvid')} | {t} | {item.get('duration')}")
except Exception as e:
    print('Error:', e)
