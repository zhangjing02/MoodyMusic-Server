import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect(r"e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\database\catalog_sync.db")
c = conn.cursor()

print("==================== XU WEI (许巍) ====================")
c.execute("SELECT id, title, release_date FROM albums WHERE artist_id = 95 ORDER BY release_date")
xuwei_albums = c.fetchall()
for alb in xuwei_albums:
    print(f"\nAlbum [{alb[0]}] 《{alb[1]}》 ({alb[2]})")
    c.execute("SELECT id, track_index, title, file_path, lrc_path FROM songs WHERE album_id = ? ORDER BY track_index", (alb[0],))
    songs = c.fetchall()
    print(f"  Song count: {len(songs)}")
    for s in songs:
        print(f"    - ID: {s[0]}, #{s[1]} {s[2]}, file: {s[3]}, lrc: {s[4]}")

print("\n==================== YU QUAN (羽·泉) ====================")
c.execute("SELECT id, title, release_date FROM albums WHERE artist_id = 106 ORDER BY release_date")
yuquan_albums = c.fetchall()
for alb in yuquan_albums:
    print(f"\nAlbum [{alb[0]}] 《{alb[1]}》 ({alb[2]})")
    c.execute("SELECT id, track_index, title, file_path, lrc_path FROM songs WHERE album_id = ? ORDER BY track_index", (alb[0],))
    songs = c.fetchall()
    print(f"  Song count: {len(songs)}")
    for s in songs:
        print(f"    - ID: {s[0]}, #{s[1]} {s[2]}, file: {s[3]}, lrc: {s[4]}")

conn.close()
