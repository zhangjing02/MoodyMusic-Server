import urllib.request, urllib.parse, ssl, sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
ctx = ssl.create_default_context()
tracks = [27074, 27075, 27076, 27077, 27078, 27079, 27080, 27081, 27082, 27083, 27084]
conn = sqlite3.connect('backend/database/catalog_sync.db')
cur = conn.cursor()
for tid in tracks:
    cur.execute('SELECT title, file_path, lrc_path, duration FROM songs WHERE id = ?', (tid,))
    row = cur.fetchone()
    title, path, lrc_path, dur = row[0], row[1], row[2], row[3]
    parsed = urllib.parse.urlparse(path)
    safe_path = urllib.parse.quote(parsed.path)
    url = f"{parsed.scheme}://{parsed.netloc}{safe_path}"
    if parsed.query:
        url += f"?{parsed.query}"
    
    req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            cl = resp.headers.get('Content-Length')
            print(f"ID {tid} 《{title}》 ({dur}s): {resp.status} ({cl} bytes) -> {path}")
    except Exception as e:
        print(f"ID {tid} 《{title}》 ({dur}s): ERROR {e} -> {path}")
