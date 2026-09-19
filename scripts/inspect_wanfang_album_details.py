#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import requests
import json
import ast

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

kuwo_album_ids = {
    '給你們': '15704217',
    '.....那些美麗的相遇': '9732512',
    '原來我們都是愛著的': '176135',
    '我們不要傷心了': '51197',
    '相愛的運氣': '2222',
    '這天': '68268',
    '不換': '2212',
    '林萬芳歌本 1 - 答案': '68277',
    '左手': '2213',
    '就值得了愛': '13550',
    '割愛': '68272',
    '一切如新': '2215',
    '斷線': '2221',
    'Tea for Two': '68271',
    '貼心': '2219',
    '時間仍然繼續在走': '68270',
    '真情': '2217',
    '放心': '2214'
}

def get_kuwo_tracks(album_id):
    url = f"http://search.kuwo.cn/r.s?pn=0&rn=30&albumid={album_id}&show_copyright_off=1&vipver=1&ft=music&encoding=utf8&rformat=json&mobi=1"
    try:
        r = requests.get(url, timeout=6)
        raw = r.text.replace('&nbsp;', ' ')
        data = ast.literal_eval(raw)
        return [(item.get('SONGNAME', ''), item.get('MUSICRID', '')) for item in data.get('abslist', [])]
    except Exception as e:
        return []

def main():
    for name, aid in kuwo_album_ids.items():
        tracks = get_kuwo_tracks(aid)
        print(f"\n💿 【{name}】(Kuwo ID: {aid}) - 共 {len(tracks)} 首:")
        for idx, (sname, srid) in enumerate(tracks):
            print(f"   #{idx}: {sname} ({srid})")

if __name__ == "__main__":
    main()
