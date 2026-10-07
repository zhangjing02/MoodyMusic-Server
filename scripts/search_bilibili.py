import sys, requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=杨坤 自由之花'
r = requests.get(url, headers=headers).json()
for item in r.get('data', {}).get('result', [])[:5]:
    title = item.get('title','').replace('<em class="keyword">', '').replace('</em>', '')
    print(f"bvid: {item.get('bvid')} - {title} ({item.get('duration')})")
