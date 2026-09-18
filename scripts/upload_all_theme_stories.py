# -*- coding: utf-8 -*-
import requests, json, sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

with open('backend/scripts/default_theme_stories.json', 'r', encoding='utf-8') as f:
    stories = json.load(f)

url = 'https://m-api.changgepd.ccwu.cc/api/admin/assets/upload'
for theme_id, story in stories.items():
    story_bytes = json.dumps(story, ensure_ascii=False, indent=2).encode('utf-8')
    filename = f'{theme_id}.json'
    files = {'file': (filename, story_bytes, 'application/json')}
    data = {'category': 'themes', 'filename': filename}
    r = requests.post(url, files=files, data=data)
    
    # Verify GET
    check = requests.get(f'https://m-api.changgepd.ccwu.cc/storage/themes/{theme_id}.json')
    hl = check.json().get('headline', '') if check.status_code == 200 else 'ERR'
    print(f"[{r.status_code}] {theme_id} -> GET {check.status_code}: {hl[:30]}")
