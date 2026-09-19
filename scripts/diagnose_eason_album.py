#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('database/catalog_sync.db')
c = conn.cursor()

c.execute("""
    SELECT s.id, s.track_index, s.title, s.file_path, s.lrc_path
    FROM songs s
    JOIN albums al ON s.album_id = al.id
    WHERE al.title LIKE '%一滴眼淚%' OR al.title LIKE '%一滴眼泪%'
    ORDER BY s.track_index ASC
""")
print("Songs in 陈奕迅 《一滴眼泪》:")
for r in c.fetchall():
    print(f"  Track {r[1]} | ID: {r[0]:<5} | 《{r[2]}》 | file_path: {r[3]}")
