import sys
if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
import json
import urllib.parse
import base64

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# 1. Kugou Song Search
url = "http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword=动力火车 Selena&page=1&pagesize=10"
r = requests.get(url, headers=headers).json()
print("Kugou results:")
for song in r.get('data', {}).get('info', []):
    print("Song:", song.get('songname'), "Singer:", song.get('singername'), "Hash:", song.get('hash'), "Album:", song.get('album_name'))
    h = song.get('hash')
    # search lyric by hash
    lrc_url = f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword=&duration=&hash={h}"
    lr = requests.get(lrc_url, headers=headers).json()
    print("  candidates:", len(lr.get('candidates', [])))
    if lr.get('candidates'):
        cand = lr['candidates'][0]
        cid = cand['id']
        key = cand['accesskey']
        down_url = f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cid}&accesskey={key}&fmt=lrc&charset=utf8"
        dr = requests.get(down_url, headers=headers).json()
        lrc_text = base64.b64decode(dr.get('content', '')).decode('utf-8', errors='replace')
        print("  LRC lines:", len(lrc_text.splitlines()))
        print("  LRC preview:\n", "\n".join(lrc_text.splitlines()[:5]))
