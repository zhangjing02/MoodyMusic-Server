import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

ARTIST_MAP = {
    171: '金海心',
    172: '老狼',
    173: '杨乃文',
    174: '阿雅',
    175: '大张伟',
    176: '江美琪',
    177: '娃娃'
}

no_proxy = {'http': None, 'https': None}

for aid, ar in ARTIST_MAP.items():
    res = requests.get(f'https://m-api.changgepd.ccwu.cc/api/admin/albums/search?artist_id={aid}&limit=50', proxies=no_proxy, timeout=10).json()
    albums = res.get('data', {}).get('albums', [])
    print(f"\n=== [{aid}] {ar} ({len(albums)} albums) ===")
    for a in sorted(albums, key=lambda x: str(x.get('release_date', ''))):
        alb_id = a['id']
        title = a['title']
        sc = a.get('song_count', 0)
        year = a.get('release_date', '')
        print(f"  • [{alb_id}] 《{title}》 ({year}): {sc} songs")

