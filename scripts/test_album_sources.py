# -*- coding: utf-8 -*-
import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 测试网易云 v1 album 接口
url1 = "http://music.163.com/api/v1/album/25437"
r1 = requests.get(url1, headers={'Referer': 'https://music.163.com'}).json()
print("163 v1 songs:", len(r1.get('songs', [])))

# 测试 QQ 音乐搜索专辑
qq_search_album = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w=%E5%88%98%E8%8B%A5%E8%8B%B1%20%E6%88%91%E7%AD%89%E4%BD%A0&format=json&t=8"
rq = requests.get(qq_search_album).json()
albs = rq.get('data', {}).get('album', {}).get('list', [])
for a in albs[:3]:
    print("QQ Album:", a.get('albumName'), a.get('albumMID'), a.get('song_count'))

if albs:
    mid = albs[0].get('albumMID')
    qq_detail = f"https://c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg?albummid={mid}&format=json"
    rd = requests.get(qq_detail).json()
    song_list = rd.get('data', {}).get('list', [])
    print("QQ Album detail songs count:", len(song_list))
    for s in song_list[:5]:
        print("  -", s.get('songname'))
