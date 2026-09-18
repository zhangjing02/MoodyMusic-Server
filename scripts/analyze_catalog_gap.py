import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend/database/catalog_sync.db')
c = conn.cursor()

total_songs = c.execute('SELECT COUNT(*) FROM tracks_sync_state').fetchone()[0]
lit_songs = c.execute("SELECT COUNT(*) FROM tracks_sync_state WHERE status = 'D1_LIT'").fetchone()[0]
unlit_songs = total_songs - lit_songs

print(f'=== 全库总体盘点 ===')
print(f'总骨架歌曲数: {total_songs} 首')
print(f'已点亮可用: {lit_songs} 首 ({lit_songs/total_songs*100:.2f}%)')
print(f'待点亮留白: {unlit_songs} 首 ({unlit_songs/total_songs*100:.2f}%)')

artists_stat = c.execute('''
    SELECT artist_name, 
           COUNT(*) as total,
           SUM(CASE WHEN status = 'D1_LIT' THEN 1 ELSE 0 END) as lit,
           SUM(CASE WHEN status != 'D1_LIT' THEN 1 ELSE 0 END) as unlit,
           COUNT(DISTINCT album_title) as album_count
    FROM tracks_sync_state
    GROUP BY artist_name
    ORDER BY total DESC
''').fetchall()

print(f'\n全库收录艺人总数: {len(artists_stat)} 位')

zero_lit = [a for a in artists_stat if a[2] == 0]
partial_lit = [a for a in artists_stat if a[2] > 0 and a[3] > 0]
full_lit = [a for a in artists_stat if a[3] == 0]

print(f'  - 100% 全部点亮艺人: {len(full_lit)} 位')
print(f'  - 部分点亮 (仍有大批经典待补) 艺人: {len(partial_lit)} 位')
print(f'  - 0% 完全未采录 (纯留白等待入库) 艺人: {len(zero_lit)} 位')

print('\n================================================================================')
print('📋 一、 完全未点亮 (0% 留白) 的重要艺人群体 (亟待开辟新存储桶入库)')
print('================================================================================')
for a in sorted(zero_lit, key=lambda x: x[1], reverse=True)[:30]:
    print(f'  🎤 {a[0]:<12} | 总曲目: {a[1]:>3} 首 | 经典专辑: {a[4]:>2} 张 | 待采录: {a[3]:>3} 首')

print('\n================================================================================')
print('📋 二、 缺失曲目较多 (点亮率较低) 的知名巨星 (亟待扩充全专)')
print('================================================================================')
for a in sorted(partial_lit, key=lambda x: x[3], reverse=True)[:30]:
    pct = a[2] / a[1] * 100 if a[1] > 0 else 0
    print(f'  🎤 {a[0]:<12} | 待补: {a[3]:>3} 首 / 总: {a[1]:>3} 首 ({a[4]:>2} 专) | 当前完成率: {pct:>5.1f}% (已亮 {a[2]} 首)')

print('\n================================================================================')
print('📋 三、 各主要风格/流派缺失与点亮概览')
print('================================================================================')

conn.close()
