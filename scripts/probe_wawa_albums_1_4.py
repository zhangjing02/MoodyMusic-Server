#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查娃娃 (金智娟) 专辑曲目在网易云的匹配 ID 与 LRC 歌词情况
"""
import sys
import sqlite3
import requests

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

session = requests.Session()
session.trust_env = False
headers = {'User-Agent': 'Mozilla/5.0'}

conn = sqlite3.connect('e:/Workspace/AI-Project/MoodyMusic-Workspace/backend/database/catalog_sync.db')
cur = conn.cursor()
cur.execute('''SELECT al.id, al.title, al.release_date, s.id, s.title, s.track_index 
               FROM albums al JOIN songs s ON al.id = s.album_id 
               WHERE al.id IN (2234, 2235, 2236, 2237)
               ORDER BY al.id, s.track_index''')
rows = cur.fetchall()

curr_al = None
for r in rows:
    al_id, al_title, al_year, song_id, song_title, track_idx = r
    if al_id != curr_al:
        curr_al = al_id
        print(f"\n==========================================")
        print(f"💿 专辑 ID {al_id}: 《{al_title}》 ({al_year})")
        print(f"==========================================")
    
    # 搜索网易云
    url = f"https://music.163.com/api/search/get/web?csrf_token=hlpretag=&hlposttag=&s=娃娃 {song_title}&type=1&offset=0&total=true&limit=3"
    try:
        res = session.get(url, headers=headers, timeout=5).json()
        matches = res.get('result', {}).get('songs', [])
        found = False
        for m in matches:
            ar_names = '/'.join([a['name'] for a in m.get('artists', [])])
            if '娃娃' in ar_names or '金智娟' in ar_names:
                m_al = m.get('album', {}).get('name', '')
                print(f"  [Song {song_id}] #{track_idx} {song_title} -> 163 ID: {m['id']} ({m['name']}) | 专辑: {m_al}")
                found = True
                break
        if not found:
            # 尝试搜索不带娃娃前缀或单搜歌名
            url2 = f"https://music.163.com/api/search/get/web?csrf_token=hlpretag=&hlposttag=&s={song_title} 金智娟&type=1&offset=0&total=true&limit=2"
            res2 = session.get(url2, headers=headers, timeout=5).json()
            matches2 = res2.get('result', {}).get('songs', [])
            if matches2:
                m = matches2[0]
                m_al = m.get('album', {}).get('name', '')
                ar_names = '/'.join([a['name'] for a in m.get('artists', [])])
                print(f"  [Song {song_id}] #{track_idx} {song_title} -> 163 ID (2nd): {m['id']} ({m['name']}) | 歌手: {ar_names} | 专辑: {m_al}")
            else:
                print(f"  [Song {song_id}] #{track_idx} {song_title} -> 未精准匹配")
    except Exception as e:
        print(f"  [Song {song_id}] #{track_idx} {song_title} -> 查询出错: {e}")
