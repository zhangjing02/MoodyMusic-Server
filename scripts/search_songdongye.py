# -*- coding: utf-8 -*-
import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 搜索 QQ音乐或网易云宋冬野
# QQ音乐搜索接口
qq_url = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w=%E5%AE%8B%E5%86%AC%E9%87%8E&format=json&t=9"
r = requests.get(qq_url, timeout=10).json()
singers = r.get('data', {}).get('singer', {}).get('list', [])
for s in singers:
    print("QQ Singer:", s.get('singerName'), s.get('singerMID'), s.get('singerPic'))

# 网易云
url163 = "http://music.163.com/api/search/get/web?s=%E5%AE%8B%E5%86%AC%E9%87%8E&type=100&offset=0&limit=10"
r163 = requests.get(url163, headers={'Referer': 'https://music.163.com'}).json()
for a in r163.get('result', {}).get('artists', []):
    print("163 Artist:", a.get('name'), a.get('id'), a.get('picUrl'))
