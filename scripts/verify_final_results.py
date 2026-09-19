import requests
import json
import urllib.parse
import sys

sys.stdout.reconfigure(encoding='utf-8')

def check_artist(artist_name):
    encoded = urllib.parse.quote(artist_name)
    url = f"https://m-api.changgepd.ccwu.cc/api/songs?artist={encoded}"
    r = requests.get(url, timeout=20)
    data = r.json()
    songs = data.get('data', [])
    
    albums = {}
    for s in songs:
        alb = s.get('album') or '未分类'
        if alb not in albums:
            albums[alb] = []
        albums[alb].append(s)
        
    print("=" * 80)
    print(f"🎵 【{artist_name}】全专生产线上线验证 (共收录 {len(songs)} 首曲目，{len(albums)} 张大碟)")
    print("=" * 80)
    total_lit = 0
    for alb, track_list in albums.items():
        lit = sum(1 for s in track_list if s.get('file_path'))
        total_lit += lit
        print(f" • 《{alb}》: {lit}/{len(track_list)} 首已点亮")
    print(f"\n🎉 汇总: {artist_name} {total_lit}/{len(songs)} 首全部点亮上线! (点亮比例: {total_lit/len(songs)*100:.1f}%)")
    return len(songs), total_lit

print("\n🚀 正在从 Cloudflare D1 生产网关拉取最新全量状态...\n")
check_artist("迪克牛仔")
print("\n")
check_artist("郑智化")
