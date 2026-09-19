#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('database/catalog_sync.db')
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM songs WHERE file_path IS NOT NULL AND file_path != ''")
print("catalog_sync.db lit songs:", c.fetchone()[0])

c.execute("SELECT COUNT(*) FROM songs WHERE file_path IS NOT NULL AND file_path != '' AND (lrc_path IS NULL OR lrc_path = '')")
print("catalog_sync.db lit songs with NO LRC:", c.fetchone()[0])

c.execute("SELECT COUNT(*) FROM songs WHERE lrc_path LIKE 'music/%'")
print("catalog_sync.db relative LRC:", c.fetchone()[0])

c.execute("SELECT COUNT(*) FROM songs WHERE file_path LIKE 'music/%'")
print("catalog_sync.db relative MP3:", c.fetchone()[0])

c.execute("""
    SELECT s.id, a.name, al.title, s.title, s.file_path, s.lrc_path
    FROM songs s
    JOIN artists a ON s.artist_id = a.id
    JOIN albums al ON s.album_id = al.id
    WHERE al.title LIKE '%无时无刻%' OR al.title LIKE '%原色%'
    LIMIT 5
""")
print("\nSample 李健/杨宗纬 songs:")
for row in c.fetchall():
    print(f"  ID: {row[0]} | {row[1]} - 《{row[2]}》 - 《{row[3]}》: {row[4]}")

c.execute("""
    SELECT 
        CASE 
            WHEN r2_mp3_key LIKE '%pub-9ea7ff16135d47238c0229f1aa54ecc4%' THEN 'Bucket 02'
            WHEN r2_mp3_key LIKE '%pub-383b876c0bb840f6b852946604275232%' THEN 'Bucket 03'
            WHEN r2_mp3_key LIKE '%pub-3507a1a1bc4b4ac3a3340833031078c2%' THEN 'Bucket 04'
            WHEN r2_mp3_key LIKE '%pub-e7d069eb11954440aeb32012e8e3c670%' THEN 'Bucket 05'
            WHEN r2_mp3_key LIKE '%pub-46ab5c0015d84be1b748cffecd23fdbb%' THEN 'Bucket 06'
            WHEN r2_mp3_key LIKE '%pub-a0a90fda9b0d45d59a52685eb2ee93d6%' THEN 'Bucket 07'
            WHEN r2_mp3_key LIKE '%pub-dd32e05660c74c3dba04d231391eb82b%' THEN 'Bucket 08'
            WHEN r2_mp3_key LIKE 'music/%' THEN 'Relative (Old/Bucket 01)'
            ELSE 'Other/Null'
        END AS bucket,
        status,
        COUNT(*)
    FROM tracks_sync_state
    GROUP BY bucket, status
""")
c.execute("""
    SELECT song_id, artist_name, album_title, song_title, r2_mp3_key, r2_lrc_key
    FROM tracks_sync_state
    WHERE status = 'D1_LIT' AND (r2_mp3_key NOT LIKE 'http%' AND r2_mp3_key NOT LIKE 'music/%')
    LIMIT 20
""")
print("\nOther/Null D1_LIT sample:")
for row in c.fetchall():
    print(f"  ID: {row[0]} | {row[1]} - 《{row[2]}》 - 《{row[3]}》: mp3={row[4]}, lrc={row[5]}")

c.execute("""
    SELECT song_id, artist_name, album_title, song_title, r2_mp3_key, r2_lrc_key
    FROM tracks_sync_state
    WHERE artist_name IN ('王菲', '古巨基', '周深') AND (
        song_title LIKE '%MV%' OR song_title LIKE '%日出%' OR song_title LIKE '%黄金%'
    )
""")
print("\nRecently fixed songs (王菲/古巨基/周深):")
for row in c.fetchall():
    print(f"  ID: {row[0]} | {row[1]} - 《{row[2]}》 - 《{row[3]}》: mp3={row[4]}, lrc={row[5]}")



