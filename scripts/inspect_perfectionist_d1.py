import requests
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

albums_to_check = ['68', '不想放手', '上五樓的快活', '哈囉', '第九次初戀', 'Better Life', '狼II']

for alb_kw in albums_to_check:
    url = f'https://m-api.changgepd.ccwu.cc/api/admin/albums/search?keyword={requests.utils.quote(alb_kw)}'
    try:
        r = requests.get(url, timeout=10).json()
        albums = r.get('data', {}).get('albums', [])
        print(f'=== Search: {alb_kw} (found {len(albums)}) ===')
        for a in albums:
            aid = a['id']
            det_url = f'https://m-api.changgepd.ccwu.cc/api/admin/albums/detail?album_id={aid}'
            det = requests.get(det_url, timeout=10).json().get('data', {})
            songs = det.get('songs', [])
            lit_songs = [s for s in songs if s.get('file_path')]
            print(f"  Album [{aid}] {a.get('artist_name')} - 《{a.get('title')}》: {len(lit_songs)}/{len(songs)} lit")
            for s in songs:
                if not s.get('file_path'):
                    print(f"    ⭕ UNLIT: [{s['id']}] track={s.get('track_index')} 《{s.get('title')}》")
    except Exception as e:
        print(f"Error checking {alb_kw}: {e}")
