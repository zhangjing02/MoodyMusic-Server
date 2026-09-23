# -*- coding: utf-8 -*-
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

API_BASE = "https://m-api.changgepd.ccwu.cc"
ASSET_UPLOAD_URL = f"{API_BASE}/api/admin/assets/upload"

qq_pic = "https://y.gtimg.cn/music/photo_new/T001R500x500M000004KKLWZ4320g1.jpg"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://y.qq.com/'
}

r = requests.get(qq_pic, headers=headers)
print("QQ Pic status:", r.status_code, "len:", len(r.content))

if r.status_code == 200:
    filename = "artist_137.jpg"
    files = {'file': (filename, r.content, 'image/jpeg')}
    data = {'category': 'artists', 'artist_id': '137', 'filename': filename}
    up = requests.post(ASSET_UPLOAD_URL, files=files, data=data, timeout=20)
    print("Upload result:", up.status_code, up.text)
