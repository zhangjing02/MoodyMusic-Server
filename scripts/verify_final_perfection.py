import requests
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

albums_to_verify = [
    '无数', "IT'S ALL ABOUT LOVE", '蕭敬騰同名',
    '天黑', '哈囉', '第九次初戀',
    '不想放手', '68', '上五樓的快活',
    '冬雨', '出没', '呼唤', '无情的雨无情的你', '狼II',
    '面對品源', '愛你到永遠',
    'Stories', 'TEARS', '花兒不見了', '誰撿到這張紙條我愛你',
    'Better Life', '飞行部落'
]

print("=" * 85)
print("📊 MOODY 音乐曲库 - 强迫症经典大碟 100% 满贯终极验收")
print("=" * 85)

conn = sqlite3.connect('backend/database/catalog_sync.db')
c = conn.cursor()

total_albums_checked = 0
all_full = True

for kw in albums_to_verify:
    url = f'https://m-api.changgepd.ccwu.cc/api/admin/albums/search?keyword={requests.utils.quote(kw)}'
    r = requests.get(url, timeout=10).json()
    albums = r.get('data', {}).get('albums', [])
    for a in albums:
        aid = a['id']
        det_url = f'https://m-api.changgepd.ccwu.cc/api/admin/albums/detail?album_id={aid}'
        det = requests.get(det_url, timeout=10).json().get('data', {})
        songs = det.get('songs', [])
        lit = [s for s in songs if s.get('file_path')]
        
        # 只核验目标经典大碟
        if len(songs) >= 8:
            total_albums_checked += 1
            is_full = len(lit) == len(songs)
            if not is_full:
                all_full = False
            badge = "💯 [100% FULL]" if is_full else f"⚠️ [{len(lit)}/{len(songs)}]"
            print(f"{badge} Album [{aid}] {a.get('artist_name')} - 《{a.get('title')}》 ({len(lit)}/{len(songs)} 首全部点亮)")

conn.close()
print("=" * 85)
print(f"验收完毕！共检查 {total_albums_checked} 张经典大碟。")
if all_full:
    print("🎉 恭喜！所有目标大碟全部达成 100% 满贯大圆满！无任何零散遗珠！")
else:
    print("⚠️ 存在个别未达标专辑，请检查。")
print("=" * 85)
