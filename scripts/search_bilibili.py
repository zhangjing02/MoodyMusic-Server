import sys
import requests
import json
import re

sys.stdout.reconfigure(encoding='utf-8')

keyword = sys.argv[1] if len(sys.argv) > 1 else '老狼 恋恋风尘 专辑'
url = f'https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={keyword}'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com'
}

r = requests.get(url, headers=headers, timeout=10).json()
items = r.get('data', {}).get('result', [])
print(f"Results for '{keyword}' ({len(items)}):")
for item in items[:8]:
    raw_title = item.get('title', '')
    clean_title = re.sub(r'<[^>]+>', '', raw_title)
    bvid = item.get('bvid')
    duration = item.get('duration')
    print(f"  • [{bvid}] ({duration}) {clean_title}")
