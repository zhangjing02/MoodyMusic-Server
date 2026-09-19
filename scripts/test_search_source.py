# -*- coding: utf-8 -*-
import sys
import re
import requests
import subprocess
import json

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def search_bilibili(artist, song):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com'
    }
    url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={artist} {song}"
    try:
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            res = r.json().get('data', {}).get('result', [])
            items = []
            for v in res:
                raw_title = re.sub(r'<[^>]+>', '', v.get('title', ''))
                bvid = v.get('bvid')
                dur = v.get('duration')
                # 过滤合集/过长视频
                parts = dur.split(':')
                sec = int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else 0
                if 90 <= sec <= 420: # 1.5 ~ 7 分钟
                    items.append({
                        'source': 'bilibili',
                        'bvid': bvid,
                        'url': f"https://www.bilibili.com/video/{bvid}",
                        'title': raw_title,
                        'duration': dur,
                        'sec': sec
                    })
            return items
    except Exception as e:
        print(f"Bilibili search error: {e}")
    return []

def search_youtube(artist, song):
    cmd = [
        'yt-dlp', '--proxy', 'http://127.0.0.1:10090',
        '--js-runtimes', 'node',
        '--extractor-args', 'youtube:player_client=android,web',
        '--print', '%(id)s | %(title)s | %(duration_string)s | %(channel)s',
        f'ytsearch5:{artist} {song}'
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
        lines = p.stdout.strip().splitlines()
        items = []
        for line in lines:
            parts = [x.strip() for x in line.split('|')]
            if len(parts) >= 4:
                vid, vtitle, vdur, vchannel = parts[0], parts[1], parts[2], parts[3]
                items.append({
                    'source': 'youtube',
                    'id': vid,
                    'url': f"https://www.youtube.com/watch?v={vid}",
                    'title': vtitle,
                    'duration': vdur,
                    'channel': vchannel
                })
        return items
    except Exception as e:
        print(f"YouTube search error: {e}")
    return []

def search_netease(artist, song):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    url = f"https://music.163.com/api/search/get/web?s={artist} {song}&type=1&limit=3"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            songs = r.json().get('result', {}).get('songs', [])
            items = []
            for s in songs:
                sid = s.get('id')
                name = s.get('name')
                art = s.get('artists', [{}])[0].get('name')
                alb = s.get('album', {}).get('name')
                mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                try:
                    head = requests.head(mp3_url, headers=headers, allow_redirects=True, timeout=5)
                    size = int(head.headers.get('Content-Length', 0))
                    ctype = head.headers.get('Content-Type', '')
                    if head.status_code == 200 and 'audio' in ctype and size > 1000000:
                        items.append({
                            'source': 'netease',
                            'id': sid,
                            'url': mp3_url,
                            'title': f"{art} - {name} ({alb})",
                            'size': size
                        })
                except Exception:
                    pass
            return items
    except Exception as e:
        print(f"NetEase error: {e}")
    return []

if __name__ == '__main__':
    artist = "齐秦"
    song = "往事随风"
    print(f"Testing search for {artist} 《{song}》...")
    
    n_res = search_netease(artist, song)
    print(f"\n🎵 NetEase 结果 ({len(n_res)} 个):")
    for n in n_res:
        print(f"  [{n['id']}] {n['size'] / 1024 / 1024:.2f} MB | {n['title']} -> {n['url']}")

    y_res = search_youtube(artist, song)
    print(f"\n▶️ YouTube 结果 ({len(y_res)} 个):")
    for y in y_res[:3]:
        print(f"  [{y['id']}] {y['duration']} | {y['title']} ({y['channel']})")

