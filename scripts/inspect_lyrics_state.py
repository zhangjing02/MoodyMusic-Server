import sys
import sqlite3
import json

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect('backend/database/catalog_sync.db')
c = conn.cursor()

# 1. Check Power Station / 忠孝东路走九遍
print("--- 动力火车 《忠孝东路走九遍》 ---")
rows = c.execute("""
    SELECT song_id, artist_name, album_title, song_title, track_index, status, r2_mp3_key, r2_lrc_key, local_lrc
    FROM tracks_sync_state
    WHERE album_title LIKE '%忠孝东路走九遍%' OR artist_name LIKE '%动力火车%'
    ORDER BY album_title, track_index, song_id
""").fetchall()

print(f"Total found: {len(rows)}")
for r in rows:
    print(r)

# 2. Status counts
print("\n--- Status distribution ---")
status_counts = c.execute("SELECT status, count(*) FROM tracks_sync_state GROUP BY status").fetchall()
for s, cnt in status_counts:
    print(f"Status: {s} -> {cnt}")

# 3. Lit songs (status='D1_LIT' or r2_mp3_key valid)
print("\n--- Lit songs analysis ---")
total_lit = c.execute("""
    SELECT count(*) FROM tracks_sync_state
    WHERE status = 'D1_LIT' OR (r2_mp3_key IS NOT NULL AND r2_mp3_key != '')
""").fetchone()[0]
print(f"Total lit songs (status='D1_LIT' or r2_mp3_key valid): {total_lit}")

# Check r2_lrc_key conditions for lit songs
no_lrc = c.execute("""
    SELECT count(*) FROM tracks_sync_state
    WHERE (status = 'D1_LIT' OR (r2_mp3_key IS NOT NULL AND r2_mp3_key != ''))
      AND (r2_lrc_key IS NULL OR r2_lrc_key = '')
""").fetchone()[0]
print(f"Lit songs with empty r2_lrc_key: {no_lrc}")

old_rel_path = c.execute("""
    SELECT count(*) FROM tracks_sync_state
    WHERE (status = 'D1_LIT' OR (r2_mp3_key IS NOT NULL AND r2_mp3_key != ''))
      AND r2_lrc_key LIKE 'music/%'
""").fetchone()[0]
print(f"Lit songs with relative r2_lrc_key (starts with 'music/'): {old_rel_path}")

has_domain = c.execute("""
    SELECT count(*) FROM tracks_sync_state
    WHERE (status = 'D1_LIT' OR (r2_mp3_key IS NOT NULL AND r2_mp3_key != ''))
      AND r2_lrc_key LIKE 'http%'
""").fetchone()[0]
print(f"Lit songs with http domain r2_lrc_key: {has_domain}")

# Sample of old relative path or empty
sample_rel = c.execute("""
    SELECT song_id, artist_name, album_title, song_title, status, r2_mp3_key, r2_lrc_key
    FROM tracks_sync_state
    WHERE (status = 'D1_LIT' OR (r2_mp3_key IS NOT NULL AND r2_mp3_key != ''))
      AND (r2_lrc_key IS NULL OR r2_lrc_key = '' OR r2_lrc_key LIKE 'music/%')
    LIMIT 20
""").fetchall()
print("\nSample songs needing lrc update:")
for s in sample_rel:
    print(s)

conn.close()
