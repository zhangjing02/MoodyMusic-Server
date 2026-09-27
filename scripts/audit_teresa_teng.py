import sqlite3

def audit_teresa():
    conn = sqlite3.connect('backend/database/catalog_sync.db')
    c = conn.cursor()

    aid = 15
    c.execute('SELECT id, name FROM artists WHERE id = ?', (aid,))
    art = c.fetchone()
    print(f"Artist: {art[1]} (ID: {art[0]})")

    c.execute('''
        SELECT a.id, a.title, a.release_date, count(s.id), 
               sum(case when s.file_path is not null and s.file_path != '' and s.file_path not like 'pending%' then 1 else 0 end) as lit
        FROM albums a 
        LEFT JOIN songs s ON a.id = s.album_id 
        WHERE a.artist_id = ? 
        GROUP BY a.id 
        ORDER BY a.release_date ASC, a.id ASC
    ''', (aid,))
    rows = c.fetchall()
    
    total_albums = len(rows)
    total_songs = sum(r[3] for r in rows)
    total_lit = sum(r[4] for r in rows)
    
    print(f"\n==========================================")
    print(f"邓丽君专辑总盘: {total_albums} 张专辑, {total_songs} 首歌曲")
    print(f"已点亮: {total_lit} 首, 待点亮: {total_songs - total_lit} 首")
    print(f"==========================================")
    
    lit_albums = [r for r in rows if r[4] > 0]
    unlit_albums = [r for r in rows if r[4] == 0]
    
    print(f"\n🌟 已点亮专辑 ({len(lit_albums)} 张):")
    for r in lit_albums:
        yr = r[2] if r[2] else '未知'
        print(f"  ✅ [{yr:^8}] 《{r[1]}》: {r[4]}/{r[3]} 首 (Album ID: {r[0]})")
        
    print(f"\n⏳ 待点亮专辑 ({len(unlit_albums)} 张，前 30 张):")
    for r in unlit_albums[:30]:
        yr = r[2] if r[2] else '未知'
        print(f"  ⭕ [{yr:^8}] 《{r[1]}》: {r[4]}/{r[3]} 首 (Album ID: {r[0]})")
        
    conn.close()

if __name__ == '__main__':
    audit_teresa()
