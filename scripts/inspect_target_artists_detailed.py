import os
import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = r"e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\database\catalog_sync.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

for aid, aname in [(95, '许巍'), (106, '羽·泉')]:
    print(f"\n==========================================")
    print(f"🎤 ARTIST: {aname} (ID: {aid})")
    print(f"==========================================")
    c.execute("SELECT id, title, release_date FROM albums WHERE artist_id = ? ORDER BY release_date", (aid,))
    albums = c.fetchall()
    for al in albums:
        alb_id, alb_title, alb_date = al
        c.execute("SELECT count(*) FROM songs WHERE album_id = ?", (alb_id,))
        total_songs = c.fetchone()[0]
        c.execute("SELECT count(*) FROM songs WHERE album_id = ? AND file_path IS NOT NULL AND file_path != ''", (alb_id,))
        lit_songs = c.fetchone()[0]
        c.execute("""
            SELECT count(*) FROM songs s 
            JOIN tracks_sync_state t ON t.song_id = s.id 
            WHERE s.album_id = ? AND t.status = 'D1_LIT'
        """, (alb_id,))
        d1_lit = c.fetchone()[0]
        print(f"💿 Album [{alb_id}] 《{alb_title}》 ({alb_date}): Total {total_songs} songs | Lit: {lit_songs} | D1_LIT: {d1_lit}")
        c.execute("SELECT id, track_index, title, file_path, lrc_path FROM songs WHERE album_id = ? ORDER BY track_index", (alb_id,))
        tracks = c.fetchall()
        for t in tracks:
            print(f"    - [{t[0]}] #{t[1]} {t[2]} | file: {bool(t[3])} | lrc: {bool(t[4])}")


conn.close()

