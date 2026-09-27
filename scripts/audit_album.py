import sys, urllib.request, urllib.parse, ssl, sqlite3

def check_album(aid):
    sys.stdout.reconfigure(encoding='utf-8')
    ctx = ssl.create_default_context()
    conn = sqlite3.connect('backend/database/catalog_sync.db')
    cur = conn.cursor()
    cur.execute('SELECT title FROM albums WHERE id = ?', (aid,))
    row = cur.fetchone()
    if not row:
        print(f"Album {aid} not found")
        return
    print(f"=== Album {aid}: 《{row[0]}》 ===")
    cur.execute('SELECT id, title, file_path, lrc_path, duration FROM songs WHERE album_id = ? ORDER BY id', (aid,))
    for sid, title, fpath, lpath, dur in cur.fetchall():
        status = []
        for label, u in [('MP3', fpath), ('LRC', lpath)]:
            if not u:
                status.append(f"{label}: NONE")
                continue
            p = urllib.parse.urlsplit(u)
            u_enc = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), '', ''))
            try:
                req = urllib.request.Request(u_enc, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, context=ctx, timeout=6) as r:
                    cl = r.headers.get('Content-Length')
                    status.append(f"{label}: 200 ({cl}B)")
            except Exception as e:
                status.append(f"{label}: ERR ({e})")
        print(f"  [{sid}] 《{title}》 ({dur}s) -> " + " | ".join(status))

if __name__ == '__main__':
    for a in sys.argv[1:]:
        check_album(int(a))
