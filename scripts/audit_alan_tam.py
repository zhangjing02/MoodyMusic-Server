import sqlite3

def audit_alan():
    conn = sqlite3.connect('backend/database/catalog_sync.db')
    c = conn.cursor()

    c.execute('SELECT id, name FROM artists WHERE name LIKE ?', ('%谭咏麟%',))
    row = c.fetchone()
    if not row:
        print("Alan Tam not found in DB")
        return
    aid, aname = row
    print(f"Artist: {aname} (ID: {aid})")

    query = """
    SELECT 
        a.id, 
        a.title, 
        a.release_date, 
        COUNT(s.id) as total_songs,
        SUM(CASE WHEN s.file_path IS NOT NULL AND s.file_path != '' AND s.file_path NOT LIKE 'pending%' THEN 1 ELSE 0 END) as lit_songs
    FROM albums a
    LEFT JOIN songs s ON a.id = s.album_id
    WHERE a.artist_id = ?
    GROUP BY a.id
    ORDER BY a.release_date ASC, a.id ASC
    """
    c.execute(query, (aid,))
    albums = c.fetchall()
    
    total_songs = sum(a[3] for a in albums)
    total_lit = sum(a[4] for a in albums)
    
    lit_albums = [a for a in albums if a[4] > 0]
    unlit_albums = [a for a in albums if a[4] == 0]
    
    print(f"\n==========================================")
    print(f"谭咏麟专辑大盘现状: 共 {len(albums)} 张专辑，{total_songs} 首歌曲")
    print(f"已点亮: {len(lit_albums)} 张专辑，{total_lit} 首歌曲")
    print(f"待补全/未点亮: {len(unlit_albums)} 张专辑，{total_songs - total_lit} 首歌曲")
    print(f"==========================================")
    
    print(f"\n🌟 已点亮大碟 ({len(lit_albums)} 张):")
    for a in lit_albums:
        pct = (a[4] / a[3] * 100) if a[3] else 0
        print(f"  ✅ [{a[2] or '未知年份':^6}] 《{a[1]}》: {a[4]}/{a[3]} 首 ({pct:.0f}%) (Album ID: {a[0]})")
        
    print(f"\n⏳ 待点亮大碟 ({len(unlit_albums)} 张):")
    for a in unlit_albums:
        print(f"  ⭕ [{a[2] or '未知年份':^6}] 《{a[1]}》: 0/{a[3]} 首 (Album ID: {a[0]})")

    conn.close()

if __name__ == '__main__':
    audit_alan()
