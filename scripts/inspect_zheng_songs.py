import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
with open('scratch/zheng_songs.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

for art in d.get('data', []):
    for alb in art.get('albums', []):
        songs = alb.get('songs', [])
        print(f"\n=== 专辑: 《{alb.get('title')}》 ({len(songs)} 首) ===")
        for s in songs:
            print(f"  [{s.get('TrackIndex')}] {s.get('title')} (ID: {s.get('id')}) -> {s.get('path')}")
