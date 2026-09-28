import sys, sqlite3
sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect("backend/database/catalog_sync.db")
c = conn.cursor()

artists = ["杨乃文", "阿雅", "大张伟", "江美琪", "娃娃"]
for a in artists:
    c.execute("SELECT id, name FROM artists WHERE name LIKE ?", (f"%{a}%",))
    arts = c.fetchall()
    print(f"\n==================== {a} ====================")
    for art in arts:
        aid = art[0]
        aname = art[1]
        print(f"Artist ID: {aid}, Name: {aname}")
        c.execute("SELECT id, title, release_date FROM albums WHERE artist_id = ? ORDER BY release_date", (aid,))
        albs = c.fetchall()
        for alb in albs:
            c.execute("SELECT COUNT(*) FROM songs WHERE album_id = ?", (alb[0],))
            cnt = c.fetchone()[0]
            print(f"  Album ID: {alb[0]:<5} | 《{alb[1]}》 ({alb[2]}) | {cnt} 首")
