import sys
if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
import os

conn = sqlite3.connect('backend/database/catalog_sync.db')
c = conn.cursor()

query = """
    SELECT count(*)
    FROM tracks_sync_state
    WHERE (status = 'D1_LIT' OR (r2_mp3_key IS NOT NULL AND r2_mp3_key != ''))
      AND (r2_lrc_key IS NULL OR r2_lrc_key = '' OR r2_lrc_key LIKE 'music/%')
"""
c.execute(query)
total_need = c.fetchone()[0]
print(f"Total lit songs needing LRC fix/backfill: {total_need}")

# Check local_lrc column for these songs
c.execute("""
    SELECT count(*)
    FROM tracks_sync_state
    WHERE (status = 'D1_LIT' OR (r2_mp3_key IS NOT NULL AND r2_mp3_key != ''))
      AND (r2_lrc_key IS NULL OR r2_lrc_key = '' OR r2_lrc_key LIKE 'music/%')
      AND local_lrc IS NOT NULL AND local_lrc != ''
""")
has_local_path = c.fetchone()[0]
print(f"Of these, have non-empty local_lrc in DB: {has_local_path}")

# Check distinct artists
c.execute("""
    SELECT artist_name, count(*)
    FROM tracks_sync_state
    WHERE (status = 'D1_LIT' OR (r2_mp3_key IS NOT NULL AND r2_mp3_key != ''))
      AND (r2_lrc_key IS NULL OR r2_lrc_key = '' OR r2_lrc_key LIKE 'music/%')
    GROUP BY artist_name
    ORDER BY count(*) DESC
""")
artist_counts = c.fetchall()
print(f"Total distinct artists: {len(artist_counts)}")
print("Top 15 artists:")
for a, cnt in artist_counts[:15]:
    print(f"  {a}: {cnt}")

conn.close()
