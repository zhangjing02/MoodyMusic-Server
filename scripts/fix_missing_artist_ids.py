import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend/database/catalog_sync.db')
cur = conn.cursor()

# 1. 查询缺失 artist_id 的数量
cur.execute("""
    SELECT count(*) 
    FROM songs s 
    JOIN albums a ON s.album_id = a.id 
    WHERE s.artist_id IS NULL AND a.artist_id IS NOT NULL
""")
before_count = cur.fetchone()[0]
print(f"修复前缺失 artist_id 歌曲数量: {before_count}")

# 2. 执行修复
cur.execute("""
    UPDATE songs 
    SET artist_id = (SELECT a.artist_id FROM albums a WHERE a.id = songs.album_id)
    WHERE artist_id IS NULL AND album_id IN (SELECT id FROM albums WHERE artist_id IS NOT NULL)
""")
conn.commit()

# 3. 验证修复后数量
cur.execute("""
    SELECT count(*) 
    FROM songs s 
    JOIN albums a ON s.album_id = a.id 
    WHERE s.artist_id IS NULL AND a.artist_id IS NOT NULL
""")
after_count = cur.fetchone()[0]
print(f"修复后缺失 artist_id 歌曲数量: {after_count}")

# 4. 重点检查童安格歌曲
cur.execute("""
    SELECT s.id, s.title, s.artist_id, a.title, art.name 
    FROM songs s
    JOIN albums a ON s.album_id = a.id
    JOIN artists art ON s.artist_id = art.id
    WHERE s.id = 30128
""")
row = cur.fetchone()
print(f"童安格 30128 检查: ID={row[0]}, 歌名={row[1]}, artist_id={row[2]}, 专辑={row[3]}, 歌手={row[4]}")

conn.close()
print("✅ 本地 catalog_sync.db 修复完成！")
