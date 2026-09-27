import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('e:/Workspace/AI-Project/MoodyMusic-Workspace/backend/database/catalog_sync.db')
cursor = conn.cursor()
sql = '''
SELECT 
  al.id, al.title, al.release_date, s.track_index, s.title, s.file_path,
  MAX(CASE WHEN s.file_path IS NOT NULL AND s.file_path != '' THEN 1 ELSE 0 END) OVER (PARTITION BY al.id) as has_lit
FROM albums al
JOIN songs s ON al.id = s.album_id
WHERE al.artist_id = 15
ORDER BY 
  has_lit DESC,
  CASE WHEN al.release_date IS NULL OR al.release_date = '' THEN '9999' ELSE al.release_date END ASC,
  al.id ASC,
  s.track_index ASC
'''
cursor.execute(sql)
rows = cursor.fetchall()
seen_albums = {}
for r in rows:
    aid, title, year, tid, stitle, fpath, has_lit = r
    if aid not in seen_albums:
        seen_albums[aid] = {'title': title, 'year': year, 'has_lit': has_lit, 'tracks': 0, 'lit_tracks': 0}
    seen_albums[aid]['tracks'] += 1
    if fpath:
        seen_albums[aid]['lit_tracks'] += 1

print(f'Total albums: {len(seen_albums)}')
for aid, inf in list(seen_albums.items())[:20]:
    print(f"has_lit={inf['has_lit']} | {inf['year']} | {inf['title']} | {inf['lit_tracks']}/{inf['tracks']} tracks")
