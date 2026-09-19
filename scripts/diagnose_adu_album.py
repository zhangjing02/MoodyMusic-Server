#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('database/catalog_sync.db')
c = conn.cursor()

c.execute("""
    SELECT al.id, al.title, count(s.id)
    FROM albums al
    JOIN songs s ON s.album_id = al.id
    WHERE al.title LIKE '%第9次%' OR al.title LIKE '%第九次%'
    GROUP BY al.id
""")
print("Albums for 阿杜 第九次初恋:")
for r in c.fetchall():
    print(r)

c.execute("""
    SELECT s.id, s.album_id, s.track_index, s.title, s.file_path, s.lrc_path
    FROM songs s
    JOIN albums al ON s.album_id = al.id
    WHERE al.title LIKE '%第9次%' OR al.title LIKE '%第九次%'
    ORDER BY s.album_id, s.track_index
""")
print("\nSongs:")
for r in c.fetchall():
    print(f"  AlbID:{r[1]} | Trk:{r[2]} | ID:{r[0]:<5} | 《{r[3]}》 | fp:{r[4]}")
