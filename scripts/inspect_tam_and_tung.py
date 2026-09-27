import sys, sqlite3, requests, json
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend/database/catalog_sync.db')
cur = conn.cursor()

# 1. Check 童安格 in local DB
cur.execute("SELECT * FROM artists WHERE name LIKE '%童安格%'")
tong = cur.fetchall()
print('=== 童安格 in local artists table ===')
print(tong)

# 2. Check 谭咏麟 in local DB
cur.execute("SELECT * FROM artists WHERE name LIKE '%谭咏麟%' OR name LIKE '%譚詠麟%'")
alan = cur.fetchall()
print('=== 谭咏麟 in local artists table ===')
print(alan)

if alan:
    aid = alan[0][0]
    cur.execute('''SELECT a.id, a.title, a.release_date, 
                          COUNT(s.id) as total_songs,
                          SUM(CASE WHEN s.file_path IS NOT NULL AND s.file_path != '' THEN 1 ELSE 0 END) as lit_songs
                   FROM albums a 
                   LEFT JOIN songs s ON a.id = s.album_id 
                   WHERE a.artist_id = ? 
                   GROUP BY a.id 
                   ORDER BY a.release_date''', (aid,))
    albums = cur.fetchall()
    print(f'\n=== 谭咏麟 Albums ({len(albums)} albums) ===')
    for al in albums:
        print(f'{al[0]} | {al[1]} ({al[2]}) | lit: {al[4]}/{al[3]}')

# 3. Check Cloudflare D1 via Worker API
print('\n=== Querying Cloudflare D1 for 童安格 ===')
try:
    r = requests.get('https://m-api.changgepd.ccwu.cc/api/songs?artistName=童安格', proxies={'http': None, 'https': None}, timeout=10)
    print("D1 search 童安格 status:", r.status_code)
    if r.ok:
        data = r.json()
        print("Data length:", len(data.get('data', [])))
        if data.get('data'):
            print(json.dumps(data.get('data')[:1], ensure_ascii=False, indent=2))
except Exception as e:
    print("Error querying D1:", e)

# 4. Check Cloudflare D1 for 谭咏麟
print('\n=== Querying Cloudflare D1 for 谭咏麟 ===')
try:
    r = requests.get('https://m-api.changgepd.ccwu.cc/api/songs?artistName=谭咏麟', proxies={'http': None, 'https': None}, timeout=10)
    print("D1 search 谭咏麟 status:", r.status_code)
    if r.ok:
        data = r.json()
        print("Data length:", len(data.get('data', [])))
        if data.get('data'):
            al_list = data['data'][0].get('albums', [])
            print(f"Total D1 albums for 谭咏麟: {len(al_list)}")
            for al in al_list:
                print(f"  {al.get('title')} ({al.get('year')}) - songs: {len(al.get('songs', []))}")
except Exception as e:
    print("Error querying D1:", e)
