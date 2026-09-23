# -*- coding: utf-8 -*-
import requests
import json
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/'
}

def search_artist(name):
    url = f"http://music.163.com/api/search/get/web?s={requests.utils.quote(name)}&type=100&offset=0&limit=5"
    r = requests.get(url, headers=headers, timeout=10).json()
    artists = r.get('result', {}).get('artists', [])
    if artists:
        art = artists[0]
        return {
            'id': art.get('id'),
            'name': art.get('name'),
            'picUrl': art.get('picUrl'),
            'albumSize': art.get('albumSize')
        }
    return None

old_artists = ['迪克牛仔', '李克勤', '谭咏麟', '蔡琴', '许茹芸', '陈小春', '宋冬野']
new_artists = ['刘若英', '小虎队', '谭维维', '林志炫']

print("=== 老歌手头像测试 ===")
for name in old_artists:
    info = search_artist(name)
    print(f"{name}: {info}")

print("\n=== 新歌手测试 ===")
for name in new_artists:
    info = search_artist(name)
    print(f"{name}: {info}")
